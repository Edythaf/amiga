"""Immutable manual PDF revisions. Signature detection is advisory, not identity verification."""
from sqlalchemy import select
from .models import ManualReviewPDF


def latest_manual(db,inv):
    return db.scalar(select(ManualReviewPDF).where(ManualReviewPDF.invoice_id==inv.id,ManualReviewPDF.version==inv.current_version).order_by(ManualReviewPDF.created_at.desc(),ManualReviewPDF.id.desc()).limit(1))


def manual_dto(row):
    return {'id':row.id,'filename':row.filename,'version':row.version,'sha256':row.sha256,'uploaded_by':row.uploaded_by,
            'created_at':row.created_at,'signature_state':row.signature_state,'signature_result':row.signature_result} if row else None
