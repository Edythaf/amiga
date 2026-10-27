"""Opted-in company recipients; transactional outbox, one attempt per voucher.

Publication only queues work. Network calls happen after the approval commits.
An interrupted/uncertain attempt is never retried automatically.
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json, secrets
from sqlalchemy import select, text, or_, and_
from .models import (TelegramAutomaticDelivery, TelegramDelivery, User, WorkRequest,
                     Invoice, Voucher, RequestNumber, now, uid)
from .repository import roles, client_ids, latest_review, fields_for, audit
from .telegram_config import (verified_link, bot_settings, bot_fingerprint,
                              preference, set_preference, company_recipients)
from .telegram_service import telegram_call, TelegramError


def deadline(minutes):
    return (datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat(timespec='microseconds').replace('+00:00','Z')


def link_binding(link, config):
    return sha256(json.dumps([link.user_id,link.chat_id,link.verified_at,bot_fingerprint(config)]).encode()).hexdigest()


def automatic_consent(db, user_id, config):
    link=verified_link(db,user_id,config)
    value=preference(db,'automatic',user_id)
    return value if link and value.startswith(link_binding(link,config)+':') else ''


def set_automatic(db, user_id, enabled, config):
    link=verified_link(db,user_id,config)
    if enabled and (not link or not bot_settings(config).get('TELEGRAM_BOT_TOKEN')):
        raise ValueError('Verifikasi Telegram penerima terlebih dahulu.')
    token=automatic_consent(db,user_id,config)
    set_preference(db,'automatic',user_id,(token or link_binding(link,config)+':'+secrets.token_hex(16)) if enabled else '')
    if not enabled:
        for row in db.scalars(select(TelegramDelivery).join(TelegramAutomaticDelivery,
                TelegramAutomaticDelivery.delivery_id==TelegramDelivery.id).where(
                TelegramDelivery.recipient_id==user_id,TelegramDelivery.state=='QUEUED')):
            row.state,row.error_code='CANCELLED','AUTOMATIC_DISABLED'


def automatic_fingerprint(db, row, config):
    link=verified_link(db,row.recipient_id,config)
    token=automatic_consent(db,row.recipient_id,config)
    if not link or not token:return None
    return sha256(json.dumps([row.request_id,row.invoice_id,row.version,row.sender_id,
        row.recipient_id,link.chat_id,link.verified_at,bot_fingerprint(config),token,
        row.voucher_id,row.body],ensure_ascii=False).encode()).hexdigest()


def enqueue_automatic(db, req, inv, voucher, sender_id, config):
    """Called inside the approval transaction; never backfills old vouchers."""
    db.flush()
    for recipient in company_recipients(db,req.client_id,config):
        user_id=recipient['user_id']
        user=db.get(User,user_id)
        if not recipient['connected'] or roles(db,user)!={'COMPANY_CLIENT'} or not automatic_consent(db,user_id,config):continue
        if db.scalar(select(TelegramAutomaticDelivery.delivery_id).where(
                TelegramAutomaticDelivery.voucher_id==voucher.id,TelegramAutomaticDelivery.recipient_id==user_id)):continue
        link=verified_link(db,user_id,config)
        number=db.get(RequestNumber,req.id)
        fields=fields_for(db,inv)
        # Fixed factual message, without unsaved AI text or a localhost link.
        message=(f"AMIGA · Voucher Anda sudah jadi\nRequest: {number.code if number else req.id}\n"
                 f"Invoice: {(fields['invoice_number'] or '-')[:200]} · versi {inv.current_version}\n\n"
                 "PDF voucher resmi hasil pemeriksaan reviewer terlampir. Silakan periksa hasilnya di AMIGA.")
        row=TelegramDelivery(id=uid('tele'),request_id=req.id,invoice_id=inv.id,version=inv.current_version,
            sender_id=sender_id,recipient_id=user_id,chat_id=link.chat_id,voucher_id=voucher.id,
            body=message,fingerprint='',state='QUEUED',expires_at=deadline(24*60))
        row.fingerprint=automatic_fingerprint(db,row,config)
        db.add(row);db.flush()
        db.add(TelegramAutomaticDelivery(delivery_id=row.id,voucher_id=voucher.id,recipient_id=user_id))
        audit(db,'TELEGRAM_AUTO_QUEUED',sender_id,req.id,inv.id,
              changes=[{'field':'delivery_id','before':None,'after':row.id}])
    db.flush()


def automatic_receipts(db, req, user_id, config):
    rows=db.scalars(select(TelegramDelivery).join(TelegramAutomaticDelivery,
        TelegramAutomaticDelivery.delivery_id==TelegramDelivery.id).where(
        TelegramDelivery.request_id==req.id,TelegramDelivery.recipient_id==user_id)
        .order_by(TelegramDelivery.created_at.desc(),TelegramDelivery.id.desc()).limit(20))
    return {'enabled':bool(automatic_consent(db,user_id,config)),
            'connected':bool(verified_link(db,user_id,config)),
            'items':[{'invoice_id':r.invoice_id,'version':r.version,'state':r.state,
                      'created_at':r.created_at,'sent_at':r.sent_at,'error_code':r.error_code} for r in rows]}


def cancellation_reason(db, row, config):
    req=db.scalar(select(WorkRequest).where(WorkRequest.id==row.request_id).with_for_update())
    inv=db.get(Invoice,row.invoice_id);voucher=db.get(Voucher,row.voucher_id)
    recipient=db.get(User,row.recipient_id);sender=db.get(User,row.sender_id)
    if (not req or not inv or not inv.active or inv.current_version!=row.version
            or inv.request_id!=req.id or req.processing_status!='COMPLETE'):return 'VOUCHER_SUPERSEDED'
    review=latest_review(db,inv)
    if (not voucher or voucher.invoice_id!=inv.id or voucher.version!=inv.current_version
            or not review or review.decision!='APPROVED' or voucher.review_id!=review.id):return 'OFFICIAL_VOUCHER_REQUIRED'
    if (not recipient or recipient.account_status!='ACTIVE' or roles(db,recipient)!={'COMPANY_CLIENT'}
            or req.client_id not in client_ids(db,recipient)):return 'RECIPIENT_INACTIVE'
    if (not sender or sender.account_status!='ACTIVE' or 'FINANCE_REVIEWER' not in roles(db,sender)
            or 'SYSTEM_ADMIN' in roles(db,sender) or req.pic_id!=sender.id):return 'SENDER_INACTIVE'
    if row.expires_at<=now():return 'AUTOMATIC_EXPIRED'
    if automatic_fingerprint(db,row,config)!=row.fingerprint:return 'AUTOMATIC_DESTINATION_CHANGED'
    return None


def process_automatic_one(app):
    """Durably claim under DB locking; never hold a DB transaction over HTTP."""
    factory=app.extensions['amiga_db']
    with factory() as db:
        if db.bind.dialect.name=='sqlite':db.execute(text('BEGIN IMMEDIATE'))
        query=select(TelegramDelivery).join(TelegramAutomaticDelivery,
            TelegramAutomaticDelivery.delivery_id==TelegramDelivery.id)
        interrupted=list(db.scalars(query.where(TelegramDelivery.state=='SENDING',TelegramDelivery.expires_at<=now())
            .with_for_update(of=TelegramDelivery,skip_locked=True)))
        for row in interrupted:
            row.state,row.error_code='UNKNOWN','AUTOMATIC_INTERRUPTED'
            audit(db,'TELEGRAM_UNKNOWN',row.sender_id,row.request_id,row.invoice_id,reason=row.error_code)
        row=db.scalar(query.where(TelegramDelivery.state=='QUEUED')
            .order_by(TelegramDelivery.created_at,TelegramDelivery.id).with_for_update(of=TelegramDelivery,skip_locked=True).limit(1))
        if not row:
            db.commit();return bool(interrupted)
        settings=bot_settings(app.config)
        problem=cancellation_reason(db,row,settings)
        if problem:
            row.state,row.error_code='CANCELLED',problem
            audit(db,'TELEGRAM_AUTO_CANCELLED',row.sender_id,row.request_id,row.invoice_id,reason=problem)
            db.commit();return True
        # Serialize one private chat across workers and space consecutive PDFs.
        # An outbox item stays QUEUED while this recipient is being served.
        recipient=db.scalar(select(User).where(User.id==row.recipient_id).with_for_update(skip_locked=True))
        busy=db.scalar(select(TelegramDelivery.id).where(TelegramDelivery.id!=row.id,
            TelegramDelivery.chat_id==row.chat_id,or_(TelegramDelivery.state=='SENDING',
            and_(TelegramDelivery.state=='SENT',TelegramDelivery.sent_at>deadline(-2/60)))).limit(1))
        if not recipient or busy:
            db.commit();return False
        row.state,row.expires_at='SENDING',deadline(5)
        delivery_id=row.id
        pdf=bytes(db.get(Voucher,row.voucher_id).pdf)
        payload={'chat_id':row.chat_id,'caption':row.body}
        db.commit()
    try:
        result=telegram_call('sendDocument',payload,settings,pdf)
        message_id=result.get('message_id') if isinstance(result,dict) else None
        if type(message_id) is not int:raise TelegramError('TELEGRAM_UNCERTAIN',True)
        state,error='SENT',None
    except TelegramError as exc:state,error=('UNKNOWN' if exc.uncertain else 'FAILED'),exc.code
    except Exception:state,error='UNKNOWN','TELEGRAM_UNCERTAIN'
    with factory.begin() as db:
        row=db.get(TelegramDelivery,delivery_id)
        row.state,row.error_code=state,error
        if state=='SENT':row.sent_at,row.message_id=now(),str(message_id)
        audit(db,'TELEGRAM_'+state,row.sender_id,row.request_id,row.invoice_id,reason=error,
              changes=[{'field':'delivery_id','before':None,'after':row.id}])
    return True
