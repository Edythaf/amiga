import json,re
from hashlib import sha256
from ...api_common import api,g,request,select,ok,fail,read_upload,save_upload,audit,uid,now,request_dto,current_app
from ...models import WorkRequest,RequestSource,RequestIntake,UploadBatch,Document
from .routes import upload_metadata
from ...batch_intake import clone_document


@api.post('/requests/batch')
def upload_batch():
    values=upload_metadata()
    key=request.form.get('idempotency_key','')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',key):fail(422,'BATCH_KEY_REQUIRED','Muat ulang formulir untuk membuat identitas unggahan.')
    files=[f for f in request.files.getlist('invoice_files[]') if f.filename]
    evidence=[f for f in request.files.getlist('evidence_files[]') if f.filename]
    if not 1<=len(files)<=10 or len(evidence)>10:fail(422,'FILE_LIMIT','Pilih 1–10 invoice dan maksimal 10 bukti; total unggahan maksimal 32 MB.')
    checked=[read_upload(f,allow_images=True) for f in files]
    supports=[read_upload(f) for f in evidence]
    fingerprint=sha256(json.dumps([values,[(f.filename,sha256(f.content).hexdigest()) for f in checked],
        [(f.filename,sha256(f.content).hexdigest()) for f in supports]],sort_keys=True).encode()).hexdigest()
    batch=g.db.scalar(select(UploadBatch).where(UploadBatch.uploaded_by==g.actor.id,UploadBatch.idempotency_key==key))
    if batch:
        if batch.fingerprint!=fingerprint:fail(409,'BATCH_CHANGED','Identitas unggahan sudah dipakai untuk isi berbeda. Muat ulang formulir.')
    else:
        batch=UploadBatch(id=uid('batch'),client_id=values['client_id'],uploaded_by=g.actor.id,idempotency_key=key,fingerprint=fingerprint)
        g.db.add(batch);g.db.flush();shared=[]
        for file in checked:
            req=WorkRequest(id=uid('req'),uploaded_by=g.actor.id,updated_at=now(),processing_status='QUEUED',stage='Menunggu ekstraksi',**values)
            g.db.add(req);g.db.flush()
            from ...request_numbers import assign_request_number
            assign_request_number(g.db,req)
            source=save_upload(req,file,'INVOICE');g.db.add(RequestSource(request_id=req.id,document_id=source.id,revision=1))
            g.db.add(RequestIntake(request_id=req.id,batch_id=batch.id,source_group=req.id))
            if not shared:
                shared=[save_upload(req,f,'EVIDENCE') for f in supports]
            else:
                for doc in shared:
                    clone_document(g.db,doc,req.id,current_app.config['UPLOAD_DIR'],g.new_files)
            audit(g.db,'REQUEST_UPLOADED',g.actor.id,req.id,reason='Batch '+batch.id+'; invoice tasks are independent')
    g.db.flush()
    requests=list(g.db.scalars(select(WorkRequest).join(RequestIntake).where(RequestIntake.batch_id==batch.id).order_by(WorkRequest.id)))
    return ok({'batch_id':batch.id,'items':[request_dto(req,True) for req in requests],
               'message':'Setiap invoice menjadi tugas terpisah setelah ekstraksi dan konfirmasi uploader.'},201)
