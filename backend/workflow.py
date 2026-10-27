"""Version-bound uploader checks. Shared by queue, DTOs and every review action."""
from hashlib import sha256
import json
from sqlalchemy import select
from .models import (Document, Invoice, InvoiceAssistance, UploaderConfirmation, RequestSource, Review, now)
from .repository import fields_for, sources_for


def source_document(db,req):
    pointer=db.get(RequestSource,req.id)
    return db.get(Document,pointer.document_id) if pointer else db.scalar(select(Document).where(
        Document.request_id==req.id,Document.type=='INVOICE').order_by(Document.uploaded_at,Document.id).limit(1))


def active_invoices(db,req):
    return list(db.scalars(select(Invoice).where(Invoice.request_id==req.id,Invoice.active==1).order_by(Invoice.index)))


def input_hash(db,req,inv):
    docs=[(d.id,d.sha256) for d in db.scalars(select(Document).where(Document.request_id==req.id).order_by(Document.id))]
    value={'fields':fields_for(db,inv),'sources':sources_for(db,inv),'documents':docs,'version':inv.current_version}
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def assistance_dto(db,req,inv):
    row=db.get(InvoiceAssistance,(inv.id,inv.current_version))
    fingerprint=input_hash(db,req,inv)
    fresh=row and row.input_hash==fingerprint
    return {'state':row.state if fresh or row and row.state=='PENDING' else 'PENDING',
            'result':row.result if fresh and row.state=='READY' else None,
            'error_code':row.error_code if fresh else None,'model':row.model if row else None,
            'updated_at':row.updated_at if row else None}


def confirmation_dto(db,req,inv):
    row=db.get(UploaderConfirmation,(inv.id,inv.current_version,input_hash(db,req,inv)))
    if row and row.item_count!=len(fields_for(db,inv)['line_items']):row=None
    return {'confirmed':bool(row),'actor_id':row.actor_id if row else None,
            'confirmed_at':row.confirmed_at if row else None,'version':inv.current_version,'item_count':row.item_count if row else None}


def ready_for_review(db,req):
    rows=active_invoices(db,req)
    def checked(inv):
        published=db.scalar(select(Review.id).where(Review.invoice_id==inv.id,Review.version==inv.current_version,Review.decision=='APPROVED').limit(1))
        return bool(published) or confirmation_dto(db,req,inv)['confirmed']
    return req.processing_status=='COMPLETE' and bool(rows) and all(checked(inv) for inv in rows)


def invalidate_assistance(db,req):
    for inv in active_invoices(db,req):
        row=db.get(InvoiceAssistance,(inv.id,inv.current_version))
        if row:
            row.state,row.result,row.job_token,row.lease_until='PENDING',None,None,None
            row.input_hash,row.error_code,row.attempts,row.updated_at=None,None,0,now()
        else:
            db.add(InvoiceAssistance(invoice_id=inv.id,version=inv.current_version,state='PENDING'))
