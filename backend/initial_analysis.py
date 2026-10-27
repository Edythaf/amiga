"""Durable first AI opinion before uploader confirmation; no DB lock during API IO."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from sqlalchemy import select,or_,and_,text,func
from .models import Invoice,InvoiceAssistance,WorkRequest,Document,Review,RequestLifecycle,AgentTurn,User,now,uid
from .repository import fields_for,sources_for,audit
from .workflow import input_hash,source_document
from .review_analysis import analyze,validate_analysis


def process_initial_one(app,request_id=None):
    factory=app.extensions['amiga_db']
    with factory.begin() as db:
        if db.bind.dialect.name=='sqlite':db.execute(text('BEGIN IMMEDIATE'))
        query=(select(Invoice).join(WorkRequest,WorkRequest.id==Invoice.request_id).join(User,User.id==WorkRequest.uploaded_by)
            .outerjoin(InvoiceAssistance,(InvoiceAssistance.invoice_id==Invoice.id)&(InvoiceAssistance.version==Invoice.current_version))
            .where(Invoice.active==1,WorkRequest.processing_status=='COMPLETE',User.account_status=='ACTIVE',
                ~select(Review.id).where(Review.invoice_id==Invoice.id,Review.version==Invoice.current_version,Review.decision=='APPROVED').exists(),
                ~select(RequestLifecycle.request_id).where(RequestLifecycle.request_id==WorkRequest.id,RequestLifecycle.state=='CLOSED').exists(),
                or_(InvoiceAssistance.invoice_id.is_(None),InvoiceAssistance.state=='PENDING',
                    and_(InvoiceAssistance.state=='RUNNING',InvoiceAssistance.lease_until<now()))))
        if request_id:query=query.where(Invoice.request_id==request_id)
        inv=db.scalar(query.order_by(WorkRequest.updated_at,Invoice.index).with_for_update(skip_locked=True,of=WorkRequest).limit(1))
        if not inv:return False
        req=db.get(WorkRequest,inv.request_id)
        db.scalar(select(User).where(User.id==req.uploaded_by).with_for_update())
        row=db.get(InvoiceAssistance,(inv.id,inv.current_version))
        if not row:
            row=InvoiceAssistance(invoice_id=inv.id,version=inv.current_version,attempts=0);db.add(row)
        fingerprint=input_hash(db,req,inv);token=uid('initial')
        day=datetime.now(timezone.utc).date().isoformat()+'T00:00:00.000000Z'
        used=db.scalar(select(func.count()).select_from(AgentTurn).where(AgentTurn.user_id==req.uploaded_by,AgentTurn.created_at>=day))
        if used>=app.config['AGENT_DAILY_LIMIT']:
            row.state,row.error_code,row.input_hash,row.updated_at='FAILED','AGENT_DAILY_LIMIT',fingerprint,now()
            return True
        usage=AgentTurn(id=uid('initialusage'),user_id=req.uploaded_by,role='uploader_initial',request_id=req.id,
                        question='Analisis awal invoice versi '+str(inv.current_version),input_hash=fingerprint,state='PENDING',model=app.config['AGENT_MODEL'])
        db.add(usage);usage_id=usage.id
        row.state,row.input_hash,row.job_token='RUNNING',fingerprint,token
        row.attempts=(row.attempts or 0)+1;row.updated_at=now()
        row.lease_until=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(timespec='microseconds').replace('+00:00','Z')
        context={'purpose':'Analisis awal untuk uploader sebelum konfirmasi. Temuan bukan persetujuan.',
                 'request_id':req.id,'invoice_id':inv.id,'version':inv.current_version,
                 'fields':fields_for(db,inv),'sources':sources_for(db,inv)}
        source=source_document(db,req)
        docs=([source] if source else [])+list(db.scalars(select(Document).where(Document.request_id==req.id,Document.type=='EVIDENCE').order_by(Document.uploaded_at.desc())))
        attachments=[];size=0;context['omitted_documents']=[]
        for doc in docs:
            path=Path(app.config['UPLOAD_DIR'])/doc.storage_key
            if len(attachments)>=5 or not path.is_file() or size+path.stat().st_size>15*1024*1024:
                context['omitted_documents'].append(doc.id);continue
            data=path.read_bytes();size+=len(data);attachments.append((f'source-{len(attachments)+1}.pdf',data))
        inv_id,version,req_id=inv.id,inv.current_version,req.id
    try:
        if not attachments:raise RuntimeError('INITIAL_SOURCE_UNAVAILABLE')
        config={**app.config,'OPENAI_MODEL':app.config['AGENT_MODEL']}
        result=(app.config.get('INITIAL_ANALYZER') or analyze)(context,attachments,config)
        validate_analysis(result['analysis'])
        error=None
    except Exception:
        result=None;error='INITIAL_ANALYSIS_FAILED'
    with factory.begin() as db:
        if db.bind.dialect.name=='sqlite':db.execute(text('BEGIN IMMEDIATE'))
        req=db.scalar(select(WorkRequest).where(WorkRequest.id==req_id).with_for_update())
        inv=db.get(Invoice,inv_id);row=db.get(InvoiceAssistance,(inv_id,version))
        usage=db.get(AgentTurn,usage_id)
        if usage:usage.state='FAILED' if error else 'DONE'
        if not row or row.job_token!=token:return True
        current=inv and inv.active==1 and inv.current_version==version and req.processing_status=='COMPLETE'
        if not current or input_hash(db,req,inv)!=fingerprint:
            row.state='SUPERSEDED'
        else:
            row.state='FAILED' if error else 'READY'
            row.result=result['analysis'] if result else None
            row.model=result.get('model',app.config['AGENT_MODEL']) if result else app.config['AGENT_MODEL']
            row.error_code=error
            audit(db,'INITIAL_AI_FAILED' if error else 'INITIAL_AI_READY',request_id=req_id,invoice_id=inv_id,
                  changes=[{'field':'version','before':None,'after':version}])
        row.job_token,row.lease_until,row.updated_at=None,None,now()
    return True
