"""Password AMIGA: current password or a short-lived code issued by a local admin."""
import json
from hashlib import sha256
from ...api_common import (api, g, current_app, session, secrets, datetime, timezone, timedelta,
    User, LocalCredential, AuthSession, Setting, body, local_input, require_role, fail, ok,
    select, delete, hash_password, audit, now)
from .routes import checked_local_password


def reset_key(user_id):
    return 'password_reset:' + user_id


def password_hash(data):
    if data.get('new_password') != data.get('password_confirm'):
        fail(422, 'PASSWORD_CONFIRMATION', 'Konfirmasi sandi baru belum sama.')
    try:
        return hash_password(data.get('new_password'))
    except ValueError as exc:
        fail(422, 'INVALID_PASSWORD', str(exc))


def replace_password(user, credential, encoded, action):
    credential.password_hash = encoded
    credential.failed_attempts, credential.locked_until = 0, None
    credential.updated_at = now()
    record = g.db.get(Setting, reset_key(user.id))
    if record:
        g.db.delete(record)
    g.db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(g.db, action, actor_id=user.id, reason='Local password updated; all account sessions revoked')
    # Do not sign in or change a role/status as a side effect of recovery.
    session.clear()
    session['csrf'] = secrets.token_urlsafe(32)
    return ok({'password_changed': True, 'csrf_token': session['csrf']})


@api.post('/auth/password/change')
def change_password():
    data = body()
    user, credential, _ = checked_local_password(data, 'current_password')
    return replace_password(user, credential, password_hash(data), 'LOCAL_PASSWORD_CHANGED')


@api.post('/admin/users/<user_id>/password-reset')
def issue_password_reset(user_id):
    require_role('SYSTEM_ADMIN')
    if current_app.config['AUTH_METHOD'] != 'local_password':
        fail(503, 'AUTH_METHOD_DISABLED', 'Gunakan pemulihan dari penyedia login yang aktif.')
    user = g.db.scalar(select(User).where(User.id == user_id).with_for_update())
    credential = g.db.scalar(select(LocalCredential).where(LocalCredential.user_id == user_id).with_for_update())
    if not user or not credential:
        fail(404, 'LOCAL_ACCOUNT_NOT_FOUND', 'Akun dengan sandi AMIGA tidak ditemukan.')
    if user.account_status == 'DISABLED':
        fail(403, 'ACCOUNT_DISABLED', 'Aktifkan akun melalui pengaturan akses sebelum membuat kode reset.')
    code = secrets.token_urlsafe(32)
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    value = json.dumps({'hash': sha256(code.encode()).hexdigest(), 'expires_at': expiry,
                       'credential_hash': sha256(credential.password_hash.encode()).hexdigest(), 'attempts': 0})
    record = g.db.get(Setting, reset_key(user.id))
    if record:
        record.value = value
    else:
        g.db.add(Setting(key=reset_key(user.id), value=value))
    audit(g.db, 'PASSWORD_RESET_CODE_ISSUED', actor_id=g.actor.id,
          changes=[{'field': 'user_id', 'before': None, 'after': user.id}])
    # Plain code appears only in this no-store response, never in audit or user DTO.
    return ok({'email': user.email, 'reset_code': code, 'expires_at': expiry})


@api.post('/auth/password/reset')
def reset_password():
    data = body()
    email, _ = local_input(data)
    user = g.db.scalar(select(User).where(User.email == email).with_for_update())
    credential = g.db.scalar(select(LocalCredential).where(LocalCredential.user_id == user.id).with_for_update()) if user else None
    record = g.db.scalar(select(Setting).where(Setting.key == reset_key(user.id)).with_for_update()) if user else None
    try:
        value = json.loads(record.value) if record else {}
    except (ValueError, TypeError):
        value = {}
    code = data.get('reset_code')
    valid_code = isinstance(code, str) and len(code) == 43 and secrets.compare_digest(
        sha256(code.encode()).hexdigest(), value.get('hash', ''))
    valid_record = (user and user.account_status != 'DISABLED' and credential
                    and value.get('expires_at', '') > now() and value.get('attempts', 5) < 5
                    and secrets.compare_digest(value.get('credential_hash', ''), sha256(credential.password_hash.encode()).hexdigest()))
    if not valid_code or not valid_record:
        if record and value and value.get('attempts', 5) < 5:
            value['attempts'] = value.get('attempts', 0) + 1
            record.value = json.dumps(value)
            g.db.commit()  # Preserve failed code attempts on the error response.
        fail(400, 'RESET_CODE_INVALID', 'Email atau kode reset tidak cocok, kedaluwarsa, atau sudah dipakai. Minta kode baru kepada admin.')
    return replace_password(user, credential, password_hash(data), 'LOCAL_PASSWORD_RESET')
