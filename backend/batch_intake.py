"""Split a new batch PDF into independent tasks in the extraction transaction."""
from sqlalchemy import select
from .models import WorkRequest,Document,RequestSource,RequestIntake,now,uid
from .validation import InvalidDraft
from pathlib import Path
from shutil import copyfileobj


def clone_document(db,doc,request_id,storage_root,new_files):
    identifier=uid('doc');key=identifier+Path(doc.storage_key).suffix
    path=Path(storage_root)/key
    with path.open('xb') as target:
        new_files.append(path)
        with (Path(storage_root)/doc.storage_key).open('rb') as source:copyfileobj(source,target)
    copy=Document(id=identifier,request_id=request_id,type=doc.type,original_filename=doc.original_filename,
        mime_type=doc.mime_type,page_count=doc.page_count,storage_key=key,sha256=doc.sha256,
        uploaded_by=doc.uploaded_by,uploaded_at=doc.uploaded_at,description=doc.description)
    db.add(copy)
    return copy


def targets(db,req,document_id,rows,storage_root,new_files):
    intake=db.get(RequestIntake,req.id)
    if not intake:
        return [(req,document_id,rows)]  # Preserve legacy requests and their historical workflow.
    if intake.selected:
        if len(rows)==1:return [(req,document_id,rows)]
        matches=[r for r in rows if (r.get('invoice_number') or '').casefold()==(intake.invoice_number or '').casefold()
                 and (r.get('vendor_name') or '').casefold()==(intake.vendor_name or '').casefold()]
        if len(matches)!=1:raise InvalidDraft('SPLIT_TARGET_AMBIGUOUS')
        return [(req,document_id,matches)]
    if len(rows)>20:raise InvalidDraft('Maksimal 20 invoice dalam satu PDF batch.')
    documents=list(db.scalars(select(Document).where(Document.request_id==req.id)))
    result=[]
    for index,fields in enumerate(rows):
        if index==0:
            target,doc_id,member=req,document_id,intake
        else:
            target=WorkRequest(id=uid('req'),client_id=req.client_id,uploaded_by=req.uploaded_by,pic_id=None,
                request_type=req.request_type,channel=req.channel,request_date=req.request_date,deadline=req.deadline,
                updated_at=now(),processing_status='COMPLETE',stage='Menunggu konfirmasi uploader')
            db.add(target);db.flush()
            from .request_numbers import assign_request_number
            assign_request_number(db,target)
            copied={}
            for doc in documents:
                copy=clone_document(db,doc,target.id,storage_root,new_files);copied[doc.id]=copy.id
            db.flush();doc_id=copied[document_id]
            db.add(RequestSource(request_id=target.id,document_id=doc_id,revision=1))
            member=RequestIntake(request_id=target.id,batch_id=intake.batch_id,source_group=intake.source_group)
            db.add(member)
        member.selected=1;member.invoice_number=fields.get('invoice_number');member.vendor_name=fields.get('vendor_name')
        result.append((target,doc_id,[fields]))
    return result
