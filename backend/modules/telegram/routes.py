"""Account linking + immutable review preview + explicit, idempotent dispatch."""
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json,re,secrets
from sqlalchemy import select,delete,update,text
from ...api_common import (api,g,current_app,body,ok,fail,request,scoped_request,scoped_invoice,
    require_review,require_role,roles,client_ids,CLIENT_ROLES,authenticate,latest_review,fields_for,audit,uid,now,reason)
from ...models import TelegramLink,TelegramChallenge,TelegramDelivery,TelegramAutomaticDelivery,AgentTurn,User,Setting,Voucher
from ...workflow import input_hash
from ...telegram_service import telegram_call,TelegramError
from ...telegram_config import (bot_settings,bot_dto,bot_fingerprint,write_bot_config,BOT_CONFIG_LOCK,
    preference,set_preference,save_contact,verified_link,company_recipients)


def require_sender(req):
    if 'SYSTEM_ADMIN' not in roles(g.db,g.actor):
        require_review(req)


@api.get('/admin/telegram-bot')
def telegram_bot_status():
    require_role('SYSTEM_ADMIN')
    return ok(bot_dto(current_app.config))


@api.patch('/admin/telegram-bot')
def telegram_bot_update():
    require_role('SYSTEM_ADMIN')
    data=body();token=data.get('token')
    if not isinstance(token,str) or not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{30,100}',token.strip()):
        fail(422,'INVALID_BOT_TOKEN','Masukkan token API bot dari BotFather, bukan ID bot saja.')
    token=token.strip()
    revision=data.get('expected_revision')
    if revision!=bot_fingerprint(current_app.config):fail(409,'BOT_CONFIG_CHANGED','Pengaturan bot berubah. Muat ulang sebelum menyimpan.')
    # getMe only verifies the supplied credential. It never sends a message.
    candidate=dict(current_app.config,TELEGRAM_BOT_TOKEN=token,TELEGRAM_RESOLVED=True)
    g.db.commit()
    try:
        identity=telegram_call('getMe',{},candidate)
        hook=telegram_call('getWebhookInfo',{},candidate)
    except TelegramError:fail(422,'BOT_VERIFICATION_FAILED','Token bot belum dapat diverifikasi. Pengaturan lama tetap berlaku.')
    authenticate();require_role('SYSTEM_ADMIN')
    username=identity.get('username') if isinstance(identity,dict) else None
    if (not isinstance(identity,dict) or identity.get('is_bot') is not True
            or str(identity.get('id'))!=token.split(':')[0]
            or not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_]{5,32}',username)):
        fail(422,'BOT_VERIFICATION_FAILED','Identitas bot tidak cocok dengan token.')
    if not isinstance(hook,dict) or hook.get('url'):
        fail(409,'BOT_WEBHOOK_ACTIVE','Bot memakai webhook. Gunakan bot khusus AMIGA tanpa webhook; webhook tidak dihapus otomatis.')
    with BOT_CONFIG_LOCK:
        if revision!=bot_fingerprint(current_app.config):fail(409,'BOT_CONFIG_CHANGED','Pengaturan bot berubah. Muat ulang.')
        try:write_bot_config(current_app.config,token,username)
        except OSError:fail(503,'BOT_CONFIG_WRITE_FAILED','Konfigurasi privat bot belum dapat disimpan.')
    audit(g.db,'TELEGRAM_BOT_CONFIGURED',g.actor.id,reason='Bot identity verified; secret omitted')
    return ok(bot_dto(current_app.config))


def expires(minutes):
    return (datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat(timespec='microseconds').replace('+00:00','Z')


def private_link():
    if roles(g.db,g.actor)!={'COMPANY_CLIENT'}:fail(403,'COMPANY_REQUIRED','Telegram penerima dihubungkan pada akun Klien perusahaan.')


def status():
    from ...telegram_automatic import automatic_consent
    row=verified_link(g.db,g.actor.id,current_app.config)
    return {'configured':bot_dto(current_app.config)['configured'],'connected':bool(row),
            'contact':preference(g.db,'contact',g.actor.id),
            'automatic_enabled':bool(automatic_consent(g.db,g.actor.id,current_app.config)),
            'username':row.username if row else None,'verified_at':row.verified_at if row else None}


@api.get('/telegram/status')
def telegram_status():
    private_link()
    return ok(status())


@api.patch('/telegram/automatic')
def telegram_automatic():
    private_link()
    enabled=body().get('enabled')
    if type(enabled) is not bool:fail(422,'AUTOMATIC_CHOICE_REQUIRED','Pilih aktif atau nonaktif untuk voucher otomatis.')
    from ...telegram_automatic import set_automatic
    try:set_automatic(g.db,g.actor.id,enabled,current_app.config)
    except ValueError as exc:fail(409,'TELEGRAM_VERIFICATION_REQUIRED',str(exc))
    audit(g.db,'TELEGRAM_AUTO_ENABLED' if enabled else 'TELEGRAM_AUTO_DISABLED',g.actor.id,
          reason='Company recipient selected automatic official voucher delivery')
    return ok(status())


@api.patch('/telegram/contact')
def telegram_contact():
    private_link()
    data=body()
    if 'contact' not in data:fail(422,'CONTACT_REQUIRED','Isi tujuan Telegram atau kirim contact kosong untuk menghapusnya.')
    try:save_contact(g.db,g.actor.id,data['contact'])
    except ValueError as exc:fail(422,'INVALID_TELEGRAM_CONTACT',str(exc))
    audit(g.db,'TELEGRAM_CONTACT_UPDATED',g.actor.id,reason='Recipient preference updated; verification required')
    return ok(status())


@api.post('/telegram/link')
def telegram_link():
    private_link()
    settings=bot_settings(current_app.config)
    if not settings['TELEGRAM_BOT_TOKEN']:fail(503,'TELEGRAM_NOT_CONFIGURED','Telegram belum diaktifkan pengelola. Akun tetap dapat digunakan.')
    username=settings['TELEGRAM_BOT_USERNAME']
    if not username:
        g.db.commit()
        try:username=telegram_call('getMe',{},current_app.config)['username']
        except (TelegramError,KeyError):fail(502,'TELEGRAM_UNAVAILABLE','Bot belum dapat dihubungi.')
        authenticate();private_link()
    if not re.fullmatch(r'[A-Za-z0-9_]{5,32}',username):fail(503,'TELEGRAM_NOT_CONFIGURED','Nama bot belum valid.')
    token='amiga_'+secrets.token_urlsafe(32)
    g.db.execute(delete(TelegramChallenge).where(TelegramChallenge.user_id==g.actor.id))
    g.db.add(TelegramChallenge(user_id=g.actor.id,token_hash=sha256(token.encode()).hexdigest(),expires_at=expires(15)))
    set_preference(g.db,'challenge',g.actor.id,bot_fingerprint(settings))
    return ok({'url':'https://t.me/'+username+'?start='+token,'expires_in_seconds':900})


@api.post('/telegram/verify')
def telegram_verify():
    private_link()
    pending=g.db.get(TelegramChallenge,g.actor.id)
    if not pending or pending.expires_at<=now():fail(409,'LINK_EXPIRED','Buat tautan baru, buka bot dan tekan Start.')
    settings=bot_settings(current_app.config);bot_hash=bot_fingerprint(settings)
    if preference(g.db,'challenge',g.actor.id)!=bot_hash:fail(409,'LINK_EXPIRED','Bot berubah. Buka tautan verifikasi baru.')
    cursor_key='telegram_offset:'+bot_hash[:48]
    cursor=g.db.get(Setting,cursor_key);offset=int(cursor.value) if cursor else 0
    g.db.commit()
    try:updates=telegram_call('getUpdates',{'offset':offset,'limit':100,'timeout':0,'allowed_updates':['message']},settings)
    except TelegramError:fail(502,'TELEGRAM_UNAVAILABLE','Telegram belum dapat diperiksa. Jika bot memakai webhook, gunakan bot khusus AMIGA tanpa webhook.')
    if not isinstance(updates,list):fail(502,'TELEGRAM_UNAVAILABLE','Respons bot belum valid.')
    g.db.rollback()
    if g.db.bind.dialect.name=='sqlite':g.db.execute(text('BEGIN IMMEDIATE'))
    authenticate();private_link()
    if bot_fingerprint(current_app.config)!=bot_hash:fail(409,'LINK_EXPIRED','Bot berubah. Verifikasi kembali.')
    for event in updates:
        message=event.get('message',{});chat=message.get('chat',{});sender=message.get('from',{})
        text_value=message.get('text','')
        if (chat.get('type')!='private' or str(chat.get('id'))!=str(sender.get('id')) or sender.get('is_bot')
            or not isinstance(text_value,str)):continue
        match=re.fullmatch(r'/start(?:@\w+)?\s+(amiga_[A-Za-z0-9_-]{43})',text_value.strip())
        if not match:continue
        challenge=g.db.scalar(select(TelegramChallenge).where(TelegramChallenge.token_hash==sha256(match.group(1).encode()).hexdigest(),TelegramChallenge.expires_at>now()).with_for_update())
        if not challenge:continue
        if preference(g.db,'challenge',challenge.user_id)!=bot_hash:continue
        user=g.db.get(User,challenge.user_id)
        if not user or user.account_status!='ACTIVE' or roles(g.db,user)!={'COMPANY_CLIENT'}:continue
        chat_id=str(chat['id'])
        if not re.fullmatch(r'[1-9][0-9]{0,19}',chat_id):continue
        contact=preference(g.db,'contact',user.id)
        if contact and contact!=(('@'+str(sender.get('username') or '')).lower() if contact.startswith('@') else chat_id):continue
        occupied=g.db.scalar(select(TelegramLink).where(TelegramLink.chat_id==chat_id,TelegramLink.user_id!=user.id))
        if occupied:continue
        row=g.db.get(TelegramLink,user.id)
        if not row:row=TelegramLink(user_id=user.id);g.db.add(row)
        row.chat_id,row.username,row.verified_at=chat_id,str(sender.get('username') or '')[:200] or None,now()
        set_preference(g.db,'link',user.id,bot_hash)
        g.db.delete(challenge)
        audit(g.db,'TELEGRAM_LINKED',user.id,reason='Private-chat challenge verified')
    if updates:
        new=max([offset]+[int(e.get('update_id',-1))+1 for e in updates])
        cursor=g.db.scalar(select(Setting).where(Setting.key==cursor_key).with_for_update())
        if cursor:cursor.value=str(max(int(cursor.value),new))
        else:g.db.add(Setting(key=cursor_key,value=str(new)))
    g.db.flush()
    return ok(status())


@api.delete('/telegram/link')
def telegram_unlink():
    private_link()
    g.db.execute(delete(TelegramLink).where(TelegramLink.user_id==g.actor.id))
    g.db.execute(delete(TelegramChallenge).where(TelegramChallenge.user_id==g.actor.id))
    audit(g.db,'TELEGRAM_UNLINKED',g.actor.id)
    return ok(status())


def fingerprint(req,inv,link,body_text,voucher_id,config=None):
    review=latest_review(g.db,inv)
    value={'input':input_hash(g.db,req,inv),'pic':req.pic_id,'recipient':link.user_id,
        'chat_id':link.chat_id,'linked_at':link.verified_at,'review':review.id if review else None,
        'message':body_text,'voucher_id':voucher_id,'bot':bot_fingerprint(config if config is not None else current_app.config)}
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def delivery_dto(row):
    user=g.db.get(User,row.recipient_id)
    return {'id':row.id,'request_id':row.request_id,'invoice_id':row.invoice_id,'version':row.version,
            'recipient_name':user.display_name,'recipient_telegram':'Chat ID …'+row.chat_id[-4:],
            'body':row.body,'has_voucher':bool(row.voucher_id),'automatic':bool(g.db.get(TelegramAutomaticDelivery,row.id)),
            'preview_hash':row.fingerprint,'state':row.state,'expires_at':row.expires_at,
            'created_at':row.created_at,'sent_at':row.sent_at,'error_code':row.error_code}


@api.get('/requests/<request_id>/telegram-deliveries')
def telegram_deliveries(request_id):
    req=scoped_request(request_id);require_sender(req)
    query=select(TelegramDelivery).where(TelegramDelivery.request_id==req.id)
    if 'SYSTEM_ADMIN' not in roles(g.db,g.actor):query=query.where(TelegramDelivery.sender_id==g.actor.id)
    rows=g.db.scalars(query.order_by(TelegramDelivery.created_at.desc()).limit(20))
    return ok({'items':[delivery_dto(r) for r in rows]})


@api.post('/requests/<request_id>/invoices/<invoice_id>/telegram-preview')
def telegram_preview(request_id,invoice_id):
    data=body();req=scoped_request(request_id,True);inv=scoped_invoice(req,invoice_id,data.get('expected_version',-1));require_sender(req)
    recipients=company_recipients(g.db,req.client_id,current_app.config)
    connected=[r for r in recipients if r['connected']]
    recipient_id=data.get('recipient_id')
    if recipient_id is None and len(connected)==1:recipient_id=connected[0]['user_id']
    if recipient_id not in {r['user_id'] for r in connected}:
        fail(409,'COMPANY_RECIPIENT_REQUIRED','Pilih akun Klien perusahaan yang sudah terverifikasi Telegram untuk perusahaan request ini.')
    link=verified_link(g.db,recipient_id,current_app.config)
    if not bot_dto(current_app.config)['configured'] or not link:
        fail(409,'TELEGRAM_UNAVAILABLE_FOR_COMPANY','Telegram Klien perusahaan belum terhubung. Voucher tetap tersedia di AMIGA.')
    turn=g.db.get(AgentTurn,data.get('turn_id')) if isinstance(data.get('turn_id'),str) else None
    expected_role='admin' if 'SYSTEM_ADMIN' in roles(g.db,g.actor) else 'reviewer'
    if not turn or turn.user_id!=g.actor.id or turn.role!=expected_role or turn.request_id!=req.id or turn.state!='DONE':
        fail(422,'CONVERSATION_REQUIRED','Tanyakan ringkasan hasil pada asisten reviewer untuk Request ID ini terlebih dahulu.')
    from ..agents.routes import context_for,digest
    if turn.request_hash!=digest(context_for(req.id)['selected_request']):
        fail(409,'AGENT_CONTEXT_CHANGED','Hasil review berubah sejak percakapan ini. Minta ringkasan AI terbaru sebelum membuat pratinjau.')
    message=data.get('message')
    review=latest_review(g.db,inv)
    fields=fields_for(g.db,inv)
    if message is None:
        prefix=f"AMIGA · Voucher Anda sudah jadi\nRequest ID: {req.id}\nInvoice: {fields['invoice_number'] or '-'} · versi {inv.current_version}\n\n"
        message=prefix+turn.result['answer'][:max(0,1000-len(prefix))]
    if not isinstance(message,str) or not 1<=len(message.strip())<=1000:fail(422,'MESSAGE_LIMIT','Pesan Telegram harus 1–1000 karakter.')
    # This notification announces a completed voucher, never an unfinished draft.
    voucher=g.db.scalar(select(Voucher).where(Voucher.invoice_id==inv.id,Voucher.version==inv.current_version))
    if not voucher or not review or review.decision!='APPROVED':fail(409,'OFFICIAL_VOUCHER_REQUIRED','Voucher harus sudah diterbitkan reviewer sebelum diinformasikan ke Telegram.')
    automatic=g.db.scalar(select(TelegramDelivery.id).join(TelegramAutomaticDelivery,
        TelegramAutomaticDelivery.delivery_id==TelegramDelivery.id).where(TelegramDelivery.voucher_id==voucher.id,
        TelegramDelivery.recipient_id==recipient_id,TelegramDelivery.state.in_(['QUEUED','SENDING','SENT','UNKNOWN'])).limit(1))
    if automatic:fail(409,'TELEGRAM_AUTOMATIC_EXISTS','Voucher ini sudah masuk pengiriman otomatis. Periksa riwayat pengiriman sebelum mengirim manual.')
    fp=fingerprint(req,inv,link,message.strip(),voucher.id if voucher else None)
    prior=g.db.scalar(select(TelegramDelivery).where(TelegramDelivery.fingerprint==fp,TelegramDelivery.state.in_(['SENDING','SENT','UNKNOWN'])).limit(1))
    if prior:fail(409,'TELEGRAM_ALREADY_DISPATCHED','Pesan yang sama sudah dikirim atau status pengirimannya perlu diperiksa; pengiriman tidak diulang otomatis.')
    g.db.execute(update(TelegramDelivery).where(TelegramDelivery.sender_id==g.actor.id,TelegramDelivery.request_id==req.id,TelegramDelivery.state=='DRAFT').values(state='CANCELLED'))
    row=TelegramDelivery(id=uid('tele'),request_id=req.id,invoice_id=inv.id,version=inv.current_version,
        sender_id=g.actor.id,recipient_id=link.user_id,chat_id=link.chat_id,body=message.strip(),
        voucher_id=voucher.id if voucher else None,fingerprint=fp,state='DRAFT',expires_at=expires(15))
    g.db.add(row);g.db.flush()
    audit(g.db,'TELEGRAM_PREVIEWED',g.actor.id,req.id,inv.id)
    return ok(delivery_dto(row),201)


@api.post('/telegram/previews/<preview_id>/send')
def telegram_send(preview_id):
    data=body()
    row=g.db.scalar(select(TelegramDelivery).where(TelegramDelivery.id==preview_id,TelegramDelivery.sender_id==g.actor.id))
    if not row:fail(404,'NOT_FOUND','Pratinjau tidak ditemukan.')
    req=scoped_request(row.request_id,True)
    g.db.refresh(row,with_for_update=True)
    inv=scoped_invoice(req,row.invoice_id,row.version);require_sender(req)
    if row.state=='SENT':return ok(delivery_dto(row))
    if row.state!='DRAFT':fail(409,'TELEGRAM_STATE','Pengiriman tidak dapat diulang otomatis. Periksa status pesan terlebih dahulu.')
    automatic=g.db.scalar(select(TelegramDelivery.id).join(TelegramAutomaticDelivery,
        TelegramAutomaticDelivery.delivery_id==TelegramDelivery.id).where(TelegramDelivery.voucher_id==row.voucher_id,
        TelegramDelivery.recipient_id==row.recipient_id,TelegramDelivery.state.in_(['QUEUED','SENDING','SENT','UNKNOWN'])).limit(1))
    if automatic:fail(409,'TELEGRAM_AUTOMATIC_EXISTS','Voucher ini sudah masuk pengiriman otomatis. Periksa riwayat pengiriman.')
    if data.get('approved') is not True or data.get('preview_hash')!=row.fingerprint:
        fail(422,'SEND_APPROVAL_REQUIRED','Setujui penerima, versi, pesan dan lampiran pada pratinjau ini.')
    settings=bot_settings(current_app.config)
    link=verified_link(g.db,row.recipient_id,settings)
    if row.expires_at<=now() or not link or fingerprint(req,inv,link,row.body,row.voucher_id,settings)!=row.fingerprint:
        fail(409,'TELEGRAM_PREVIEW_STALE','Data atau penerima berubah. Buat dan setujui pratinjau baru.')
    recipient=g.db.get(User,row.recipient_id)
    if recipient.account_status!='ACTIVE' or roles(g.db,recipient)!={'COMPANY_CLIENT'} or req.client_id not in client_ids(g.db,recipient):
        fail(409,'RECIPIENT_INACTIVE','Penerima tidak lagi mempunyai akses klien ini.')
    voucher=g.db.get(Voucher,row.voucher_id) if row.voucher_id else None
    review=latest_review(g.db,inv)
    if not voucher or not review or review.decision!='APPROVED':fail(409,'OFFICIAL_VOUCHER_REQUIRED','Voucher resmi aktif belum tersedia.')
    pdf=bytes(voucher.pdf) if voucher else None
    payload={'chat_id':row.chat_id,'caption' if pdf else 'text':row.body}
    row.state='SENDING';g.db.commit()
    try:
        result=telegram_call('sendDocument' if pdf else 'sendMessage',payload,settings,pdf)
        message_id=result.get('message_id') if isinstance(result,dict) else None
        if type(message_id) is not int:raise TelegramError('TELEGRAM_UNCERTAIN',True)
        state,error='SENT',None
    except TelegramError as exc:state,error='UNKNOWN' if exc.uncertain else 'FAILED',exc.code
    except Exception:state,error='UNKNOWN','TELEGRAM_UNCERTAIN'
    row=g.db.get(TelegramDelivery,preview_id);row.state,row.error_code=state,error
    if state=='SENT':row.sent_at,row.message_id=now(),str(message_id)
    audit(g.db,'TELEGRAM_'+state,row.sender_id,row.request_id,row.invoice_id,reason=error,
          changes=[{'field':'delivery_id','before':None,'after':row.id}])
    g.db.commit()
    return ok(delivery_dto(row))
