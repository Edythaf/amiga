"""Offline configuration checks. No DDL, login, cloud call or secret output."""
import json
import os
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from .ai_config import resolve_openai_key


def inspect_configuration(env_file=None, environ=None):
    root = Path(__file__).resolve().parent
    environment = os.environ if environ is None else environ
    path = Path(env_file or environment.get('AMIGA_ENV_FILE') or root / '.env')
    values = dict(dotenv_values(path)) if path.is_file() else {}
    values.update({key: value for key, value in environment.items() if key in (
        'DATABASE_URL', 'AUTH_METHOD', 'GOOGLE_CLIENT_ID', 'ADMIN_BOOTSTRAP_EMAIL', 'BEDROCK_MODEL_ID',
        'AI_PROVIDER', 'OPENAI_MODEL', 'OPENAI_API_KEY', 'OPENAI_API_KEY_FILE', 'GPT_LUNA_API',
        'AWS_REGION', 'AWS_PROFILE', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')})
    def present(key):
        return bool(str(values.get(key) or '').strip())
    database = {'kind': 'sqlite', 'mode': 'local_development', 'configured': True,
                'connection_verified': False}
    raw_url = values.get('DATABASE_URL')
    if raw_url:
        try:
            url = make_url(raw_url)
            kind = url.get_backend_name()
            database = {'kind': kind, 'mode': 'configured_database',
                        'configured': kind in ('sqlite', 'postgresql'), 'connection_verified': False}
        except Exception:
            database = {'kind': 'invalid', 'mode': 'invalid_configuration',
                        'configured': False, 'connection_verified': False}
    auth_method = values.get('AUTH_METHOD') or 'local_password'
    provider = values.get('AI_PROVIDER') or 'openai'
    api_key_present = bool(resolve_openai_key(values))
    required = ['ADMIN_BOOTSTRAP_EMAIL']
    if provider == 'bedrock':
        required.append('BEDROCK_MODEL_ID')
    elif provider == 'openai' and not api_key_present:
        required.append('OPENAI_API_KEY')
    elif provider != 'openai':
        required.append('AI_PROVIDER')
    if auth_method == 'google':
        required.append('GOOGLE_CLIENT_ID')
    missing = [key for key in required if not present(key) or key == 'AI_PROVIDER']
    if provider == 'openai' and not api_key_present and 'OPENAI_API_KEY' not in missing:
        missing.append('OPENAI_API_KEY')
    credentials_hint = bool(environment.get('AWS_PROFILE') or values.get('AWS_PROFILE') or (
        present('AWS_ACCESS_KEY_ID') and present('AWS_SECRET_ACCESS_KEY')) or
        (Path.home() / '.aws' / 'credentials').is_file() or (Path.home() / '.aws' / 'config').is_file() or
        environment.get('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI') or environment.get('AWS_WEB_IDENTITY_TOKEN_FILE'))
    return {
        'environment_file_present': path.is_file(),
        'database': database,
        'authentication': {'method': auth_method, 'google_required': auth_method == 'google',
                           'owner_password_setup': 'Start-AMIGA.cmd opens one-use setup in browser' if auth_method == 'local_password' else None},
        'google': {'client_id_present': present('GOOGLE_CLIENT_ID'), 'live_login_verified': False},
        'first_admin': {'allowlist_configured': present('ADMIN_BOOTSTRAP_EMAIL'),
                        'activation_marker': '/admin', 'identity_verification_required': True},
        'extraction': {'provider': provider, 'model': (values.get('OPENAI_MODEL') or 'gpt-6-luna') if provider == 'openai' else values.get('BEDROCK_MODEL_ID') or None,
                       'model_id_present': bool(values.get('OPENAI_MODEL') or 'gpt-6-luna') if provider == 'openai' else present('BEDROCK_MODEL_ID'),
                       'openai_api_key_present': api_key_present,
                       'aws_provider_hint_present': credentials_hint, 'live_extraction_verified': False},
        'missing_configuration': missing,
        'development_available': database['configured'] and auth_method in ('local_password', 'google'),
        'external_activation_complete': False,
    }


def print_report(env_file=None):
    report = inspect_configuration(env_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('\nTidak ada koneksi database/cloud, perubahan skema, atau nilai rahasia yang dicetak.')
    if report['missing_configuration']:
        print('Konfigurasi yang kurang dicatat di atas. Model AI diatur terpisah dari login.')
    else:
        print('Field konfigurasi tersedia; login dan ekstraksi nyata tetap perlu diuji sebelum dianggap aktif.')
    return 0 if report['development_available'] else 1
