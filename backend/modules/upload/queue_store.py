"""Primary source queue store, adapted to the shared versioned schema.

One database serves the supplied backend and portal. Claiming is atomic on both
SQLite and PostgreSQL; startup never resets another worker's PROCESSING job.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, or_, and_, text
from ...models import WorkRequest, Document, now, uid
from ...workflow import source_document


def claim_next_document(app, request_id=None):
    with app.extensions['amiga_db']() as db:
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        query = select(WorkRequest).where(or_(WorkRequest.processing_status == 'QUEUED',
            and_(WorkRequest.processing_status == 'PROCESSING', WorkRequest.lease_until < now())))
        if request_id:
            query = query.where(WorkRequest.id == request_id)
        req = db.scalar(query.order_by(WorkRequest.updated_at, WorkRequest.id).with_for_update(skip_locked=True).limit(1))
        if not req:
            return None
        req.processing_status, req.stage = 'PROCESSING', 'Ekstraksi dokumen'
        req.job_token = uid('job')
        req.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec='seconds').replace('+00:00', 'Z')
        req.updated_at = now()
        doc = source_document(db,req)
        job = (req.id, req.job_token, doc.id, doc.storage_key)
        db.commit()
        return job


