import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, request, session, url_for
from werkzeug.serving import is_running_from_reloader

from backend.modules.auth.routes import auth_bp
from backend.modules.upload.queue_worker import start_queue_worker
from backend.modules.upload.routes import upload_bp
from backend.modules.admin.routes import admin_bp

def create_app():
    backend_dir = Path(__file__).resolve().parent
    project_dir = backend_dir.parent
    frontend_dir = project_dir / "frontend"

    load_dotenv(backend_dir / ".env")

    app = Flask(
        __name__,
        template_folder=str(frontend_dir / "templates"),
        static_folder=str(frontend_dir / "static"),
        static_url_path="/static",
    )

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        DATABASE_URL=os.getenv("DATABASE_URL", "").strip(),
        MAX_CONTENT_LENGTH=None,
        UPLOAD_DIR=backend_dir / "storage" / "uploads",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        S3_BUCKET=os.getenv("S3_BUCKET", ""),
        AWS_REGION=os.getenv("AWS_REGION", "ap-southeast-1"),
        S3_PREFIX=os.getenv("S3_PREFIX", "amiga-invoices"),
        BEDROCK_MODEL_ID=os.getenv(
            "BEDROCK_MODEL_ID",
            "apac.anthropic.claude-sonnet-4-20250514-v1:0",
        ),
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(upload_bp)

    @app.before_request
    def require_login():
        endpoint = request.endpoint

        # Izinkan halaman login dan file statis dibuka tanpa login.
        if endpoint in {"auth.login", "static"}:
            return None

        # Endpoint internal tanpa nama juga tidak perlu dialihkan.
        if endpoint is None:
            return None

        if not session.get("user_id"):
            return redirect(url_for("auth.login"))

        return None

    # Cegah queue worker dimulai dua kali saat Flask memakai reloader.
    if not app.debug or is_running_from_reloader():
        start_queue_worker(app)

    return app