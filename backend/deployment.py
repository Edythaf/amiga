"""EC2 entry point: keep production checks separate from the local launcher."""
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from dotenv import dotenv_values, load_dotenv
from sqlalchemy.engine import make_url

STATIC_AWS = ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
              'AWS_PROFILE', 'AWS_DEFAULT_PROFILE')


def deployment_errors(values):
    errors = []
    lab_demo = values.get('AMIGA_ENV') == 'lab_demo'
    if values.get('AMIGA_ENV') not in ('production', 'lab_demo'):
        errors.append('PRODUCTION_MODE_REQUIRED')
    if lab_demo and values.get('AMIGA_LAB_HTTP_ACK') != '1':
        errors.append('LAB_HTTP_ACK_REQUIRED')
    if len(values.get('SECRET_KEY') or '') < 32 or 'CHANGE_ME' in (values.get('SECRET_KEY') or ''):
        errors.append('SECRET_KEY_REQUIRED')
    try:
        database = make_url(values.get('DATABASE_URL') or '')
        if database.get_backend_name() != 'postgresql' or not database.database or not database.username:
            errors.append('POSTGRESQL_REQUIRED')
    except Exception:
        errors.append('POSTGRESQL_REQUIRED')
    try:
        origin = urlsplit(values.get('PUBLIC_BASE_URL') or '')
        invalid_origin = (origin.scheme != ('http' if lab_demo else 'https') or not origin.hostname or origin.username or origin.password
                          or origin.query or origin.fragment or origin.path not in ('', '/')
                          or 'change_me' in origin.hostname.lower() or origin.port == 0)
    except ValueError:
        invalid_origin = True
    if invalid_origin:
        errors.append('LAB_HTTP_ENDPOINT_REQUIRED' if lab_demo else 'HTTPS_ENDPOINT_REQUIRED')
    for name in ('AMIGA_ENV_FILE', 'UPLOAD_DIR'):
        path = values.get(name) or ''
        if not path or not PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts:
            errors.append(name + '_ABSOLUTE_PATH_REQUIRED')
    if any(values.get(name) for name in STATIC_AWS):
        errors.append('EC2_INSTANCE_ROLE_REQUIRED')
    if values.get('AI_PROVIDER') != 'bedrock':
        errors.append('BEDROCK_REQUIRED')
    if values.get('AWS_REGION') != 'us-east-1':
        errors.append('MENTOR_REGION_REVIEW_REQUIRED')
    if values.get('BEDROCK_MODEL_ID') != 'us.amazon.nova-lite-v1:0':
        errors.append('US_NOVA_LITE_REVIEW_REQUIRED')
    if values.get('AGENT_MODEL') != 'gpt-6-luna':
        errors.append('LUNA_AGENT_REQUIRED')
    if not (values.get('OPENAI_API_KEY') or values.get('OPENAI_API_KEY_FILE')):
        errors.append('LUNA_CREDENTIAL_REQUIRED')
    if not values.get('ADMIN_BOOTSTRAP_EMAIL'):
        errors.append('OWNER_EMAIL_REQUIRED')
    return errors


def read_deployment_values(path, environ=None):
    values = dict(dotenv_values(path)) if Path(path).is_file() else {}
    values.update(os.environ if environ is None else environ)
    return values


def create_server():
    path = os.environ.get('AMIGA_ENV_FILE', '')
    if not path or not Path(path).is_file():
        raise RuntimeError('EC2_ENV_FILE_REQUIRED')
    load_dotenv(path, override=False)
    errors = deployment_errors(os.environ)
    if errors:
        raise RuntimeError('EC2_CONFIGURATION: ' + ', '.join(errors))
    from .app import create_app
    origin = urlsplit(os.environ['PUBLIC_BASE_URL'])
    app = create_app({'TRUSTED_HOSTS': [origin.hostname, 'localhost', '127.0.0.1']})
    if os.environ.get('AMIGA_ENV') == 'lab_demo':
        @app.after_request
        def label_lab(response):
            response.headers['X-AMIGA-Environment'] = 'lab_demo'
            return response
    return app
