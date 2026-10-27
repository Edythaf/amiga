"""Authenticated, rate-limited per-role agents. Model output cannot execute a send."""
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json,re
from sqlalchemy import select,func
from ...api_common import (api,g,current_app,request,body,ok,fail,scoped_request,request_access,
    request_dto,invoice_dto,invoices,authenticate,roles,now,uid,task_complete,lifecycle)
from ...models import AgentTurn,WorkRequest,User,Document
from ...agent_service import agent_role,urgency,reviewer_metrics,reply,validate_reply
from ...workflow import ready_for_review
from ...telegram_config import bot_dto


def context_for(request_id=None):
    if roles(g.db,g.actor)=={'COMPANY_CLIENT'}:fail(403,'COMPANY_TRACKING_ONLY','Gunakan portal progres perusahaan.')
    role=agent_role(g.db,g.actor)
    query=select(WorkRequest)
    if role=='uploader':query=query.where(request_access())
    elif role=='reviewer':query=query.where((WorkRequest.pic_id==g.actor.id)|((WorkRequest.pic_id.is_(None))&(WorkRequest.uploaded_by!=g.actor.id)&~select(Document.id).where(Document.request_id==WorkRequest.id,Document.uploaded_by==g.actor.id).exists()))
    candidates=list(g.db.scalars(query.order_by(WorkRequest.deadline,WorkRequest.id).limit(201)))
    if role=='reviewer':candidates=[r for r in candidates if r.pic_id==g.actor.id or lifecycle(g.db,r)['state']=='OPEN' and not task_complete(r) and ready_for_review(g.db,r)]
    rows=[request_dto(req) for req in candidates[:100]]
    cards=[{key:r[key] for key in ('id','request_code','client_name','pic_name','deadline','work_status','updated_at','invoice_count','voucher_count')} for r in rows]
    urgent=[u for row in rows if (u:=urgency(row))]
    codes={r['id']:r['request_code'] for r in rows}
    for item in urgent:item['request_code']=codes[item['request_id']]
    urgent.sort(key=lambda u:(u['priority']!='HIGH',u['deadline'],u['request_id']))
    result={'role':role,'requests':cards,'urgent':urgent[:30],'truncated':len(candidates)>100,
            'today_jakarta':(datetime.now(timezone.utc)+timedelta(hours=7)).date().isoformat()}
    if request_id:
        req=scoped_request(request_id)
        detail=request_dto(req,True)
        result['selected_request']={key:detail[key] for key in ('id','request_code','client_name','pic_name','deadline','work_status','updated_at','processing','ready_for_review','invoices','telegram')}
    if role=='admin':result['performance']=reviewer_metrics(g.db)
    return result


def digest(value):
    def stable(item):
        if isinstance(item,dict):return {k:stable(v) for k,v in item.items() if k!='executed_at'}
        if isinstance(item,list):return [stable(v) for v in item]
        return item
    return sha256(json.dumps(stable(value),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


@api.get('/agents/overview')
def agent_overview():
    request_id=request.args.get('request_id') or None
    if request_id and len(request_id)>160:fail(422,'INVALID_REQUEST_ID','Request ID tidak valid.')
    return ok({**context_for(request_id),'model':current_app.config['AGENT_MODEL'],
               'telegram_configured':bot_dto(current_app.config)['configured'],
               'daily_limit':current_app.config['AGENT_DAILY_LIMIT']})


@api.get('/agents/history')
def agent_history():
    request_id=request.args.get('request_id') or None
    if request_id:request_id=scoped_request(request_id).id
    role=agent_role(g.db,g.actor)
    rows=list(g.db.scalars(select(AgentTurn).where(AgentTurn.user_id==g.actor.id,AgentTurn.role==role,
        AgentTurn.request_id==request_id,AgentTurn.state=='DONE').order_by(AgentTurn.created_at.desc()).limit(20)))
    return ok({'items':[{'id':r.id,'question':r.question,'result':r.result,'created_at':r.created_at,'model':r.model} for r in reversed(rows)]})


@api.post('/agents/chat')
def agent_chat():
    data=body();question=data.get('question');request_id=data.get('request_id') or None
    if not isinstance(question,str) or not 1<=len(question.strip())<=1000:fail(422,'INVALID_QUESTION','Pertanyaan harus 1–1000 karakter.')
    question=question.strip()
    if not request_id:
        match=re.search(r'\b(?:req_[0-9a-f]{32}|REQ-\d{8}-\d{4,}-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{4,})\b',question,re.I)
        if match:request_id=match.group()
    if request_id is not None and (not isinstance(request_id,str) or len(request_id)>160):fail(422,'INVALID_REQUEST_ID','Request ID tidak valid.')
    if request_id:request_id=scoped_request(request_id).id
    g.db.refresh(g.actor,with_for_update=True)
    context=context_for(request_id);role=context['role'];fingerprint=digest({'context':context,'question':question})
    cached=g.db.scalar(select(AgentTurn).where(AgentTurn.user_id==g.actor.id,AgentTurn.role==role,
        AgentTurn.request_id==request_id,AgentTurn.input_hash==fingerprint,AgentTurn.model==current_app.config['AGENT_MODEL'],AgentTurn.state=='DONE').order_by(AgentTurn.created_at.desc()).limit(1))
    if cached:return ok({'id':cached.id,'result':cached.result,'model':cached.model,'cached':True,'request_id':request_id})
    today=datetime.now(timezone.utc).date().isoformat()+'T00:00:00.000000Z'
    count=g.db.scalar(select(func.count()).select_from(AgentTurn).where(AgentTurn.user_id==g.actor.id,AgentTurn.created_at>=today))
    if count>=current_app.config['AGENT_DAILY_LIMIT']:fail(429,'AGENT_DAILY_LIMIT','Kuota bantuan AI hari ini habis. Proses invoice tetap dapat dilanjutkan dari data yang tersedia.')
    recent=g.db.scalar(select(AgentTurn.created_at).where(AgentTurn.user_id==g.actor.id,AgentTurn.role.in_(['uploader','reviewer','admin'])).order_by(AgentTurn.created_at.desc()).limit(1))
    if recent and (datetime.now(timezone.utc)-datetime.fromisoformat(recent.replace('Z','+00:00'))).total_seconds()<5:
        fail(429,'AGENT_RATE_LIMIT','Tunggu lima detik sebelum bertanya lagi.')
    history=list(g.db.scalars(select(AgentTurn).where(AgentTurn.user_id==g.actor.id,AgentTurn.role==role,
        AgentTurn.request_id==request_id,AgentTurn.state=='DONE').order_by(AgentTurn.created_at.desc()).limit(4)))
    prior=[{'question':r.question,'answer':r.result['answer']} for r in reversed(history)]
    if len(json.dumps(context,ensure_ascii=False))>100000:fail(422,'AGENT_CONTEXT_LIMIT','Pilih Request ID agar konteks analisis lebih kecil.')
    if not current_app.config.get('OPENAI_API_KEY') and not current_app.config.get('AGENT_RESPONDER'):
        fail(503,'AGENT_NOT_CONFIGURED','Layanan AI belum tersedia. Hubungi pengelola.')
    turn=AgentTurn(id=uid('chat'),user_id=g.actor.id,role=role,request_id=request_id,question=question,input_hash=fingerprint,
                   request_hash=digest(context['selected_request']) if request_id else None,state='PENDING',model=current_app.config['AGENT_MODEL'])
    g.db.add(turn);g.db.commit();turn_id=turn.id
    try:
        result=(current_app.config.get('AGENT_RESPONDER') or reply)(question,context,prior,current_app.config)
        validate_reply(result)
        if result['intent']=='OUT_OF_SCOPE':result={'answer':'Saya membantu pekerjaan invoice, voucher, progres dan pemeriksaan AMIGA. Pilih Request ID atau tanyakan tugas yang perlu ditindaklanjuti.','next_steps':[],'intent':'OUT_OF_SCOPE'}
        if role!='reviewer' and result['intent']=='PREVIEW_TELEGRAM':result={**result,'intent':'ANSWER'}
    except Exception:
        g.db.get(AgentTurn,turn_id).state='FAILED';g.db.commit()
        fail(502,'AGENT_UNAVAILABLE','AI belum dapat menjawab. Progres dan pekerjaan tetap tersimpan; coba kembali nanti.')
    g.db.expire_all();authenticate()
    if g.actor.account_status!='ACTIVE' or agent_role(g.db,g.actor)!=role:fail(403,'AGENT_ACCESS_CHANGED','Akses akun berubah. Masuk kembali.')
    fresh=context_for(request_id)
    if digest({'context':fresh,'question':question})!=fingerprint:
        g.db.get(AgentTurn,turn_id).state='STALE';g.db.commit()
        fail(409,'AGENT_CONTEXT_CHANGED','Data pekerjaan berubah selama analisis. Tanyakan kembali untuk hasil terbaru.')
    turn=g.db.get(AgentTurn,turn_id);turn.state,turn.result='DONE',result
    return ok({'id':turn.id,'result':result,'model':turn.model,'cached':False,'request_id':request_id})
