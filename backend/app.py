import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from backend.modules.upload.queue_worker import start_queue_worker
from backend.modules.upload.routes import upload_bp


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
        MAX_CONTENT_LENGTH=None,
        UPLOAD_DIR=backend_dir / "storage" / "uploads",
        DATABASE_URL=os.getenv("DATABASE_URL", "").strip(),
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

    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    app.register_blueprint(upload_bp)

    is_reloader_parent = (
        app.debug
        and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
    )

    if not is_reloader_parent:
        start_queue_worker(app)

    return app