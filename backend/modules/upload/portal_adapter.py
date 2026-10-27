"""Bridge the supplied document/Bedrock pipeline to the established portal DTO.

The source document is never overwritten. All money stays Decimal text, and
missing discounts/taxes remain unknown until the reviewer confirms them.
"""
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import warnings
import json
from PIL import Image, ImageOps
from . import service
from ...models import HEADER_FIELDS, ITEM_FIELDS

SOURCE_ID = 'amiga-20261015T221710Z-1-001'
FIELD_MAP = {'vendor_name': 'supplier_name', 'bank_name': 'supplier_bank_name',
             'account_number': 'supplier_bank_account_number', 'account_holder': 'supplier_bank_account_name',
             'invoice_tax_amount': 'tax_amount'}


@dataclass(frozen=True)
class PreparedDocument:
    content: bytes
    pages: int
    filename: str
    original_content: bytes | None = None
    original_filename: str | None = None
    original_mime: str | None = None


def prepare_document(content, filename, config, *, allow_images=False):
    """Use the ZIP's inspectors; conversion is bounded and deterministic."""
    extension = Path(filename).suffix.lower()
    if not content or len(content) > config['FILE_LIMIT']:
        raise service.UploadError('Berkas kosong atau melebihi batas ukuran.')
    with TemporaryDirectory(prefix='amiga-inspect-', dir=config['UPLOAD_DIR']) as directory:
        path = Path(directory) / ('source' + extension)
        path.write_bytes(content)
        if extension == '.pdf' and content.startswith(b'%PDF-'):
            details = service.inspect_pdf(path)
            if details['page_count'] > config['PAGE_LIMIT']:
                raise service.UploadError('PDF harus berisi 1–5 halaman.')
            return PreparedDocument(content, details['page_count'], filename)
        if not allow_images or extension not in service.IMAGE_FORMATS:
            raise service.UploadError('Unggah PDF, JPG, JPEG, PNG, atau WEBP yang valid.' if allow_images else 'Bukti pendukung harus PDF.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as picture:
                    if picture.width * picture.height > config.get('IMAGE_PIXEL_LIMIT', 20_000_000):
                        raise service.UploadError('Resolusi foto terlalu besar. Gunakan gambar maksimal 20 megapiksel.')
                service.inspect_image(path, extension)
                with Image.open(path) as picture:
                    normalized = ImageOps.exif_transpose(picture).convert('RGB')
                    output = BytesIO()
                    normalized.save(output, format='PDF', resolution=150,
                                    title='Invoice scan', creationDate='D:20000101000000Z', modDate='D:20000101000000Z')
        except service.UploadError:
            raise
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise service.UploadError('Foto tidak dapat dibaca atau resolusinya tidak aman.') from exc
        converted = output.getvalue()
        if len(converted) > config['FILE_LIMIT']:
            raise service.UploadError('PDF hasil konversi melebihi batas ukuran.')
        return PreparedDocument(converted, 1, str(Path(filename).with_suffix('.pdf')),
                                content, filename, {'.jpg':'image/jpeg','.jpeg':'image/jpeg',
                                                    '.png':'image/png','.webp':'image/webp'}[extension])


def _decimal_text(value):
    if isinstance(value, Decimal):
        return format(value, 'f')
    if type(value) is int:
        return str(value)
    return value


def from_source_invoice(row):
    result = {key: _decimal_text(row.get(FIELD_MAP.get(key, key))) for key in HEADER_FIELDS}
    result['line_items'] = [{key: _decimal_text(item.get(key)) for key in ITEM_FIELDS}
                            for item in row.get('line_items', [])]
    return result


def to_source_invoice(fields):
    result = {FIELD_MAP.get(key, key): fields.get(key) for key in HEADER_FIELDS}
    result['line_items'] = [dict(item) for item in fields['line_items']]
    return result


def extract_for_portal(path, config):
    provider = config.get('AI_PROVIDER', 'openai')
    if provider not in ('openai', 'bedrock'):
        raise RuntimeError('EXTRACTION_NOT_CONFIGURED')
    if provider == 'openai':
        # Provider choice is explicit; no silent cross-provider fallback.
        from ...openai_extractor import extract_pdf
        result = extract_pdf(path, config)
        result['source_backend'] = SOURCE_ID
        result['source_invoices'] = [to_source_invoice(row) for row in result['invoices']]
        return result
    if not config.get('BEDROCK_MODEL_ID'):
        raise RuntimeError('EXTRACTION_NOT_CONFIGURED')
    with TemporaryDirectory(prefix='amiga-extract-', dir=config.get('UPLOAD_DIR', path.parent)) as directory:
        text_path = Path(directory) / 'extracted.txt'
        document = service.extract_pdf_text(path, text_path)
        if document['status'] == 'OCR_REQUIRED':
            document = service.extract_document_with_bedrock(path, 'PDF', text_path,
                config['BEDROCK_MODEL_ID'], config['AWS_REGION'])
        extracted_text = text_path.read_text(encoding='utf-8')
        result = service.extract_invoice_data_with_bedrock(extracted_text,
            config['BEDROCK_MODEL_ID'], config['AWS_REGION'])
    source_rows = json.loads(json.dumps(result['invoices'], default=_decimal_text))
    return {'invoices': [from_source_invoice(row) for row in source_rows],
            'source_invoices': source_rows, 'source_backend': SOURCE_ID,
            'ocr_text': extracted_text, 'provider':'bedrock', 'model':config['BEDROCK_MODEL_ID'],
            'document_extraction':document, 'model_response':result.get('model_response')}
