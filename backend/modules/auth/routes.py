from urllib.parse import urlsplit

import psycopg
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from psycopg.rows import dict_row
from werkzeug.security import check_password_hash


auth_bp = Blueprint("auth", __name__)


def _safe_next_url(target):
    if not target:
        return None

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return None

    if not target.startswith("/") or target.startswith("//"):
        return None

    return target


def _default_destination(roles):
    if "SYSTEM_ADMIN" in roles:
        return url_for("auth.admin_dashboard")

    if roles.intersection({"INTAKE_SUPPORT", "FINANCE_REVIEWER"}):
        return url_for("upload.queue_page")

    return url_for("auth.login")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_next_url(request.form.get("next") or request.args.get("next"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        database_url = current_app.config.get("DATABASE_URL")

        try:
            with psycopg.connect(database_url, row_factory=dict_row) as connection:
                user = connection.execute(
                    """
                    SELECT user_id, full_name, password_hash, is_active
                    FROM users
                    WHERE LOWER(email) = %s
                    """,
                    (email,),
                ).fetchone()

                if (
                    user is None
                    or not user["is_active"]
                    or not check_password_hash(user["password_hash"], password)
                ):
                    flash("Email atau password tidak cocok.", "error")
                    return render_template("login.html", next_url=next_url)

                role_rows = connection.execute(
                    """
                    SELECT role_code
                    FROM user_roles
                    WHERE user_id = %s
                    ORDER BY role_code
                    """,
                    (user["user_id"],),
                ).fetchall()

        except Exception:
            current_app.logger.exception("Login gagal mengakses database")
            flash("Login belum dapat diproses. Coba lagi.", "error")
            return render_template("login.html", next_url=next_url)

        roles = {row["role_code"] for row in role_rows}
        session.clear()
        session["user_id"] = user["user_id"]
        session["full_name"] = user["full_name"]
        session["roles"] = sorted(roles)

        # Jangan biarkan akun admin diarahkan ke alur Intake Support melalui next URL.
        if "SYSTEM_ADMIN" in roles:
            return redirect(url_for("auth.admin_dashboard"))

        return redirect(next_url or _default_destination(roles))

    return render_template("login.html", next_url=next_url)


@auth_bp.route("/admin", methods=["GET"])
def admin_dashboard():
    if "SYSTEM_ADMIN" not in session.get("roles", []):
        abort(403)

    return render_template("admin_dashboard.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
