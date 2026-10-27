from sqlalchemy import select
from .models import (InvoiceVersion, LineItem, FieldSource, Review, Role, Membership,
                     Audit, InvoiceAssistance, HEADER_FIELDS, ITEM_FIELDS, now, uid)


def roles(db, user):
    return set(db.scalars(select(Role.role).where(Role.user_id == user.id)))


def client_ids(db, user):
    return set(db.scalars(select(Membership.client_id).where(Membership.user_id == user.id)))


def fields_for(db, invoice, version=None):
    version = version or invoice.current_version
    head = db.get(InvoiceVersion, (invoice.id, version))
    if head is None:
        return None
    fields = {key: getattr(head, key) for key in HEADER_FIELDS}
    fields['line_items'] = [{key: getattr(row, key) for key in ITEM_FIELDS} for row in db.scalars(
        select(LineItem).where(LineItem.invoice_id == invoice.id, LineItem.version == version).order_by(LineItem.index))]
    return fields


def sources_for(db, invoice, version=None):
    return {row.field: {'document_id': row.document_id, 'source_type': row.source_type,
                        'page': row.page, 'notes': row.notes} for row in db.scalars(select(FieldSource).where(
                            FieldSource.invoice_id == invoice.id, FieldSource.version == (version or invoice.current_version)))}


def write_version(db, invoice, fields, sources, actor_id, reason, expected_count):
    """Append only: callers hold the request row lock. No revision is overwritten."""
    version = invoice.current_version
    db.add(InvoiceVersion(invoice_id=invoice.id, version=version, created_by=actor_id,
                          created_at=now(), reason=reason, expected_item_count=expected_count,
                          **{key: fields[key] for key in HEADER_FIELDS}))
    db.flush()
    for index, row in enumerate(fields['line_items']):
        db.add(LineItem(invoice_id=invoice.id, version=version, index=index, **row))
    for field, source in sources.items():
        if source:
            db.add(FieldSource(invoice_id=invoice.id, version=version, field=field, **source))
    db.add(InvoiceAssistance(invoice_id=invoice.id,version=version,state='PENDING'))
    db.flush()


def latest_review(db, invoice):
    return db.scalar(select(Review).where(Review.invoice_id == invoice.id, Review.version == invoice.current_version)
                     .order_by(Review.created_at.desc(), Review.id.desc()).limit(1))


def audit(db, action, actor_id=None, request_id=None, invoice_id=None, reason=None, changes=None):
    db.add(Audit(id=uid('evt'), request_id=request_id, invoice_id=invoice_id,
                 actor_id=actor_id, action=action, at=now(), reason=reason, changes=changes or []))
