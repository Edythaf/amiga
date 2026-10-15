import json
import secrets

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
from werkzeug.security import generate_password_hash


admin_bp = Blueprint("admin", __name__, url_prefix="/admin/manage")
MANAGED_ROLES = {"INTAKE_SUPPORT", "FINANCE_REVIEWER"}


def _require_system_admin():
    if "SYSTEM_ADMIN" not in session.get("roles", []):
        abort(403)


def _csrf_token():
    token = session.get("admin_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["admin_csrf_token"] = token
    return token


def _check_csrf():
    expected = session.get("admin_csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not expected or not secrets.compare_digest(expected, submitted):
        abort(400, description="Token formulir tidak valid. Muat ulang halaman.")


def _connect():
    database_url = current_app.config.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL belum dikonfigurasi")
    return psycopg.connect(database_url, row_factory=dict_row)


def _write_audit(connection, action, entity_type, entity_id, new_value, old_value=None):
    # Password dan password_hash tidak dimasukkan ke audit log.
    connection.execute(
        """
        INSERT INTO audit_logs
            (actor_user_id, action, entity_type, entity_id,
             old_value, new_value, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
        """,
        (
            session.get("user_id"),
            action,
            entity_type,
            str(entity_id),
            json.dumps(old_value) if old_value is not None else None,
            json.dumps(new_value) if new_value is not None else None,
        ),
    )


def _load_admin_data():
    with _connect() as connection:
        users = connection.execute(
            """
            SELECT u.user_id, u.full_name, u.email, u.is_active, u.created_at,
                   COALESCE(STRING_AGG(ur.role_code, ', ' ORDER BY ur.role_code),
                            'Belum memiliki role') AS role_codes
            FROM users AS u
            LEFT JOIN user_roles AS ur ON ur.user_id = u.user_id
            GROUP BY u.user_id, u.full_name, u.email, u.is_active, u.created_at
            ORDER BY u.full_name, u.email
            """
        ).fetchall()

        companies = connection.execute(
            """
            SELECT company_id, company_code, company_name, is_active, created_at
            FROM companies
            ORDER BY company_name
            """
        ).fetchall()

        role_options = connection.execute(
            """
            SELECT role_code, role_name
            FROM roles
            WHERE role_code IN ('INTAKE_SUPPORT', 'FINANCE_REVIEWER')
            ORDER BY role_name
            """
        ).fetchall()

        access_rows = connection.execute(
            """
            SELECT u.full_name, u.email, c.company_name, a.granted_at
            FROM user_company_access AS a
            JOIN users AS u ON u.user_id = a.user_id
            JOIN companies AS c ON c.company_id = a.company_id
            ORDER BY c.company_name, u.full_name
            """
        ).fetchall()

    return users, companies, role_options, access_rows


@admin_bp.route("", methods=["GET", "POST"])
def manage():
    _require_system_admin()

    if request.method == "POST":
        _check_csrf()
        action = request.form.get("action", "").strip()

        try:
            if action == "create_user":
                full_name = request.form.get("full_name", "").strip()
                email = request.form.get("email", "").strip().lower()
                password = request.form.get("password", "")
                role_code = request.form.get("role_code", "").strip().upper()

                if not full_name or not email or len(password) < 12:
                    flash(
                        "Nama dan email wajib diisi. Password awal minimal 12 karakter.",
                        "error",
                    )
                    return redirect(url_for("admin.manage"))

                if role_code not in MANAGED_ROLES:
                    abort(400, description="Role akun tidak diizinkan.")

                with _connect() as connection:
                    role = connection.execute(
                        "SELECT role_code FROM roles WHERE role_code = %s",
                        (role_code,),
                    ).fetchone()

                    if role is None:
                        flash("Role belum tersedia di tabel roles.", "error")
                        return redirect(url_for("admin.manage"))

                    user = connection.execute(
                        """
                        INSERT INTO users
                            (full_name, email, password_hash, is_active,
                             created_at, updated_at)
                        VALUES (%s, %s, %s, TRUE, NOW(), NOW())
                        RETURNING user_id
                        """,
                        (
                            full_name,
                            email,
                            generate_password_hash(password),
                        ),
                    ).fetchone()

                    connection.execute(
                        """
                        INSERT INTO user_roles
                            (user_id, role_code, assigned_by, assigned_at)
                        VALUES (%s, %s, %s, NOW())
                        """,
                        (
                            user["user_id"],
                            role_code,
                            session.get("user_id"),
                        ),
                    )

                    _write_audit(
                        connection,
                        "USER_CREATED",
                        "user",
                        user["user_id"],
                        {
                            "full_name": full_name,
                            "email": email,
                            "role_code": role_code,
                        },
                    )

                flash("Akun berhasil dibuat.", "success")

            elif action == "create_company":
                company_code = request.form.get(
                    "company_code", ""
                ).strip().upper()
                company_name = request.form.get("company_name", "").strip()

                if not company_code or not company_name:
                    flash("Kode dan nama perusahaan wajib diisi.", "error")
                    return redirect(url_for("admin.manage"))

                with _connect() as connection:
                    company = connection.execute(
                        """
                        INSERT INTO companies
                            (company_code, company_name, is_active, created_at)
                        VALUES (%s, %s, TRUE, NOW())
                        RETURNING company_id
                        """,
                        (company_code, company_name),
                    ).fetchone()

                    _write_audit(
                        connection,
                        "COMPANY_CREATED",
                        "company",
                        company["company_id"],
                        {
                            "company_code": company_code,
                            "company_name": company_name,
                        },
                    )

                flash("Perusahaan berhasil didaftarkan.", "success")

            elif action == "grant_company_access":
                user_id = int(request.form.get("user_id", ""))
                company_id = int(request.form.get("company_id", ""))

                with _connect() as connection:
                    user = connection.execute(
                        """
                        SELECT user_id, full_name, email
                        FROM users
                        WHERE user_id = %s AND is_active = TRUE
                        """,
                        (user_id,),
                    ).fetchone()

                    company = connection.execute(
                        """
                        SELECT company_id, company_code, company_name
                        FROM companies
                        WHERE company_id = %s AND is_active = TRUE
                        """,
                        (company_id,),
                    ).fetchone()

                    if user is None or company is None:
                        flash("Pilih akun dan perusahaan yang aktif.", "error")
                        return redirect(url_for("admin.manage"))

                    inserted = connection.execute(
                        """
                        INSERT INTO user_company_access
                            (user_id, company_id, granted_by, granted_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT (user_id, company_id) DO NOTHING
                        RETURNING user_id
                        """,
                        (
                            user_id,
                            company_id,
                            session.get("user_id"),
                        ),
                    ).fetchone()

                    if inserted:
                        _write_audit(
                            connection,
                            "COMPANY_ACCESS_GRANTED",
                            "user_company_access",
                            f"{user_id}:{company_id}",
                            {
                                "user_id": user_id,
                                "email": user["email"],
                                "company_id": company_id,
                                "company_code": company["company_code"],
                            },
                        )

                if inserted:
                    flash("Akses perusahaan diberikan.", "success")
                else:
                    flash(
                        "Akun tersebut sudah memiliki akses ke perusahaan ini.",
                        "error",
                    )

            else:
                abort(400, description="Aksi admin tidak dikenal.")

        except psycopg.errors.UniqueViolation:
            flash("Email atau kode perusahaan sudah terdaftar.", "error")

        except (ValueError, TypeError):
            abort(400, description="Data formulir tidak valid.")

        except Exception:
            current_app.logger.exception("Operasi System Admin gagal")
            flash(
                "Perubahan gagal disimpan. Periksa konfigurasi database dan coba lagi.",
                "error",
            )

        return redirect(url_for("admin.manage"))

    try:
        users, companies, role_options, access_rows = _load_admin_data()
    except Exception:
        current_app.logger.exception("Gagal memuat data administrasi")
        users, companies, role_options, access_rows = [], [], [], []
        flash(
            "Data admin belum dapat dimuat. Periksa koneksi dan skema database.",
            "error",
        )

    return render_template(
        "admin_manage.html",
        csrf_token=_csrf_token(),
        users=users,
        companies=companies,
        role_options=role_options,
        access_rows=access_rows,
    )


@admin_bp.route("/audit", methods=["GET"])
def audit_log():
    _require_system_admin()

    try:
        with _connect() as connection:
            entries = connection.execute(
                """
                SELECT a.audit_id, a.actor_user_id, u.full_name AS actor_name,
                       a.action, a.entity_type, a.entity_id,
                       a.old_value, a.new_value, a.created_at
                FROM audit_logs AS a
                LEFT JOIN users AS u ON u.user_id = a.actor_user_id
                ORDER BY a.created_at DESC, a.audit_id DESC
                LIMIT 250
                """
            ).fetchall()
    except Exception:
        current_app.logger.exception("Gagal memuat audit log")
        entries = []
        flash(
            "Audit log belum dapat dimuat. Periksa koneksi dan skema database.",
            "error",
        )

    return render_template("admin_audit.html", entries=entries)