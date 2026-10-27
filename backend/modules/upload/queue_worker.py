"""Primary ZIP document pipeline + integrated durable, versioned queue.

OCR/document operations come from the supplied service.py. Lease/fencing and
transactional publication retain the portal guarantees. No global PROCESSING
reset is run on startup and no second worker/database is created.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json
import threading
from pathlib import Path
from sqlalchemy import select, or_, and_, text
from ...models import WorkRequest, Document, Extraction, Invoice, now, uid, HEADER_FIELDS
from ...repository import write_version, audit
from ...validation import normalize, InvalidDraft
from .queue_store import claim_next_document as claim


def real_extractor(path, config):
    from .portal_adapter import extract_for_portal
    return extract_for_portal(path, config)


def process_one(app, request_id=None):
    job = claim(app, request_id)
    if job is None:
        return False
    req_id, token, doc_id, key = job
    raw = None
    new_files=[]
    try:
        extractor = app.config.get('EXTRACTOR') or real_extractor
        raw = extractor(Path(app.config['UPLOAD_DIR']) / key, app.config)
        rows = raw.get('invoices') if isinstance(raw, dict) else None
        if not isinstance(rows, list) or not rows or len(rows) > 100:
            raise InvalidDraft('Jumlah invoice tidak valid.')
        normalized = [normalize(row) for row in rows]  # All or none, never silently omit an invoice.
        with app.extensions['amiga_db']() as db:
            if db.bind.dialect.name == 'sqlite':
                db.execute(text('BEGIN IMMEDIATE'))
            req = db.scalar(select(WorkRequest).where(WorkRequest.id == req_id).with_for_update())
            if req.job_token != token or req.processing_status != 'PROCESSING':
                return True
            from ...batch_intake import targets
            for target,target_doc,target_rows in targets(db,req,doc_id,normalized,app.config['UPLOAD_DIR'],new_files):
                extraction = Extraction(id=uid('ext'), request_id=target.id, document_id=target_doc, created_at=now(), payload=raw)
                db.add(extraction)
                db.flush()
                # Re-extraction creates a new generation, retaining historical invoices/reviews.
                for previous in db.scalars(select(Invoice).where(Invoice.request_id == target.id, Invoice.active == 1)):
                    previous.active = 0
                offset = db.scalar(select(__import__('sqlalchemy').func.max(Invoice.index)).where(Invoice.request_id == target.id))
                for index, fields in enumerate(target_rows, start=(offset + 1 if offset is not None else 0)):
                    invoice = Invoice(id=uid('inv'), request_id=target.id, extraction_id=extraction.id,
                                      index=index, current_version=1, active=1)
                    db.add(invoice)
                    db.flush()
                    sources = {key: {'document_id': target_doc, 'source_type': 'EXTRACTED', 'page': None, 'notes': None}
                               for key in HEADER_FIELDS if fields.get(key) is not None}
                    write_version(db, invoice, fields, sources, None, 'Ekstraksi dokumen', None)
                target.processing_status, target.stage, target.error_code = 'COMPLETE', 'Menunggu review manusia', None
                target.job_token, target.lease_until, target.updated_at = None, None, now()
                audit(db, 'EXTRACTION_COMPLETED', request_id=target.id,
                      changes=[{'field': 'invoice_count', 'before': None, 'after': len(target_rows)}])
            db.commit()
    except Exception as exc:
        for path in new_files:path.unlink(missing_ok=True)
        app.logger.warning('Extraction failed for %s (%s)', req_id, type(exc).__name__)
        allowed_codes = {'EXTRACTION_NOT_CONFIGURED', 'EXTRACTION_TRUNCATED', 'EXTRACTION_INVALID_PDF',
                         'EXTRACTION_INVALID_OUTPUT', 'EXTRACTION_REFUSED', 'OPENAI_AUTH_FAILED',
                         'OPENAI_ACCESS_DENIED', 'OPENAI_MODEL_UNAVAILABLE', 'OPENAI_QUOTA_LIMIT', 'OPENAI_UNAVAILABLE',
                         'BEDROCK_AUTH_FAILED', 'BEDROCK_ACCESS_DENIED', 'BEDROCK_QUOTA_LIMIT',
                         'BEDROCK_MODEL_UNAVAILABLE', 'BEDROCK_INVALID_REQUEST', 'BEDROCK_UNAVAILABLE', 'SPLIT_TARGET_AMBIGUOUS'}
        code = str(exc) if str(exc) in allowed_codes else 'EXTRACTION_FAILED'
        with app.extensions['amiga_db']() as db:
            req = db.scalar(select(WorkRequest).where(WorkRequest.id == req_id).with_for_update())
            if req and req.job_token == token:
                # Even malformed extraction remains inspectable by the operator.
                # Source corrections never replace the original model output.
                if isinstance(raw, dict):
                    db.add(Extraction(id=uid('ext'), request_id=req.id, document_id=doc_id,
                                      created_at=now(), payload=raw))
                req.processing_status, req.stage, req.error_code = 'FAILED', 'Ekstraksi gagal; periksa konfigurasi atau dokumen', code
                req.job_token, req.lease_until, req.updated_at = None, None, now()
                audit(db, code, request_id=req.id)
                db.commit()
    return True


def start_worker(app):
    stop = threading.Event()
    def run():
        from ...initial_analysis import process_initial_one
        from ...telegram_automatic import process_automatic_one
        while not stop.is_set():
            try:
                sent=process_automatic_one(app)
                if process_one(app) or process_initial_one(app) or sent:
                    continue
            except Exception:
                app.logger.exception('Queue worker failed')
            stop.wait(2)
    worker = threading.Thread(target=run, name='amiga-queue', daemon=True)
    worker.start()
    app.extensions['amiga_worker_stop'] = stop
    return worker
