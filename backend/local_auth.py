"""Password hashing and trusted first-owner setup. No Google connection required."""
from getpass import getpass
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import re
import secrets
import bcrypt
from sqlalchemy import select, text
from .models import User, Role, LocalCredential, Setting, uid, now
from .repository import audit

DUMMY_HASH = bcrypt.hashpw(b'amiga-dummy-credential', bcrypt.gensalt(rounds=12)).decode('ascii')


def parse_identity(value):
    if not isinstance(value, str) or len(value) > 280:
        raise ValueError('Email tidak valid.')
    marker = re.search(r'\s*/(admin|review|view|uploder|uploader)\s*$', value, re.I)
    requested_role = {'admin': 'SYSTEM_ADMIN', 'review': 'FINANCE_REVIEWER', 'view': 'FINANCE_REVIEWER',
                      'uploder': 'CLIENT_OWNER', 'uploader': 'CLIENT_OWNER'}.get(marker.group(1).lower()) if marker else None
    email = (value[:marker.start()] if marker else value).strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[^\s@/]+@[^\s@/]+\.[^\s@/]+', email):
        raise ValueError('Email tidak valid.')
    return email, requested_role


def parse_email(value):
    email, role = parse_identity(value)
    return email, role == 'SYSTEM_ADMIN'


def password_bytes(value):
    if not isinstance(value, str) or not 10 <= len(value) <= 72 or len(value.encode('utf-8')) > 72:
        raise ValueError('Password minimal 10 karakter dan maksimal 72 byte UTF-8.')
    return value.encode('utf-8')


def hash_password(value):
    return bcrypt.hashpw(password_bytes(value), bcrypt.gensalt(rounds=12)).decode('ascii')


def verify_password(value, stored):
    try:
        return bcrypt.checkpw(password_bytes(value), stored.encode('ascii'))
    except (ValueError, TypeError, UnicodeError):
        return False


def prepare_owner_setup(app):
    """Only the local launcher can mint this short-lived, one-use capability."""
    if app.config['AUTH_METHOD'] != 'local_password':
        return None
    email, _ = parse_email(app.config['ADMIN_BOOTSTRAP_EMAIL'])
    with app.extensions['amiga_db'].begin() as db:
        if app.extensions['amiga_engine'].dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        bootstrap = db.scalar(select(Setting).where(Setting.key == 'bootstrap_consumed').with_for_update())
        user = db.scalar(select(User).where(User.email == email))
        if (bootstrap.value != '0' or db.scalar(select(Role).where(Role.role == 'SYSTEM_ADMIN').limit(1))
                or (user and db.get(LocalCredential, user.id))):
            return None
        if user and (user.account_status == 'DISABLED' or db.get(Role, (user.id, 'FINANCE_REVIEWER'))):
            raise ValueError('Akun pemilik perlu diperiksa sebelum aktivasi admin.')
        token = secrets.token_urlsafe(32)
        value = json.dumps({'hash': sha256(token.encode()).hexdigest(), 'email': email,
                           'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec='microseconds').replace('+00:00', 'Z')})
        record = db.get(Setting, 'owner_setup')
        if record:
            record.value = value
        else:
            db.add(Setting(key='owner_setup', value=value))
        return token


def owner_setup_record(db, token, email):
    """Validate without consuming. The registration transaction consumes on success."""
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    bootstrap = db.scalar(select(Setting).where(Setting.key == 'bootstrap_consumed').with_for_update())
    record = db.scalar(select(Setting).where(Setting.key == 'owner_setup').with_for_update())
    if not record or bootstrap.value != '0':
        return None
    try:
        value = json.loads(record.value)
        if (value['email'] != email or value['expires_at'] <= now()
                or not secrets.compare_digest(value['hash'], sha256(token.encode()).hexdigest())):
            return None
    except (ValueError, TypeError, KeyError):
        return None
    if db.scalar(select(Role).where(Role.role == 'SYSTEM_ADMIN').limit(1)):
        return None
    user = db.scalar(select(User).where(User.email == email))
    if user and (db.get(LocalCredential, user.id) or user.account_status == 'DISABLED'
                 or db.get(Role, (user.id, 'FINANCE_REVIEWER'))):
        return None
    return record


def setup_admin(app, password_reader=None):
    """Local operator creates a password once; /admin activates the role later."""
    if app.config['AUTH_METHOD'] != 'local_password':
        return False
    email, _ = parse_email(app.config['ADMIN_BOOTSTRAP_EMAIL'])
    factory = app.extensions['amiga_db']
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user and db.get(LocalCredential, user.id):
            return False
        other_admin = db.scalar(select(Role).where(Role.role == 'SYSTEM_ADMIN', Role.user_id != (user.id if user else '')))
        if other_admin:
            raise ValueError('Admin sudah ada. Pengelola yang aktif perlu mengatur akun tambahan.')
        if user and user.account_status == 'DISABLED':
            raise ValueError('Akun pemilik dinonaktifkan. Periksa akun melalui pengelola yang aktif.')
        if user and db.get(Role, (user.id, 'FINANCE_REVIEWER')):
            raise ValueError('System Admin tidak boleh sekaligus Finance Reviewer.')
    reader = password_reader or getpass
    print('Buat password khusus AMIGA sekali saja. Password tidak tampil saat diketik.')
    password = reader('Password AMIGA (minimal 10 karakter): ')
    encoded = hash_password(password)
    if password != reader('Ulangi password AMIGA: '):
        raise ValueError('Konfirmasi password tidak sama. Jalankan lagi.')
    # Recheck after the interactive prompt so concurrent setup cannot overwrite a password.
    with factory.begin() as db:
        if app.extensions['amiga_engine'].dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        bootstrap = db.scalar(select(Setting).where(Setting.key == 'bootstrap_consumed').with_for_update())
        user = db.scalar(select(User).where(User.email == email).with_for_update())
        admin = db.scalar(select(Role).where(Role.role == 'SYSTEM_ADMIN').limit(1))
        if admin and (not user or admin.user_id != user.id):
            raise ValueError('Admin sudah ada. Setup dibatalkan.')
        if user and db.get(LocalCredential, user.id):
            return False
        if user and user.account_status == 'DISABLED':
            raise ValueError('Akun pemilik dinonaktifkan.')
        if user and db.get(Role, (user.id, 'FINANCE_REVIEWER')):
            raise ValueError('System Admin tidak boleh sekaligus Finance Reviewer.')
        if not user:
            if bootstrap.value != '0':
                raise ValueError('Aktivasi admin pertama telah digunakan.')
            user = User(id=uid('usr'), email=email, display_name=email.split('@')[0], account_status='PENDING_ADMIN')
            db.add(user)
            db.flush()
        is_admin = bool(admin and admin.user_id == user.id)
        if not is_admin and bootstrap.value != '0':
            raise ValueError('Aktivasi admin pertama telah digunakan.')
        db.add(LocalCredential(user_id=user.id, password_hash=encoded, admin_bootstrap_allowed=0 if is_admin else 1, updated_at=now()))
        if not is_admin:
            user.account_status = 'PENDING_ADMIN'
        audit(db, 'LOCAL_PASSWORD_CONFIGURED', actor_id=user.id, reason='Trusted local operator setup')
    print('Password AMIGA tersimpan. Masuk pertama dengan email/admin, berikutnya cukup email biasa.')
    return True
