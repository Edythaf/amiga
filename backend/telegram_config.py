"""Private bot configuration and verified recipient preferences. No secret in DTOs."""
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import tempfile
from threading import Lock
from .models import Setting, TelegramLink, TelegramChallenge, User, Role, Membership
from sqlalchemy import select

BOT_CONFIG_LOCK = Lock()


def setting_key(kind, user_id):
    return 'tg_' + kind + ':' + sha256(user_id.encode()).hexdigest()


def bot_settings(config):
    if config.get('TELEGRAM_RESOLVED'):
        return dict(config)
    result = dict(config)
    location = config.get('TELEGRAM_CONFIG_FILE') or (Path(config['UPLOAD_DIR']).parent / '.telegram-bot.json' if config.get('UPLOAD_DIR') else None)
    path = Path(location) if location else None
    try:
        if path and path.exists():
            if path.stat().st_size > 16384:
                raise ValueError()
            saved = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(saved, dict) or not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{30,100}', saved.get('token', ''))
                    or not re.fullmatch(r'[A-Za-z0-9_]{5,32}', saved.get('username', ''))):
                raise ValueError()
            result.update(TELEGRAM_BOT_TOKEN=saved['token'], TELEGRAM_BOT_USERNAME=saved['username'])
    except (OSError, ValueError, KeyError, TypeError):
        result.update(TELEGRAM_BOT_TOKEN='', TELEGRAM_BOT_USERNAME='', TELEGRAM_CONFIG_ERROR=True)
    result['TELEGRAM_RESOLVED'] = True
    return result


def bot_fingerprint(config):
    return sha256(bot_settings(config).get('TELEGRAM_BOT_TOKEN', '').encode()).hexdigest()


def bot_dto(config):
    values = bot_settings(config)
    token = values.get('TELEGRAM_BOT_TOKEN', '')
    return {'configured': bool(token), 'username': values.get('TELEGRAM_BOT_USERNAME') or None,
            'bot_id': token.split(':', 1)[0] if ':' in token else None,
            'revision': bot_fingerprint(values), 'configuration_error': bool(values.get('TELEGRAM_CONFIG_ERROR'))}


def write_bot_config(config, token, username):
    path = Path(config.get('TELEGRAM_CONFIG_FILE') or Path(config['UPLOAD_DIR']).parent / '.telegram-bot.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.telegram-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump({'token': token, 'username': username}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def preference(db, kind, user_id):
    row = db.get(Setting, setting_key(kind, user_id))
    return row.value if row else ''


def set_preference(db, kind, user_id, value):
    key = setting_key(kind, user_id)
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def normalize_contact(value):
    if value is None or value == '':
        return ''
    if not isinstance(value, str):
        raise ValueError('Isi username Telegram atau Chat ID, bukan nomor HP.')
    value = value.strip()
    if not value:
        return ''
    if re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{4,31}', value):
        return value.lower()
    if re.fullmatch(r'[1-9][0-9]{0,19}', value):
        return value
    raise ValueError('Gunakan @username Telegram atau Chat ID pribadi. Nomor HP saja tidak dapat dipakai mengirim voucher.')


def save_contact(db, user_id, value):
    value = normalize_contact(value)
    if preference(db, 'contact', user_id) != value:
        db.query(TelegramLink).filter(TelegramLink.user_id == user_id).delete()
        db.query(TelegramChallenge).filter(TelegramChallenge.user_id == user_id).delete()
        set_preference(db, 'contact', user_id, value)
    return value


def verified_link(db, user_id, config):
    row = db.get(TelegramLink, user_id)
    if not row or preference(db, 'link', user_id) != bot_fingerprint(config):
        return None
    return row


def company_recipients(db, client_id, config):
    users=db.scalars(select(User).join(Membership,Membership.user_id==User.id).join(Role,Role.user_id==User.id).where(
        Membership.client_id==client_id,Role.role=='COMPANY_CLIENT',User.account_status=='ACTIVE').order_by(User.display_name,User.id))
    return [{'user_id':u.id,'name':u.display_name,'connected':bool(verified_link(db,u.id,config))} for u in users]
