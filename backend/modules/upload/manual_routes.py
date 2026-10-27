from datetime import datetime,timezone,timedelta
from hashlib import sha256
from io import BytesIO
from sqlalchemy import select,func
from ...api_common import (api,g,current_app,body,request,ok,fail,scoped_request,scoped_invoice,mutation_invoice,
    require_review,require_open,read_upload,latest_review,audit,uid,now,authenticate,send_file)
from ...models import ManualReviewPDF
from ...manual_pdf import latest_manual,manual_dto
from ...signature_analysis import inspect_signature,validate_signature


def editable_manual(req,inv):
    require_review(req)
    if latest_review(g.db,inv) and latest_review(g.db,inv).decision in ('APPROVED','REJECTED'):
        fail(409,'REVIEW_REVISION_REQUIRED','Buat revisi invoice sebelum mengganti PDF hasil yang sudah diputuskan.')


@api.post('/requests/<request_id>/invoices/<invoice_id>/manual-pdf')
def upload_manual(request_id,invoice_id):
    try:version=int(request.form.get('expected_version',''))
    except ValueError:fail(422,'VERSION_REQUIRED','Kirim versi invoice yang ditampilkan.')
    req,inv=mutation_invoice(request_id,invoice_id,{'expected_version':version});editable_manual(req,inv)
    previous=latest_manual(g.db,inv)
    if request.form.get('expected_previous_id','')!=(previous.id if previous else ''):fail(409,'MANUAL_PDF_CHANGED','PDF manual berubah. Muat ulang sebelum mengunggah.')
    if request.form.get('content_confirmed')!='true':fail(422,'MANUAL_CONTENT_CONFIRMATION','Konfirmasikan PDF sebagai voucher hasil akhir revisi reviewer untuk invoice ini.')
    checked=read_upload(request.files.get('review_pdf'))
    row=ManualReviewPDF(id=uid('manual'),invoice_id=inv.id,version=version,uploaded_by=g.actor.id,
        filename=checked.filename,pdf=checked.content,sha256=sha256(checked.content).hexdigest(),page_count=checked.pages)
    g.db.add(row);g.db.flush();req.updated_at=now()
    audit(g.db,'MANUAL_REVIEW_PDF_UPLOADED',g.actor.id,req.id,inv.id,changes=[{'field':'manual_pdf','before':previous.id if previous else None,'after':row.id}])
    return ok(manual_dto(row),201)


@api.get('/requests/<request_id>/invoices/<invoice_id>/manual-pdf/<pdf_id>')
def download_manual(request_id,invoice_id,pdf_id):
    req=scoped_request(request_id);inv=scoped_invoice(req,invoice_id);require_review(req)
    row=g.db.get(ManualReviewPDF,pdf_id)
    if not row or row.invoice_id!=inv.id:fail(404,'NOT_FOUND','PDF hasil review tidak ditemukan.')
    return send_file(BytesIO(row.pdf),mimetype='application/pdf',as_attachment=True,download_name=row.filename)


@api.post('/requests/<request_id>/invoices/<invoice_id>/manual-pdf/<pdf_id>/signature')
def signature_check(request_id,invoice_id,pdf_id):
    req,inv=mutation_invoice(request_id,invoice_id,body());require_review(req)
    row=latest_manual(g.db,inv)
    if not row or row.id!=pdf_id:fail(409,'MANUAL_PDF_CHANGED','PDF manual sudah berubah. Muat ulang.')
    if row.signature_state in ('DETECTED','NOT_DETECTED','UNCERTAIN'):return ok(manual_dto(row))
    since=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='microseconds').replace('+00:00','Z')
    lease=(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat(timespec='microseconds').replace('+00:00','Z')
    if row.signature_state=='RUNNING' and row.analysis_started_at and row.analysis_started_at>lease:return ok(manual_dto(row))
    used=g.db.scalar(select(func.sum(ManualReviewPDF.analysis_attempts)).where(ManualReviewPDF.uploaded_by==g.actor.id,ManualReviewPDF.created_at>=since)) or 0
    if row.analysis_attempts>=2 or used>=10:fail(429,'SIGNATURE_LIMIT','Batas pemeriksaan tanda tangan tercapai. PDF tetap dapat diterbitkan tanpa pemeriksaan AI.')
    row.signature_state='RUNNING';row.analysis_attempts+=1;row.analysis_started_at=now();attempt=row.analysis_attempts
    pdf,pages=bytes(row.pdf),row.page_count;g.db.commit()
    try:
        analyzer=current_app.config.get('SIGNATURE_ANALYZER') or inspect_signature
        result=validate_signature(analyzer(pdf,pages,current_app.config),pages);state=result['status']
    except Exception:
        result={'status':'UNCERTAIN','note':'AI belum dapat memeriksa tanda tangan. Periksa PDF secara manual; unggahan tetap tersimpan.','pages':[]};state='FAILED'
    authenticate();req=scoped_request(request_id,True);inv=scoped_invoice(req,invoice_id);require_review(req)
    current=latest_manual(g.db,inv)
    if not current or current.id!=pdf_id or current.analysis_attempts!=attempt:fail(409,'MANUAL_PDF_CHANGED','Hasil analisis berasal dari PDF terdahulu. Muat ulang.')
    current.signature_state,current.signature_result=state,result
    audit(g.db,'SIGNATURE_AI_CHECKED',g.actor.id,req.id,inv.id,reason='Advisory only: '+state)
    return ok(manual_dto(current))
