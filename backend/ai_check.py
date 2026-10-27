"""Explicit paid provider smoke check using a fictional PDF, never a user's invoice."""
import json
from pathlib import Path
import tempfile
from decimal import Decimal
from reportlab.pdfgen.canvas import Canvas
from .processing import real_extractor
from .validation import normalize, validate


def check_ai(app):
    root = Path(__file__).resolve().parent.parent / '.runtime-temp'
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        path = Path(directory) / 'fictitious-invoice.pdf'
        canvas = Canvas(str(path))
        lines = ['INVOICE - FICTIONAL TEST DATA ONLY', 'Vendor: Vendor Fiktif AMIGA',
                 'Invoice number: INV-QA-001', 'Invoice date: 2026-01-01', 'Currency: IDR',
                 'Item: Jasa uji | Quantity: 1 | Unit price: 100000 | Discount: 0 | Tax: 0 | Line total: 100000',
                 'Subtotal: 100000', 'Invoice discount: 0', 'Invoice tax: 0', 'TOTAL: 100000',
                 'Bank: Bank Fiktif', 'Account number: 0000123', 'Account holder: Vendor Fiktif AMIGA']
        for i, line in enumerate(lines):
            canvas.setFont('Helvetica', 10)
            canvas.drawString(36, 790 - 22*i, line)
        canvas.save()
        raw = real_extractor(path, app.config)
        rows = raw.get('invoices', [])
        if len(rows) != 1:
            raise RuntimeError('AI_CHECK_FAILED')
        fields = normalize(rows[0])
        result = validate(fields, 1, len(fields['line_items']))
        if (not result['valid'] or fields['invoice_number'] != 'INV-QA-001' or fields['account_number'] != '0000123'
                or Decimal(result['calculated']['total'] or '0') != Decimal('100000')):
            raise RuntimeError('AI_CHECK_FAILED')
        return {'provider': app.config['AI_PROVIDER'], 'model': app.config.get('BEDROCK_MODEL_ID') if app.config['AI_PROVIDER'] == 'bedrock' else app.config.get('OPENAI_MODEL'),
                'live_extraction_verified': True, 'fictional_pdf_only': True,
                'invoice_count': 1, 'line_item_count': len(fields['line_items']),
                'validation_passed': True, 'account_leading_zeros_preserved': True,
                'usage': raw.get('usage', {})}


def print_check(app):
    try:
        result = check_ai(app)
    except Exception as exc:
        allowed = {'EXTRACTION_NOT_CONFIGURED', 'EXTRACTION_TRUNCATED', 'EXTRACTION_REFUSED', 'EXTRACTION_INVALID_OUTPUT',
                   'OPENAI_AUTH_FAILED', 'OPENAI_ACCESS_DENIED', 'OPENAI_MODEL_UNAVAILABLE', 'OPENAI_QUOTA_LIMIT', 'OPENAI_UNAVAILABLE',
                   'BEDROCK_AUTH_FAILED', 'BEDROCK_ACCESS_DENIED', 'BEDROCK_QUOTA_LIMIT',
                   'BEDROCK_MODEL_UNAVAILABLE', 'BEDROCK_INVALID_REQUEST', 'BEDROCK_UNAVAILABLE'}
        code = str(exc) if str(exc) in allowed else 'AI_CHECK_FAILED'
        print(json.dumps({'live_extraction_verified': False, 'code': code}))
        return 1
    print(json.dumps(result))
    return 0
