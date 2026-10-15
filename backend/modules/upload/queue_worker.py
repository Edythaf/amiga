"""Single-worker FIFO processor started by the Flask application factory."""

import json
import threading
import time
from pathlib import Path

from .queue_store import (
    claim_next_document,
    initialize_queue,
    save_invoice_records,
    update_queue_item,
)
from .service import (
    OcrError,
    UploadError,
    extract_document_with_bedrock,
    extract_invoice_data_with_bedrock,
    extract_pdf_text,
    validate_invoice_data,
)


def _write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _set_stage(app, document_id, stage, step):
    update_queue_item(
        app.config["DATABASE_URL"], document_id,
        status="PROCESSING", stage=stage, stage_step=step,
    )


def process_one_document(app, document_id):
    """Run extraction and validation, preserving results in each document folder."""
    db_path = app.config["DATABASE_URL"]
    upload_dir = Path(app.config["UPLOAD_DIR"])
    document_dir = upload_dir / document_id
    metadata_path = document_dir / "metadata.json"
    extracted_path = document_dir / "extracted.txt"
    invoice_path = document_dir / "invoice_data.json"

    metadata = {}
    current_step = 0
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        stored_filename = metadata.get("stored_filename")
        if not stored_filename or stored_filename != Path(stored_filename).name:
            raise UploadError("Metadata dokumen tidak valid.")
        document_path = document_dir / stored_filename
        if not document_path.is_file():
            raise UploadError("File dokumen tidak ditemukan.")

        current_step = 1
        _set_stage(app, document_id, "Membaca teks / OCR dokumen", 1)
        started = time.perf_counter()
        extraction_started = time.perf_counter()
        document_type = metadata.get("document_type")
        if document_type == "PDF":
            extraction = extract_pdf_text(document_path, extracted_path)
            if extraction["status"] == "OCR_REQUIRED":
                extraction = extract_document_with_bedrock(
                    document_path=document_path,
                    document_type="PDF",
                    output_path=extracted_path,
                    model_id=app.config["BEDROCK_MODEL_ID"],
                    aws_region=app.config["AWS_REGION"],
                )
            else:
                extraction["extraction_method"] = "PYMUPDF"
        elif document_type == "IMAGE":
            extraction = extract_document_with_bedrock(
                document_path=document_path,
                document_type="IMAGE",
                output_path=extracted_path,
                model_id=app.config["BEDROCK_MODEL_ID"],
                aws_region=app.config["AWS_REGION"],
            )
        else:
            raise UploadError("Jenis dokumen tidak didukung.")

        extraction_time = round(time.perf_counter() - extraction_started, 2)
        extracted_text = extracted_path.read_text(encoding="utf-8")
        metadata.update({
            "status": "PROCESSING",
            "ocr_status": extraction.get("status"),
            "extracted_filename": "extracted.txt",
            "extraction_method": extraction.get("extraction_method"),
        })
        _write_json(metadata_path, metadata)

        current_step = 2
        _set_stage(app, document_id, "Mengekstrak data invoice", 2)
        invoice_started = time.perf_counter()
        invoice_result = extract_invoice_data_with_bedrock(
            extracted_text=extracted_text,
            model_id=app.config["BEDROCK_MODEL_ID"],
            aws_region=app.config["AWS_REGION"],
        )
        invoices = invoice_result.get("invoices", [])
        if not invoices:
            raise OcrError("Tidak ada invoice yang ditemukan dalam dokumen.")

        current_step = 3
        _set_stage(app, document_id, "Memvalidasi hasil ekstraksi", 3)
        validations = [validate_invoice_data(invoice) for invoice in invoices]
        validation = {
            "valid": all(item["valid"] for item in validations),
            "issues": [
                f"Invoice {index + 1}: {issue}"
                for index, item in enumerate(validations)
                for issue in item["issues"]
            ],
        }
        invoice_time = round(time.perf_counter() - invoice_started, 2)
        processing_time = round(time.perf_counter() - started, 2)
        invoice_records = [
            {
                "data": invoice,
                "validation": validations[index],
                "status": "READY_FOR_REVIEW" if validations[index]["valid"] else "NEEDS_REVIEW",
                "previewed": False,
            }
            for index, invoice in enumerate(invoices)
        ]
        save_invoice_records(db_path, document_id, invoice_records)
        
        _write_json(invoice_path, {"invoices": invoice_records})
        metadata["invoice_data_filename"] = "invoice_data.json"
        metadata["invoice_count"] = len(invoices)
        metadata["validation"] = validation
        metadata["status"] = "READY_FOR_REVIEW" if validation.get("valid") else "EXCEPTION"
        metadata.setdefault("timing", {}).update({
            "extraction_time_seconds": extraction_time,
            "invoice_time_seconds": invoice_time,
            "processing_time_seconds": processing_time,
        })
        _write_json(metadata_path, metadata)
        update_queue_item(
            db_path, document_id,
            status=metadata["status"],
            stage=("Siap untuk Human Review" if validation.get("valid") else "Perlu penanganan exception"),
            stage_step=3,
            error_message=None if validation.get("valid") else "; ".join(validation.get("issues", [])),
        )
    except Exception as error:
        app.logger.exception("Queue processing gagal untuk %s", document_id)
        metadata["status"] = "EXCEPTION"
        metadata["processing_error"] = str(error)
        try:
            _write_json(metadata_path, metadata)
        except OSError:
            app.logger.exception("Metadata exception gagal disimpan untuk %s", document_id)
        failed_step = max(current_step, 1)
        failed_stage = {
            1: "Gagal membaca dokumen",
            2: "Gagal mengekstrak data invoice",
            3: "Gagal memvalidasi data",
        }[failed_step]
        update_queue_item(
            db_path, document_id,
            status="EXCEPTION", stage=failed_stage, stage_step=failed_step,
            error_message=str(error),
        )


def _worker_loop(app, stop_event):
    while not stop_event.is_set():
        item = claim_next_document(app.config["DATABASE_URL"])
        if item is None:
            stop_event.wait(1.0)
            continue
        try:
            with app.app_context():
                process_one_document(app, item["document_id"])
        except Exception as error:
            app.logger.exception("Worker antrean mengalami kesalahan")
            try:
                update_queue_item(
                    app.config["DATABASE_URL"], item["document_id"],
                    status="EXCEPTION", stage="Gagal diproses", stage_step=3,
                    error_message=str(error),
                )
            except Exception:
                app.logger.exception("Status exception gagal disimpan")


def start_queue_worker(app):
    """Initialize the durable queue and start one FIFO worker for this app process."""
    initialize_queue(app.config["DATABASE_URL"])
    if app.extensions.get("amiga_queue_worker"):
        return
    stop_event = threading.Event()
    worker = threading.Thread(
        target=_worker_loop,
        args=(app, stop_event),
        name="amiga-fifo-worker",
        daemon=True,
    )
    app.extensions["amiga_queue_worker"] = {"thread": worker, "stop": stop_event}
    worker.start()
