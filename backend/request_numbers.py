"""Immutable human request codes alongside stable legacy UUID relationships."""
import re
import unicodedata
from sqlalchemy import select
from .models import Setting, CompanyNumber, RequestNumber, Client, WorkRequest


def assign_request_number(db, req):
    existing = db.get(RequestNumber, req.id)
    if existing:
        return existing
    # Serialize allocations with a permanent counter, including first allocation.
    if db.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(Setting).values(key='request_company_counter', value='0').on_conflict_do_nothing(index_elements=['key']))
    counter = db.scalar(select(Setting).where(Setting.key == 'request_company_counter').with_for_update().execution_options(populate_existing=True))
    # A concurrent allocator may have completed while this transaction waited.
    existing = db.get(RequestNumber, req.id, populate_existing=True)
    if existing:
        return existing
    company = db.get(CompanyNumber, req.client_id, populate_existing=True)
    if not company:
        counter.value = str(int(counter.value) + 1)
        company = CompanyNumber(client_id=req.client_id, number=int(counter.value), next_request=1)
        db.add(company)
    name = unicodedata.normalize('NFKD', db.get(Client, req.client_id).name).encode('ascii','ignore').decode()
    slug = re.sub(r'[^A-Z0-9]+', '-', name.upper()).strip('-')[:70].rstrip('-') or 'PERUSAHAAN'
    number = company.next_request
    company.next_request += 1
    row = RequestNumber(request_id=req.id, client_id=req.client_id, sequence=number,
        code=f"REQ-{req.request_date.replace('-', '')}-{company.number:04d}-{slug}-{number:04d}")
    db.add(row)
    db.flush()
    return row


def backfill_request_numbers(db):
    missing = list(db.scalars(select(WorkRequest).outerjoin(RequestNumber, RequestNumber.request_id == WorkRequest.id)
        .where(RequestNumber.request_id.is_(None)).order_by(WorkRequest.request_date, WorkRequest.id)))
    for req in missing:
        assign_request_number(db, req)
