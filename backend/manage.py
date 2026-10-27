"""Local administrative CLI. Never exposes email-only login through HTTP."""
import argparse
import os
from pathlib import Path
import re
import secrets
from sqlalchemy import select, delete
from .app import create_app
from .models import User, Client, Role, Membership, AuthSession, uid
from .repository import audit, roles


def main():
    parser = argparse.ArgumentParser(description='AMIGA local backend management')
    parser.add_argument('--env-file', help='Read an existing .env without copying its secrets')
    commands = parser.add_subparsers(dest='command', required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--port', type=int, default=5000)
    serve.add_argument('--open-browser', action='store_true', help='Open the login page; first owner creates a password in the form')
    serve.add_argument('--reload', action='store_true', help='Reload local Python source changes without enabling the debugger')
    commands.add_parser('init-db')
    commands.add_parser('work-once')
    commands.add_parser('check-ai', help='Make one real extraction call with a fictional test PDF; API usage is billed by provider')
    commands.add_parser('doctor', help='Inspect configuration offline without exposing secrets or initializing a database')
    commands.add_parser('setup-admin', help='Create the first owner password locally once, using masked input')
    login_parser = commands.add_parser('configure-google', help='Save a Web OAuth client ID without changing accounts or database')
    login_parser.add_argument('--client-id', help='Public Google OAuth Web client ID; prompted when omitted')
    client_parser = commands.add_parser('create-client')
    client_parser.add_argument('--name', required=True)
    user_parser = commands.add_parser('provision-user')
    user_parser.add_argument('--email', required=True)
    user_parser.add_argument('--role', required=True, choices=['SYSTEM_ADMIN', 'FINANCE_REVIEWER', 'SERVICE_LEAD', 'CLIENT_OWNER', 'CLIENT_BACKUP'])
    user_parser.add_argument('--client', action='append', default=[])
    args = parser.parse_args()
    if args.env_file:
        env_file = Path(args.env_file).resolve()
        if not env_file.is_file():
            parser.error('.env file not found')
        os.environ['AMIGA_ENV_FILE'] = str(env_file)
    if args.command == 'doctor':
        from .doctor import print_report
        raise SystemExit(print_report(args.env_file))
    if args.command == 'configure-google':
        from .login_setup import configure_google
        target = args.env_file or os.environ.get('AMIGA_ENV_FILE') or Path(__file__).resolve().parent / '.env'
        try:
            configure_google(target, args.client_id)
        except (ValueError, EOFError) as exc:
            parser.error(str(exc))
        return
    reloader_child = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if args.command == 'serve' and not reloader_child:
        from .launcher import check_port
        try:
            check_port(args.port)
        except ValueError as exc:
            parser.error(str(exc))
        os.environ['AMIGA_RUN_ID'] = secrets.token_urlsafe(16)
    options = {'START_QUEUE_WORKER': False}
    if args.command == 'init-db':
        options['INIT_SCHEMA'] = True
    app = create_app(options)
    if args.command == 'setup-admin':
        from .local_auth import setup_admin
        try:
            setup_admin(app)
        except (ValueError, EOFError) as exc:
            parser.error(str(exc))
    elif args.command == 'serve':
        use_reload = args.reload and not app.config['PRODUCTION']
        if os.getenv('START_QUEUE_WORKER', '1') == '1' and (not use_reload or reloader_child):
            from .processing import start_worker
            start_worker(app)
        if args.open_browser and not reloader_child:
            from .local_auth import prepare_owner_setup
            from .launcher import open_login_when_ready
            try:
                setup_token = prepare_owner_setup(app)
            except ValueError as exc:
                parser.error(str(exc))
            if setup_token:
                print('Halaman aktivasi pemilik akan terbuka. Buat passwordmu sendiri pada formulir AMIGA.')
            open_login_when_ready(args.port, app.config['RUN_ID'], setup_token)
        print('AMIGA: http://127.0.0.1:' + str(args.port) + '/login | Ctrl+C untuk berhenti')
        app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=use_reload, reloader_type='stat')
    elif args.command == 'init-db':
        print('Skema amiga_* siap. Tabel legacy tetap disimpan.')
    elif args.command == 'work-once':
        from .processing import process_one
        from .initial_analysis import process_initial_one
        print('Processed' if process_one(app) or process_initial_one(app) else 'Queue empty')
    elif args.command == 'check-ai':
        from .ai_check import print_check
        raise SystemExit(print_check(app))
    else:
        with app.extensions['amiga_db'].begin() as db:
            if args.command == 'create-client':
                if not 2 <= len(args.name.strip()) <= 200:
                    parser.error('Nama klien harus 2–200 karakter.')
                client = Client(id=uid('cli'), name=args.name.strip())
                db.add(client)
                print(client.id)
                audit(db, 'CLI_CLIENT_CREATED', changes=[{'field': 'client', 'before': None, 'after': client.id}])
            else:
                email = args.email.strip().lower()
                if not re.fullmatch(r'[^\s@/]+@[^\s@/]+\.[^\s@/]+', email):
                    parser.error('Email tidak valid; simpan tanpa /admin.')
                if args.role in ('CLIENT_OWNER', 'CLIENT_BACKUP') and not args.client:
                    parser.error('--client wajib untuk peran ini.')
                if any(not db.get(Client, c) for c in args.client):
                    parser.error('ID klien tidak ditemukan.')
                user = db.scalar(select(User).where(User.email == email))
                if not user:
                    user = User(id=uid('usr'), email=email, display_name=email, account_status='ACTIVE')
                    db.add(user)
                    db.flush()
                current_roles = roles(db, user)
                if {args.role, *current_roles} >= {'SYSTEM_ADMIN', 'FINANCE_REVIEWER'}:
                    parser.error('System Admin tidak boleh sekaligus Finance Reviewer.')
                if args.role not in current_roles:
                    db.add(Role(user_id=user.id, role=args.role))
                for client_id in set(args.client):
                    if not db.get(Membership, (user.id, client_id)):
                        db.add(Membership(user_id=user.id, client_id=client_id))
                user.account_status = 'ACTIVE'
                db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                audit(db, 'CLI_USER_PROVISIONED', reason='Local operator provisioned verified-login account',
                      changes=[{'field': 'user', 'before': None, 'after': {'id': user.id, 'email': email, 'role': args.role, 'clients': args.client}}])
                print(user.id + ': provisioned; credentials are still required at login.')


if __name__ == '__main__':
    main()
