from getpass import getpass
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash


def main():
    backend_dir = Path(__file__).resolve().parent
    load_dotenv(backend_dir / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL belum diatur di backend/.env")

    full_name = input("Nama System Admin: ").strip()
    email = input("Email: ").strip().lower()
    password = getpass("Password (minimal 12 karakter): ")
    password_confirmation = getpass("Ulangi password: ")

    if not full_name or not email:
        raise SystemExit("Nama dan email harus diisi.")
    if len(password) < 12:
        raise SystemExit("Password harus minimal 12 karakter.")
    if password != password_confirmation:
        raise SystemExit("Password tidak sama.")

    password_hash = generate_password_hash(password)

    with psycopg.connect(database_url) as connection:
        role = connection.execute(
            "SELECT role_code FROM roles WHERE role_code = 'SYSTEM_ADMIN'"
        ).fetchone()

        if role is None:
            raise SystemExit("Role SYSTEM_ADMIN belum ada di database.")

        existing_user = connection.execute(
            "SELECT user_id FROM users WHERE LOWER(email) = %s",
            (email,),
        ).fetchone()

        if existing_user:
            raise SystemExit("Email tersebut sudah terdaftar.")

        user_row = connection.execute(
            """
            INSERT INTO users (full_name, email, password_hash)
            VALUES (%s, %s, %s)
            RETURNING user_id
            """,
            (full_name, email, password_hash),
        ).fetchone()

        user_id = user_row[0]

        connection.execute(
            """
            INSERT INTO user_roles (user_id, role_code)
            VALUES (%s, 'SYSTEM_ADMIN')
            """,
            (user_id,),
        )

    print(f"Akun System Admin berhasil dibuat untuk {email}.")


if __name__ == "__main__":
    main()