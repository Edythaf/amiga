"""ZIP primary controller, adapted to the existing portal API and revocable access.

The native HTML/session/SQL controller is rebased onto the shared integration
schema so there is one login, one policy, one set of immutable invoice versions.
"""
from ...api_common import (
    LocalCredential, Role, Setting, User, api, audit,
    body, create_client_workspace, current_app, datetime, fail, g,
    hash_password, local_input, now, ok, owner_setup_record, parse_identity,
    pending_status, re, request_role, roles, secrets, select,
    session, session_dto, start_session, timedelta, timezone, uid,
    verify_password
)


@api.get('/auth/csrf')
def csrf():
    session.setdefault('csrf', secrets.token_urlsafe(32))
    method = current_app.config['AUTH_METHOD']
    data = {'csrf_token': session['csrf'], 'google_client_id': current_app.config['GOOGLE_CLIENT_ID'], 'review_workflow': 'task_pool_v1',
            'auth_method': method, 'auth_configured': method == 'local_password' or bool(current_app.config['GOOGLE_CLIENT_ID'])}
    token = session.get('owner_setup_token')
    if token:
        email = current_app.config['ADMIN_BOOTSTRAP_EMAIL']
        if method == 'local_password' and owner_setup_record(g.db, token, email):
            data['owner_setup_email_input'] = email + '/admin'
        else:
            session.pop('owner_setup_token', None)
    return ok(data)



@api.post('/auth/owner-setup')
def owner_setup():
    data = body()
    if current_app.config['AUTH_METHOD'] != 'local_password':
        fail(503, 'AUTH_METHOD_DISABLED', 'Gunakan metode masuk yang aktif.')
    email = current_app.config['ADMIN_BOOTSTRAP_EMAIL']
    if not owner_setup_record(g.db, data.get('setup_token'), email):
        session.pop('owner_setup_token', None)
        fail(403, 'OWNER_SETUP_EXPIRED', 'Tautan aktivasi tidak berlaku. Jalankan ulang Start-AMIGA.cmd untuk membuka tautan baru.')
    # Keep the verified capability in an HttpOnly signed cookie so a page reload
    # does not lose the setup form. It still expires/consumes against the DB hash.
    session['owner_setup_token'] = data['setup_token']
    return ok({'email_input': email + '/admin'})



@api.post('/auth/register')
def register():
    data = body()
    email, requested_role = local_input(data)
    # The email suffix is authoritative. Legacy account_type is only a consistency check.
    account_type = data.get('account_type')
    if account_type not in (None, 'company_client', 'uploader'):
        fail(422, 'INVALID_ACCOUNT_TYPE', 'Jenis pendaftaran tidak valid.')
    if ((account_type == 'company_client' and requested_role is not None)
            or (account_type == 'uploader' and requested_role != 'CLIENT_OWNER')):
        fail(422, 'ROLE_CONFLICT', 'Klien memakai email biasa; Uploader menambahkan /uploder.')
    wants_admin = requested_role == 'SYSTEM_ADMIN'
    setup_record = None
    if email == current_app.config['ADMIN_BOOTSTRAP_EMAIL']:
        setup_record = owner_setup_record(g.db, data.get('setup_token') or session.get('owner_setup_token'), email)
        if not setup_record:
            fail(403, 'OWNER_SETUP_REQUIRED', 'Untuk membuat akun pemilik, buka tautan aktivasi dari Start-AMIGA.cmd. Jika sudah punya password, pilih Masuk.')
        if not wants_admin:
            fail(422, 'ADMIN_MARKER_REQUIRED', 'Aktivasi pertama memerlukan /admin pada email.')
    elif data.get('setup_token'):
        fail(403, 'OWNER_SETUP_INVALID', 'Tautan ini hanya berlaku untuk akun pemilik yang ditentukan.')
    user = g.db.scalar(select(User).where(User.email == email).with_for_update())
    if user and not setup_record:
        fail(409, 'EMAIL_REGISTERED', 'Email sudah terdaftar. Gunakan Masuk atau hubungi pengelola.')
    company_name = None
    if requested_role is None:
        company_name = registration_company_name(data)
    name = data.get('display_name') or email.split('@')[0]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        fail(422, 'INVALID_NAME', 'Nama harus 1–200 karakter.')
    try:
        encoded = hash_password(data.get('password'))
    except ValueError as exc:
        fail(422, 'INVALID_PASSWORD', str(exc))
    if not user:
        user = User(id=uid('usr'), email=email, display_name=name.strip(),
                    account_status=pending_status(requested_role))
        g.db.add(user)
    g.db.flush()
    g.db.add(LocalCredential(user_id=user.id, password_hash=encoded, admin_bootstrap_allowed=0))
    if setup_record:
        user.display_name, user.account_status = name.strip(), 'ACTIVE'
        g.db.add(Role(user_id=user.id, role='SYSTEM_ADMIN'))
        g.db.get(Setting, 'bootstrap_consumed').value = '1'
        setup_record.value = ''
        audit(g.db, 'ADMIN_BOOTSTRAPPED', actor_id=user.id, reason='One-use owner setup from local launcher')
    elif company_name:
        user.account_status='PENDING_COMPANY'
        g.db.add(Setting(key='company_request:'+user.id,value=company_name))
    elif requested_role == 'CLIENT_OWNER':
        create_client_workspace(user)
    elif requested_role == 'FINANCE_REVIEWER':
        request_role(user, requested_role)
    if data.get('telegram_contact'):
        if not company_name:
            fail(422, 'COMPANY_REQUIRED', 'Telegram penerima diatur pada akun perusahaan.')
        from ...telegram_config import save_contact
        try:
            save_contact(g.db, user.id, data['telegram_contact'])
        except ValueError as exc:
            fail(422, 'INVALID_TELEGRAM_CONTACT', str(exc))
    audit(g.db, 'ACCOUNT_REGISTERED', actor_id=user.id)
    return start_session(user, 201)


def registration_company_name(data):
    name = data.get('company_name')
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 200:
        fail(422, 'COMPANY_NAME_REQUIRED', 'Isi nama perusahaan 2–200 karakter untuk akun Klien, atau tambahkan /uploder untuk Uploader.')
    return name.strip()



def checked_local_password(data, password_field='password'):
    """Shared password proof and lockout for sign-in and local password changes."""
    email, requested_role = local_input(data)
    user = g.db.scalar(select(User).where(User.email == email).with_for_update())
    credential = g.db.scalar(select(LocalCredential).where(LocalCredential.user_id == user.id).with_for_update()) if user else None
    if credential and credential.locked_until and credential.locked_until > now():
        fail(429, 'LOGIN_LOCKED', 'Terlalu banyak percobaan. Coba lagi dalam 15 menit.')
    if credential and credential.locked_until:
        credential.failed_attempts, credential.locked_until = 0, None
    # Do the same password work for unknown users; never attach credentials to an existing account publicly.
    from ...local_auth import DUMMY_HASH
    valid = verify_password(data.get(password_field), credential.password_hash if credential else DUMMY_HASH)
    if not credential or not valid:
        if credential:
            credential.failed_attempts += 1
            if credential.failed_attempts >= 5:
                credential.locked_until = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
            g.db.commit()  # Failure responses otherwise roll back attempt counters.
        fail(401, 'INVALID_CREDENTIALS', 'Email atau password AMIGA salah.')
    if user.account_status == 'DISABLED':
        fail(403, 'ACCOUNT_DISABLED', 'Akun telah dinonaktifkan.')
    credential.failed_attempts, credential.locked_until = 0, None
    return user, credential, requested_role


@api.post('/auth/login')
def local_login():
    data = body()
    user, credential, requested_role = checked_local_password(data)
    email = user.email
    wants_admin = requested_role == 'SYSTEM_ADMIN'
    request_role(user, requested_role)
    bootstrap = g.db.scalar(select(Setting).where(Setting.key == 'bootstrap_consumed').with_for_update())
    if (wants_admin and email == current_app.config['ADMIN_BOOTSTRAP_EMAIL'] and credential.admin_bootstrap_allowed == 1
            and bootstrap.value == '0' and not g.db.scalar(select(Role).where(Role.role == 'SYSTEM_ADMIN').limit(1))):
        if 'FINANCE_REVIEWER' in roles(g.db, user):
            fail(403, 'ROLE_CONFLICT', 'System Admin tidak boleh sekaligus Finance Reviewer.')
        user.account_status = 'ACTIVE'
        g.db.add(Role(user_id=user.id, role='SYSTEM_ADMIN'))
        bootstrap.value, credential.admin_bootstrap_allowed = '1', 0
        audit(g.db, 'ADMIN_BOOTSTRAPPED', actor_id=user.id)
    return start_session(user)



@api.post('/auth/google')
def google_login():
    data = body()
    if current_app.config['AUTH_METHOD'] != 'google':
        fail(503, 'AUTH_METHOD_DISABLED', 'Gunakan email dan password AMIGA.')
    credential = data.get('credential')
    client_id = current_app.config['GOOGLE_CLIENT_ID']
    if not client_id:
        fail(503, 'GOOGLE_NOT_CONFIGURED', 'GOOGLE_CLIENT_ID belum dikonfigurasi di server.')
    if not isinstance(credential, str) or not 1 <= len(credential) <= 16000:
        fail(422, 'TOKEN_REQUIRED', 'Google ID token diperlukan.')
    try:
        verifier = current_app.config.get('TOKEN_VERIFIER')
        if verifier:
            claims = verifier(credential, client_id)
        else:
            from google.oauth2.id_token import verify_oauth2_token
            from google.auth.transport.requests import Request
            claims = verify_oauth2_token(credential, Request(), client_id)
        if (claims.get('aud') != client_id or claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com')
            or claims.get('email_verified') is not True or not claims.get('sub')
            or float(claims.get('exp', 0)) <= datetime.now(timezone.utc).timestamp()):
            raise ValueError('Invalid claims')
        email = str(claims['email']).strip().lower()
        if len(email) > 254 or not re.fullmatch(r'[^\s@/]+@[^\s@/]+\.[^\s@/]+', email):
            raise ValueError('Invalid email')
    except Exception:
        fail(401, 'INVALID_GOOGLE_TOKEN', 'Identitas Google tidak dapat diverifikasi. Coba login kembali.')
    email_input = data.get('email_input', '')
    try:
        supplied, requested_role = parse_identity(email_input)
    except ValueError as exc:
        fail(422, 'INVALID_EMAIL', str(exc))
    wants_admin = requested_role == 'SYSTEM_ADMIN'
    if supplied != email:
        fail(422, 'EMAIL_MISMATCH', 'Email formulir harus sama dengan akun Google yang dipilih.')
    bootstrap = g.db.scalar(select(Setting).where(Setting.key == 'bootstrap_consumed').with_for_update())
    user = g.db.scalar(select(User).where(User.google_sub == str(claims['sub'])).with_for_update())
    if user and user.email != email:
        fail(403, 'IDENTITY_CHANGED', 'Email identitas berubah; hubungi administrator untuk rekonsiliasi.')
    if not user:
        user = g.db.scalar(select(User).where(User.email == email).with_for_update())
        if user and user.google_sub and user.google_sub != str(claims['sub']):
            fail(403, 'IDENTITY_CONFLICT', 'Email telah terhubung ke identitas Google lain.')
    if not user:
        user = User(id=uid('usr'), email=email, display_name=str(claims.get('name') or email)[:200],
                    account_status=pending_status(requested_role))
        g.db.add(user)
        g.db.flush()
        if requested_role == 'CLIENT_OWNER':
            create_client_workspace(user)
        elif requested_role is None:
            user.account_status = 'PENDING_COMPANY'
            g.db.add(Setting(key='company_request:'+user.id, value=registration_company_name(data)))
    if user.account_status == 'DISABLED':
        fail(403, 'ACCOUNT_DISABLED', 'Akun telah dinonaktifkan.')
    user.google_sub = str(claims['sub'])
    request_role(user, requested_role)
    if (wants_admin and email == current_app.config['ADMIN_BOOTSTRAP_EMAIL'] and bootstrap.value == '0'
            and not g.db.scalar(select(Role).where(Role.role == 'SYSTEM_ADMIN').limit(1))):
        user.account_status = 'ACTIVE'
        g.db.add(Role(user_id=user.id, role='SYSTEM_ADMIN'))
        bootstrap.value = '1'
        audit(g.db, 'ADMIN_BOOTSTRAPPED', actor_id=user.id)
    return start_session(user)



@api.get('/auth/me')
def me():
    return ok(session_dto(g.actor, g.auth_session.expires_at))



@api.post('/auth/logout')
def logout():
    g.db.delete(g.auth_session)
    audit(g.db, 'LOGOUT', actor_id=g.actor.id)
    session.clear()
    return ok({'logged_out': True})

