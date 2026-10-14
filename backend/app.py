import secrets
from pathlib import Path
import os
from dotenv import load_dotenv

from flask import Flask

from backend.modules.upload.routes import upload_bp


def create_app():
    app = Flask(__name__)

    backend_dir = Path(__file__).resolve().parent
    load_dotenv(backend_dir / ".env")

    app.config.update(
        # Kunci sesi sementara untuk pengembangan lokal.
        SECRET_KEY=secrets.token_hex(32),

        # Tidak menetapkan batas ukuran upload.
        MAX_CONTENT_LENGTH=None,

        # File disimpan di luar folder publik.
        UPLOAD_DIR=backend_dir / "storage" / "uploads",

        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        S3_BUCKET=os.getenv("S3_BUCKET", ""),
        AWS_REGION=os.getenv("AWS_REGION", "ap-southeast-1"),
        S3_PREFIX=os.getenv("S3_PREFIX", "amiga-invoices"),
        BEDROCK_MODEL_ID=os.getenv("BEDROCK_MODEL_ID", "apac.anthropic.claude-sonnet-4-20250514-v1:0",),
    )

    app.config["UPLOAD_DIR"].mkdir(
        parents=True,
        exist_ok=True,
    )

    app.register_blueprint(upload_bp)

    return app