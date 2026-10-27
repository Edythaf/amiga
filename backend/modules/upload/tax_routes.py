from sqlalchemy import select,func,text
from decimal import Decimal
from ...api_common import (api,g,body,ok,fail,mutation_invoice,require_review,latest_review,fields_for,
    current_app,authenticate,audit,now,datetime,timezone,timedelta,Path)
from ...models import InvoiceTaxPlan,Client
from ...workflow import input_hash,source_document
from ...voucher_tax import FIELDS,CATALOG,defaults,normalize_plan,calculate_tax,plan_dto
from ...tax_analysis import analyze_tax,validate_tax_analysis
from ...validation import InvalidDraft


def writable(req,inv):
    require_review(req)
    review=latest_review(g.db,inv)
    if review and review.decision in ('APPROVED','REJECTED'):fail(409,'TAX_REVISION_REQUIRED','Buat revisi invoice sebelum mengubah pajak voucher yang sudah diputuskan.')


@api.patch('/requests/<request_id>/invoices/<invoice_id>/voucher-tax')
def save_tax(request_id,invoice_id):
    data=body();req,inv=mutation_invoice(request_id,invoice_id,data);writable(req,inv)
    return ok(save_tax_plan(req,inv,data))


def save_tax_plan(req,inv,data):
    row=g.db.get(InvoiceTaxPlan,(inv.id,inv.current_version));revision=row.revision if row else 0
    if type(data.get('expected_tax_revision')) is not int or data['expected_tax_revision']!=revision:fail(409,'TAX_CHANGED','Pajak voucher berubah. Muat ulang.')
    if data.get('acknowledged') is not True:fail(422,'TAX_CONFIRMATION_REQUIRED','Konfirmasikan jenis, tarif, dasar dan pajak yang sudah tercatat.')
    try:plan=normalize_plan(data.get('plan'));calculate_tax(fields_for(g.db,inv),plan)
    except InvalidDraft as exc:fail(422,'INVALID_VOUCHER_TAX',str(exc))
    if row and row.revision and all(getattr(row,key)==plan[key] for key in FIELDS):return plan_dto(g.db,inv,fields_for(g.db,inv))
    before={key:getattr(row,key) for key in FIELDS} if row else None
    if not row:row=InvoiceTaxPlan(invoice_id=inv.id,version=inv.current_version);g.db.add(row)
    for key,value in plan.items():setattr(row,key,value)
    row.revision=revision+1;row.edited_at=now();row.edited_by=g.actor.id;req.updated_at=now()
    audit(g.db,'VOUCHER_TAX_UPDATED',g.actor.id,req.id,inv.id,reason=plan['note'],changes=[{'field':'voucher_tax','before':before,'after':plan}])
    g.db.flush();return plan_dto(g.db,inv,fields_for(g.db,inv))


@api.patch('/requests/<request_id>/invoices/<invoice_id>/review-draft')
def save_review_draft(request_id,invoice_id):
    """One request lock and one transaction for invoice fields + their tax plan."""
    from .routes import save_invoice_draft
    from ...api_common import invoice_dto
    data=body();req,inv=mutation_invoice(request_id,invoice_id,data);writable(req,inv)
    old=g.db.get(InvoiceTaxPlan,(inv.id,inv.current_version));revision=old.revision if old else 0
    if type(data.get('expected_tax_revision')) is not int or data['expected_tax_revision']!=revision:
        fail(409,'TAX_CHANGED','Pajak voucher berubah. Muat ulang.')
    if data.get('acknowledged') is not True:fail(422,'TAX_CONFIRMATION_REQUIRED','Konfirmasikan pemeriksaan data dan pajak.')
    changed=False
    if data.get('invoice') is not None:
        if not isinstance(data['invoice'],dict):fail(422,'INVALID_DRAFT','Data invoice harus objek.')
        result=save_invoice_draft(req,inv,data['invoice']);changed=result['revision_created']
    tax=save_tax_plan(req,inv,{**data,'expected_tax_revision':0 if changed else revision})
    return ok({'invoice':invoice_dto(req,inv),'voucher_tax':tax,'revision_created':changed})


@api.post('/requests/<request_id>/invoices/<invoice_id>/voucher-tax/analyze')
def suggest_tax(request_id,invoice_id):
    data=body();req,inv=mutation_invoice(request_id,invoice_id,data);writable(req,inv)
    row=g.db.get(InvoiceTaxPlan,(inv.id,inv.current_version))
    fingerprint=input_hash(g.db,req,inv)
    if row and row.ai_state=='READY' and row.ai_input_hash==fingerprint:return ok(plan_dto(g.db,inv,fields_for(g.db,inv)))
    lease=(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat(timespec='microseconds').replace('+00:00','Z')
    if row and row.ai_state=='RUNNING' and row.ai_started_at and row.ai_started_at>lease:return ok(plan_dto(g.db,inv,fields_for(g.db,inv)))
    since=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='microseconds').replace('+00:00','Z')
    used=g.db.scalar(select(func.sum(InvoiceTaxPlan.ai_attempts)).where(InvoiceTaxPlan.edited_by==g.actor.id,InvoiceTaxPlan.ai_started_at>=since)) or 0
    if (row and row.ai_attempts>=2) or used>=10:fail(429,'TAX_AI_LIMIT','Batas analisis pajak tercapai. Reviewer tetap bisa mengisi pajak secara manual.')
    fields=fields_for(g.db,inv)
    if not row:row=InvoiceTaxPlan(invoice_id=inv.id,version=inv.current_version,**defaults(fields));g.db.add(row);g.db.flush()
    row.ai_state='RUNNING';row.ai_attempts+=1;row.ai_started_at=now();row.ai_input_hash=fingerprint
    if not row.edited_by:row.edited_by=g.actor.id
    attempt=row.ai_attempts;fingerprint=input_hash(g.db,req,inv)
    source=source_document(g.db,req)
    pdf=(Path(current_app.config['UPLOAD_DIR'])/source.storage_key).read_bytes()
    context={'fields':fields,'invoice_version':inv.current_version,'company_name':g.db.get(Client,req.client_id).name}
    g.db.commit()
    try:
        analyzer=current_app.config.get('TAX_ANALYZER') or analyze_tax
        result=validate_tax_analysis(analyzer(context,pdf,current_app.config));state='READY'
    except Exception:
        result={'note':'AI belum dapat mengusulkan pajak. Isi manual atau coba ulang. Tidak ada pajak tambahan diterapkan otomatis.'};state='FAILED'
    if current_app.extensions['amiga_engine'].dialect.name=='sqlite':g.db.execute(text('BEGIN IMMEDIATE'))
    g.db.expire_all();authenticate();req,inv=mutation_invoice(request_id,invoice_id,data);writable(req,inv)
    row=g.db.get(InvoiceTaxPlan,(inv.id,inv.current_version))
    if not row or row.ai_attempts!=attempt or fingerprint!=input_hash(g.db,req,inv):fail(409,'TAX_CONTEXT_CHANGED','Dokumen atau data berubah saat analisis pajak. Muat ulang.')
    row.ai_state=state;row.ai_result=result
    if state=='READY' and row.revision==0:
        source_vat=calculate_tax(fields,defaults(fields))['source_vat'] if fields.get('total_amount') is not None else '0'
        vat=CATALOG.get(result['vat_rule']);pph=CATALOG.get(result['withholding_rule'])
        row.vat_rate=vat[1] if vat else '0';row.vat_base=result['vat_base']
        row.withholding_rate=pph[1] if pph else '0';row.withholding_base=result['withholding_base'];row.withholding_kind=pph[0] if pph else 'PPh'
        row.source_withholding=result['source_withholding'] if result['withholding_in_total'] else '0'
        # A missing fact yields an advisory proposal only, never a guessed payable adjustment.
        complete=not result['missing_facts']
        row.vat_mode='ADD' if vat and complete and Decimal(source_vat)==0 else 'KEEP'
        row.withholding_mode='DEDUCT' if pph and complete and not result['withholding_in_total'] else 'KEEP'
        row.note=result['note']
    audit(g.db,'VOUCHER_TAX_AI_'+state,g.actor.id,req.id,inv.id,reason='Advisory tax proposal; invoice source and approval unchanged')
    return ok(plan_dto(g.db,inv,fields_for(g.db,inv)))
