"""Application factory. Run: python -m backend.manage serve"""
import os
import secrets
from datetime import timedelta
from pathlib import Path
from flask import g, request, session, jsonify, send_from_directory
from dotenv import load_dotenv
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException
from .models import Base, Setting


class ApiFault(Exception):
    def __init__(self, status, code, message, fields=None):
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}


def configure_workspace(app, overrides=None):
    root = Path(__file__).resolve().parent
    load_dotenv(os.getenv('AMIGA_ENV_FILE') or root / '.env', override=False)
    production = os.getenv('AMIGA_ENV', 'development') == 'production'
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY'), PRODUCTION=production,
        DATABASE_URL=os.getenv('DATABASE_URL') or 'sqlite:///' + (root / 'storage' / 'amiga.db').as_posix(),
        UPLOAD_DIR=Path(os.getenv('UPLOAD_DIR') or root / 'storage' / 'documents'),
        GOOGLE_CLIENT_ID=os.getenv('GOOGLE_CLIENT_ID', '').strip(),
        AUTH_METHOD=os.getenv('AUTH_METHOD', 'local_password').strip(),
        RUN_ID=os.getenv('AMIGA_RUN_ID', ''),
        ADMIN_BOOTSTRAP_EMAIL=os.getenv('ADMIN_BOOTSTRAP_EMAIL', '').strip().lower(),
        AWS_REGION=os.getenv('AWS_REGION', 'ap-southeast-1'),
        BEDROCK_MODEL_ID=os.getenv('BEDROCK_MODEL_ID', '').strip(),
        AI_PROVIDER=os.getenv('AI_PROVIDER', 'openai').strip(),
        OPENAI_MODEL=os.getenv('OPENAI_MODEL', 'gpt-6-luna').strip(),
        AGENT_MODEL=os.getenv('AGENT_MODEL', 'gpt-6-luna').strip(),
        AGENT_DAILY_LIMIT=int(os.getenv('AGENT_DAILY_LIMIT', '60')),
        TELEGRAM_BOT_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN', '').strip(),
        TELEGRAM_BOT_USERNAME=os.getenv('TELEGRAM_BOT_USERNAME', '').strip().lstrip('@'),
        START_QUEUE_WORKER=os.getenv('START_QUEUE_WORKER', '1') == '1',
        SESSION_HOURS=int(os.getenv('SESSION_HOURS', '8')), SESSION_COOKIE_NAME='amiga_local_review_session', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=production,
        MAX_CONTENT_LENGTH=32 * 1024 * 1024, FILE_LIMIT=10 * 1024 * 1024, PAGE_LIMIT=5,
        IDR_TOLERANCE='1', DEFAULT_TOLERANCE='0.01',
    )
    app.config.update(overrides or {})
    if 'OPENAI_API_KEY' not in (overrides or {}):
        from .ai_config import resolve_openai_key
        app.config['OPENAI_API_KEY'] = '' if app.testing else resolve_openai_key()
    if app.config['AI_PROVIDER'] not in ('openai', 'bedrock'):
        raise RuntimeError('AI_PROVIDER must be openai or bedrock.')
    if app.config['AUTH_METHOD'] not in ('local_password', 'google'):
        raise RuntimeError('AUTH_METHOD must be local_password or google.')
    if not 1 <= app.config['SESSION_HOURS'] <= 24:
        raise RuntimeError('SESSION_HOURS must be between 1 and 24.')
    if any(app.config.get(key) for key in ('TOKEN_VERIFIER','EXTRACTOR','REVIEW_ANALYZER','INITIAL_ANALYZER','AGENT_RESPONDER','TELEGRAM_TRANSPORT','SIGNATURE_ANALYZER','TAX_ANALYZER')) and not app.testing:
        raise RuntimeError('Injected identity/extraction is permitted only in isolated tests.')
    if app.config['PRODUCTION'] and (not app.config['SECRET_KEY'] or len(app.config['SECRET_KEY']) < 32 or not app.config['SESSION_COOKIE_SECURE']
                                   or not app.config['DATABASE_URL'].startswith('postgresql')):
        raise RuntimeError('Production requires SECRET_KEY, secure cookies and PostgreSQL.')
    storage = Path(app.config['UPLOAD_DIR'])
    storage.mkdir(parents=True, exist_ok=True)
    if not app.config['SECRET_KEY']:
        keyfile = storage.parent / '.session-secret'
        try:
            with keyfile.open('x', encoding='ascii') as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config['SECRET_KEY'] = keyfile.read_text(encoding='ascii').strip()
    app.permanent_session_lifetime = timedelta(hours=app.config['SESSION_HOURS'])
    url = app.config['DATABASE_URL']
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    engine = create_engine(url, connect_args={'timeout': 20, 'check_same_thread': False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def pragmas(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    # Development SQLite can initialize itself. Existing PostgreSQL databases
    # require an explicit init-db command after reviewing the additive migration.
    initialize = app.config.get('INIT_SCHEMA', engine.dialect.name == 'sqlite')
    if initialize:
        Base.metadata.create_all(engine)
        from .schema import ensure_workflow_columns
        ensure_workflow_columns(engine)
    else:
        from sqlalchemy import inspect
        if not inspect(engine).has_table('amiga_settings'):
            engine.dispose()
            raise RuntimeError('Workspace schema is missing. Review migrations/001_workspace.sql, then run backend.manage init-db explicitly.')
    factory = sessionmaker(engine, expire_on_commit=False)
    app.extensions['amiga_db'], app.extensions['amiga_engine'] = factory, engine
    with factory.begin() as db:
        if engine.dialect.name == 'sqlite':db.execute(text('BEGIN IMMEDIATE'))
        if db.get(Setting, 'schema_version') is None:
            db.add(Setting(key='schema_version', value='8'))
        elif db.get(Setting, 'schema_version').value in ('1', '2', '3', '4', '5', '6', '7') and initialize:
            db.get(Setting, 'schema_version').value = '8'
        elif db.get(Setting, 'schema_version').value != '8':
            raise RuntimeError('Unsupported database schema. Apply the reviewed migration first.')
        if db.get(Setting, 'bootstrap_consumed') is None:
            db.add(Setting(key='bootstrap_consumed', value='0'))

        from .request_numbers import backfill_request_numbers
        backfill_request_numbers(db)

    @app.before_request
    def prepare():
        g.db = factory()
        g.actor = None
        if request.path.startswith('/api/'):
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if engine.dialect.name == 'sqlite':
                    g.db.execute(text('BEGIN IMMEDIATE'))
                token, expected = request.headers.get('X-CSRF-Token', ''), session.get('csrf', '')
                if not token or not expected or not secrets.compare_digest(token, expected):
                    raise ApiFault(403, 'CSRF', 'Sesi formulir tidak valid. Muat ulang halaman.')
            if request.path not in ('/api/auth/csrf', '/api/auth/google', '/api/auth/login', '/api/auth/register', '/api/auth/owner-setup', '/api/auth/password/change', '/api/auth/password/reset'):
                from .api import authenticate
                authenticate()
                if request.path not in ('/api/auth/me', '/api/auth/logout') and g.actor.account_status != 'ACTIVE':
                    raise ApiFault(403, 'ACCOUNT_INACTIVE', 'Akun belum aktif atau telah dinonaktifkan.')

    @app.after_request
    def finish(response):
        if hasattr(g, 'db'):
            if response.status_code < 400:
                g.db.commit()
            else:
                g.db.rollback()
                for path in g.get('new_files', []):
                    path.unlink(missing_ok=True)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = ('strict-origin-when-cross-origin' if app.config['PRODUCTION']
                                              else 'no-referrer-when-downgrade')
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin-allow-popups'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        if not app.config['PRODUCTION'] and (request.path in ('/', '/login', '/admin', '/reviewer', '/client', '/uploader', '/pending') or request.path.startswith('/portal/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.teardown_request
    def close(error):
        if hasattr(g, 'db'):
            g.db.close()
        if error:
            for path in g.get('new_files', []):
                path.unlink(missing_ok=True)

    @app.errorhandler(ApiFault)
    def fault(exc):
        return jsonify(error={'code': exc.code, 'message': exc.message, 'fields': exc.fields}), exc.status

    @app.errorhandler(IntegrityError)
    def conflict(exc):
        g.db.rollback()
        return fault(ApiFault(409, 'CONFLICT', 'Data berubah atau sudah terdaftar. Muat ulang.'))

    @app.errorhandler(OperationalError)
    def unavailable(exc):
        g.db.rollback()
        return fault(ApiFault(503, 'DATABASE_UNAVAILABLE', 'Database sedang tidak tersedia atau sibuk.'))

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith('/api/'):
            return fault(ApiFault(exc.code, 'HTTP_' + str(exc.code), exc.description))
        return exc

    from .api import api
    app.register_blueprint(api)
    portal = root.parent / 'frontend' / 'portal'
    @app.get('/')
    @app.get('/login')
    @app.get('/admin')
    @app.get('/reviewer')
    @app.get('/client')
    @app.get('/uploader')
    @app.get('/pending')
    def portal_page():
        return send_from_directory(portal, 'index.html')

    @app.get('/portal/<path:name>')
    def portal_asset(name):
        return send_from_directory(portal, name)

    @app.get('/health')
    def health():
        return jsonify(status='ok', service='AMIGA', backend_source='amiga-20261015T221710Z-1-001', schema_version=8, review_workflow='uploader_confirmation_v2', auth_method=app.config['AUTH_METHOD'], run_id=app.config['RUN_ID'],
                       ai_provider=app.config['AI_PROVIDER'], ai_model=app.config['OPENAI_MODEL'] if app.config['AI_PROVIDER']=='openai' else app.config['BEDROCK_MODEL_ID'])

    if app.config['START_QUEUE_WORKER'] and not app.testing:
        from .modules.upload.queue_worker import start_worker
        start_worker(app)
    return app


def create_app(overrides=None):
    """Compatibility import; the ZIP-derived backend.app owns app creation."""
    from .app import create_app as primary_factory
    return primary_factory(overrides)
