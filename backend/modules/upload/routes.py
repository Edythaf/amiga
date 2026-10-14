import json
import re
import secrets
import time
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from backend.voucher_service import generate_voucher_pdf

from .service import (
    OcrError,
    UploadError,
    extract_document_with_bedrock,
    extract_invoice_data_with_bedrock,
    extract_pdf_text,
    save_document,
    validate_invoice_data,
)


upload_bp = Blueprint("upload", __name__)

DOCUMENT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
LINE_ITEM_PATTERN = re.compile(
    r"^line_items\[(\d+)\]\[(description|quantity|unit_price|line_total)\]$"
)

EDITABLE_INVOICE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "due_date",
    "purchase_order_number",
    "supplier_name",
    "supplier_address",
    "customer_name",
    "customer_address",
    "purpose",
    "service_period",
    "payment_method",
    "supplier_bank_name",
    "supplier_bank_account_number",
    "supplier_bank_account_name",
    "currency",
    "subtotal",
    "tax_rate",
    "tax_amount",
    "total_amount",
)


def get_upload_token():
    if "upload_token" not in session:
        session["upload_token"] = secrets.token_hex(32)
    return session["upload_token"]


def is_valid_csrf_token(token):
    submitted_token = request.form.get("csrf_token", "")
    return secrets.compare_digest(token, submitted_token)


def render_upload_error(
    token,
    message,
    status_code,
    result=None,
    invoice_data=None,
    extracted_text="",
):
    return (
        render_template(
            "upload.html",
            token=token,
            result=result,
            invoice_data=invoice_data,
            extracted_text=extracted_text,
            error=message,
            upload_time=session.get("upload_time"),
        ),
        status_code,
    )


def get_document_paths(document_id):
    if not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        abort(400)

    document_dir = Path(current_app.config["UPLOAD_DIR"]) / document_id
    return {
        "directory": document_dir,
        "metadata": document_dir / "metadata.json",
        "extracted": document_dir / "extracted.txt",
        "invoice_data": document_dir / "invoice_data.json",
    }


def get_original_document_url(document_id):
    return url_for(
        "upload.original_document",
        document_id=document_id,
    )


def render_review_page(
    token,
    metadata,
    invoice_data=None,
    extracted_text="",
    error=None,
    status_code=200,
):
    timing = metadata.get("timing", {}) if isinstance(metadata, dict) else {}
    response = render_template(
        "upload.html",
        token=token,
        result=metadata,
        invoice_data=invoice_data,
        extracted_text=extracted_text,
        original_file_url=get_original_document_url(
            metadata["document_id"]
        ) if metadata and metadata.get("document_id") else None,
        upload_time=timing.get(
            "upload_time_seconds",
            session.get("upload_time"),
        ),
        extraction_time=timing.get("extraction_time_seconds"),
        invoice_time=timing.get("invoice_time_seconds"),
        processing_time=timing.get("processing_time_seconds"),
        validation=metadata.get("validation") if metadata else None,
        error=error,
    )
    return response if status_code == 200 else (response, status_code)


@upload_bp.route("/", methods=["GET", "POST"])
def upload_page():
    token = get_upload_token()

    if request.method == "GET":
        result = session.pop("upload_result", None)
        upload_time = (
            result.get("timing", {}).get("upload_time_seconds")
            if isinstance(result, dict)
            else session.get("upload_time")
        )
        return render_template(
            "upload.html",
            token=token,
            result=result,
            upload_time=upload_time,
        )

    if not is_valid_csrf_token(token):
        return render_upload_error(
            token,
            "Sesi formulir berubah. Pilih file dan coba lagi.",
            400,
        )

    upload_started = time.perf_counter()

    try:
        result = save_document(
            file=request.files.get("document"),
            upload_dir=Path(current_app.config["UPLOAD_DIR"]),
            s3_bucket=current_app.config["S3_BUCKET"],
            aws_region=current_app.config["AWS_REGION"],
            s3_prefix=current_app.config.get("S3_PREFIX", ""),
        )

        upload_time = round(time.perf_counter() - upload_started, 2)
        result["timing"] = {"upload_time_seconds": upload_time}

        metadata_path = (
            Path(current_app.config["UPLOAD_DIR"])
            / result["document_id"]
            / "metadata.json"
        )
        metadata_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        session["upload_time"] = upload_time
        session["upload_result"] = result
        return redirect(url_for("upload.upload_page"), code=303)

    except UploadError as error:
        return render_upload_error(token, str(error), 400)
    except OSError:
        current_app.logger.exception("Penyimpanan dokumen gagal")
        return render_upload_error(
            token,
            "Dokumen gagal disimpan. Periksa ruang dan izin folder.",
            500,
        )


@upload_bp.route("/<document_id>/original", methods=["GET"])
def original_document(document_id):
    paths = get_document_paths(document_id)

    if not paths["metadata"].is_file():
        abort(404)

    try:
        metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            abort(404)

        stored_filename = metadata.get("stored_filename")
        if (
            not stored_filename
            or stored_filename != Path(stored_filename).name
        ):
            abort(404)

        document_path = paths["directory"] / stored_filename
        if not document_path.is_file():
            abort(404)

        return send_file(
            document_path,
            as_attachment=False,
            download_name=metadata.get("original_filename", stored_filename),
        )
    except (OSError, json.JSONDecodeError, TypeError):
        current_app.logger.exception("Dokumen asli gagal dibaca")
        abort(500)


@upload_bp.route("/<document_id>/extract", methods=["POST"])
def extract_document(document_id):
    token = get_upload_token()

    if not is_valid_csrf_token(token):
        return render_upload_error(
            token,
            "Sesi formulir berubah. Coba lagi.",
            400,
        )

    try:
        paths = get_document_paths(document_id)
        if not paths["metadata"].is_file():
            return render_upload_error(
                token,
                "Dokumen tidak ditemukan.",
                404,
            )

        metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return render_upload_error(
                token,
                "Metadata dokumen tidak valid.",
                400,
            )

        document_type = metadata.get("document_type")
        stored_filename = metadata.get("stored_filename")
        if (
            document_type not in {"PDF", "IMAGE"}
            or not stored_filename
            or stored_filename != Path(stored_filename).name
        ):
            return render_review_page(
                token,
                metadata,
                error="Metadata dokumen tidak valid.",
                status_code=400,
            )

        document_path = paths["directory"] / stored_filename
        if not document_path.is_file():
            return render_review_page(
                token,
                metadata,
                error="File dokumen tidak ditemukan.",
                status_code=404,
            )

        processing_started = time.perf_counter()
        extraction_started = time.perf_counter()

        if document_type == "PDF":
            extraction = extract_pdf_text(document_path, paths["extracted"])

            if extraction["status"] == "OCR_REQUIRED":
                extraction = extract_document_with_bedrock(
                    document_path=document_path,
                    document_type="PDF",
                    output_path=paths["extracted"],
                    model_id=current_app.config["BEDROCK_MODEL_ID"],
                    aws_region=current_app.config["AWS_REGION"],
                )
            else:
                extraction["extraction_method"] = "PYMUPDF"
        else:
            extraction = extract_document_with_bedrock(
                document_path=document_path,
                document_type="IMAGE",
                output_path=paths["extracted"],
                model_id=current_app.config["BEDROCK_MODEL_ID"],
                aws_region=current_app.config["AWS_REGION"],
            )

        extraction_time = round(time.perf_counter() - extraction_started, 2)
        extracted_text = paths["extracted"].read_text(encoding="utf-8")

        metadata.update(
            {
                "ocr_status": extraction["status"],
                "extracted_filename": "extracted.txt",
                "extraction_method": extraction["extraction_method"],
                "status": "OCR_EXTRACTED",
            }
        )
        paths["metadata"].write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        invoice_started = time.perf_counter()
        invoice_data = extract_invoice_data_with_bedrock(
            extracted_text=extracted_text,
            model_id=current_app.config["BEDROCK_MODEL_ID"],
            aws_region=current_app.config["AWS_REGION"],
        )
        validation = validate_invoice_data(invoice_data)
        invoice_time = round(time.perf_counter() - invoice_started, 2)
        processing_time = round(time.perf_counter() - processing_started, 2)

        paths["invoice_data"].write_text(
            json.dumps(invoice_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        metadata["invoice_data_filename"] = "invoice_data.json"
        metadata["validation"] = validation
        metadata["status"] = (
            "READY_FOR_REVIEW" if validation["valid"] else "NEEDS_REVIEW"
        )
        metadata.setdefault("timing", {}).update(
            {
                "extraction_time_seconds": extraction_time,
                "invoice_time_seconds": invoice_time,
                "processing_time_seconds": processing_time,
            }
        )
        paths["metadata"].write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        return render_review_page(
            token,
            metadata,
            invoice_data=invoice_data,
            extracted_text=extracted_text,
        )

    except OcrError as error:
        current_app.logger.exception("Pemrosesan OCR atau Bedrock gagal")
        return render_upload_error(
            token,
            str(error),
            502,
            result=metadata if "metadata" in locals() else None,
        )
    except UploadError as error:
        return render_upload_error(
            token,
            str(error),
            400,
            result=metadata if "metadata" in locals() else None,
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        current_app.logger.exception("Ekstraksi dokumen gagal")
        return render_upload_error(
            token,
            "Dokumen atau metadata gagal dibaca/disimpan.",
            500,
            result=metadata if "metadata" in locals() else None,
        )


@upload_bp.route("/<document_id>/review", methods=["POST"])
def review_invoice(document_id):
    token = get_upload_token()

    if not is_valid_csrf_token(token):
        return render_upload_error(
            token,
            "Sesi formulir berubah. Coba lagi.",
            400,
        )

    if not DOCUMENT_ID_PATTERN.fullmatch(document_id):
        return render_upload_error(token, "ID dokumen tidak valid.", 400)

    review_action = request.form.get("review_action")
    if review_action not in {"save", "approve"}:
        return render_upload_error(token, "Aksi review tidak valid.", 400)

    try:
        paths = get_document_paths(document_id)
        if not paths["metadata"].is_file() or not paths["invoice_data"].is_file():
            return render_upload_error(
                token,
                "Data invoice tidak ditemukan. Ekstrak dokumen terlebih dahulu.",
                404,
            )

        metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
        invoice_data = json.loads(
            paths["invoice_data"].read_text(encoding="utf-8")
        )

        if not isinstance(metadata, dict) or not isinstance(invoice_data, dict):
            return render_upload_error(
                token,
                "Metadata atau data invoice tidak valid.",
                400,
            )

        if metadata.get("status") == "APPROVED":
            return render_review_page(
                token,
                metadata,
                invoice_data=invoice_data,
                extracted_text=(
                    paths["extracted"].read_text(encoding="utf-8")
                    if paths["extracted"].is_file()
                    else ""
                ),
                error="Invoice sudah disetujui dan tidak dapat diedit.",
                status_code=409,
            )

        for field in EDITABLE_INVOICE_FIELDS:
            value = request.form.get(field, "").strip()
            invoice_data[field] = value or None

        submitted_items = {}
        for field_name, value in request.form.items():
            match = LINE_ITEM_PATTERN.fullmatch(field_name)
            if match:
                index = int(match.group(1))
                item_field = match.group(2)
                submitted_items.setdefault(index, {})[item_field] = (
                    value.strip() or None
                )

        if "line_items_submitted" in request.form or submitted_items:
            existing_items = invoice_data.get("line_items", [])
            if not isinstance(existing_items, list):
                existing_items = []

            reviewed_items = []
            for index in sorted(submitted_items):
                item = submitted_items[index]
                existing_item = (
                    existing_items[index]
                    if index < len(existing_items)
                    and isinstance(existing_items[index], dict)
                    else {}
                )
                reviewed_items.append(
                    {
                        "line_number": existing_item.get("line_number")
                        or str(index + 1),
                        "description": item.get("description"),
                        "quantity": item.get("quantity"),
                        "unit_price": item.get("unit_price"),
                        "line_total": item.get("line_total"),
                    }
                )
            invoice_data["line_items"] = reviewed_items

        validation = validate_invoice_data(invoice_data)

        paths["invoice_data"].write_text(
            json.dumps(invoice_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        metadata["invoice_data_filename"] = "invoice_data.json"
        metadata["validation"] = validation
        metadata["status"] = (
            "APPROVED"
            if review_action == "approve"
            else ("READY_FOR_REVIEW" if validation["valid"] else "NEEDS_REVIEW")
        )
        paths["metadata"].write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        extracted_text = (
            paths["extracted"].read_text(encoding="utf-8")
            if paths["extracted"].is_file()
            else ""
        )
        return render_review_page(
            token,
            metadata,
            invoice_data=invoice_data,
            extracted_text=extracted_text,
        )

    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        current_app.logger.exception("Review invoice gagal disimpan")
        return render_upload_error(
            token,
            "Data review gagal dibaca atau disimpan.",
            500,
        )


def prepare_voucher_pdf(document_id):
    paths = get_document_paths(document_id)

    if not paths["metadata"].is_file() or not paths["invoice_data"].is_file():
        abort(404)

    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    invoice_data = json.loads(
        paths["invoice_data"].read_text(encoding="utf-8")
    )

    if not isinstance(metadata, dict) or not isinstance(invoice_data, dict):
        abort(400)
    if metadata.get("status") != "APPROVED":
        abort(409)

    voucher_number = metadata.get("voucher_number")
    if not voucher_number:
        voucher_number = f"VCH-{document_id[:8].upper()}"
        metadata["voucher_number"] = voucher_number
        paths["metadata"].write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    pdf_path = paths["directory"] / "voucher.pdf"
    generate_voucher_pdf(
        invoice_data=invoice_data,
        output_path=pdf_path,
        voucher_number=voucher_number,
        requester_name=None,
        approver_name=None,
    )

    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", voucher_number)
    return pdf_path, safe_filename


@upload_bp.route("/<document_id>/voucher/preview", methods=["GET"])
def preview_voucher(document_id):
    try:
        _, voucher_filename = prepare_voucher_pdf(document_id)
        return render_template(
            "voucher_preview.html",
            document_id=document_id,
            voucher_filename=voucher_filename,
            token=get_upload_token(),
        )
    except (OSError, json.JSONDecodeError, TypeError):
        current_app.logger.exception("Preview voucher gagal dibuat")
        return render_upload_error(
            get_upload_token(),
            "Preview voucher gagal dibuat.",
            500,
        )
    except Exception:
        current_app.logger.exception("Preview voucher gagal dibuat")
        return render_upload_error(
            get_upload_token(),
            "Preview voucher gagal dibuat.",
            500,
        )


@upload_bp.route("/<document_id>/voucher/preview.pdf", methods=["GET"])
def voucher_preview_pdf(document_id):
    try:
        pdf_path, voucher_filename = prepare_voucher_pdf(document_id)
        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=f"{voucher_filename}.pdf",
        )
    except (OSError, json.JSONDecodeError, TypeError):
        current_app.logger.exception("PDF preview voucher gagal dibuat")
        abort(500)
    except Exception:
        current_app.logger.exception("PDF preview voucher gagal dibuat")
        abort(500)


@upload_bp.route("/<document_id>/voucher/generate", methods=["POST"])
def generate_voucher(document_id):
    token = get_upload_token()

    if not is_valid_csrf_token(token):
        return render_upload_error(
            token,
            "Sesi formulir berubah. Coba lagi.",
            400,
        )

    try:
        pdf_path, voucher_filename = prepare_voucher_pdf(document_id)
        return send_file(
            pdf_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{voucher_filename}.pdf",
        )
    except (OSError, json.JSONDecodeError, TypeError):
        current_app.logger.exception("Unduhan voucher gagal")
        return render_upload_error(
            token,
            "Voucher gagal dibuat. Coba lagi.",
            500,
        )
    except Exception:
        current_app.logger.exception("Unduhan voucher gagal")
        return render_upload_error(
            token,
            "Voucher gagal dibuat. Coba lagi.",
            500,
        )
