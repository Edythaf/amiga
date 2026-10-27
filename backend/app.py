"""AMIGA primary backend, rebased on amiga-20261015T221710Z-1-001.zip.

The supplied Flask/module layout is the entry point. The existing portal API is
installed as a compatibility/security extension over the same database/session.
The ZIP auth/admin/upload controllers are adapted to one shared REST contract;
there is no second session-only HTML login that could bypass access checks.
"""
from pathlib import Path
from flask import Flask
from .application import configure_workspace, ApiFault


def create_app(overrides=None):
    backend_dir = Path(__file__).resolve().parent
    frontend_dir = backend_dir.parent / 'frontend'
    app = Flask(__name__, template_folder=str(frontend_dir / 'templates'),
                static_folder=str(frontend_dir / 'static'), static_url_path='/static')
    app.config['BACKEND_SOURCE'] = 'amiga-20261015T221710Z-1-001'
    return configure_workspace(app, overrides)
