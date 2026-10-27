"""Primary-source admin entry adapted to AMIGA's masked, one-time provisioning.

Run: python -m backend.create_admin. The owner chooses their own password;
no embedded test account, default password or direct native-PostgreSQL writes.
The normal launcher browser setup is preferred.
"""
from .app import create_app
from .local_auth import setup_admin


def main():
    app = create_app({'START_QUEUE_WORKER': False})
    try:
        setup_admin(app)
    finally:
        app.extensions['amiga_engine'].dispose()


if __name__ == '__main__':
    main()
