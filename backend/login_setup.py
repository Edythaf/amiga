"""Save the public Google OAuth client ID, preserving other local settings."""
import os
from pathlib import Path
import re
from uuid import uuid4


def save_google_client_id(client_id, env_file):
    if not isinstance(client_id, str):
        raise ValueError('Client ID harus berupa teks.')
    client_id = client_id.strip()
    if len(client_id) > 255 or not re.fullmatch(r'\d+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', client_id):
        raise ValueError('Masukkan OAuth Client ID aplikasi Web yang berakhiran .apps.googleusercontent.com.')
    target = Path(env_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = target.read_text(encoding='utf-8-sig') if target.exists() else ''
    pattern = r'(?m)^[ \t]*(?:export[ \t]+)?GOOGLE_CLIENT_ID[ \t]*=.*$'
    entry = 'GOOGLE_CLIENT_ID=' + client_id
    if re.search(pattern, content):
        content = re.sub(pattern, entry, content)
    else:
        content = content.rstrip('\r\n') + ('\n' if content else '') + entry + '\n'
    temporary = target.with_name(target.name + '.tmp-' + uuid4().hex)
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as handle:
            handle.write(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def configure_google(env_file, client_id=None):
    if client_id is None:
        print('Authorized JavaScript origins: http://localhost dan http://localhost:5000')
        print('Google Cloud: https://console.cloud.google.com/auth/clients')
        client_id = input('Tempel OAuth Client ID (bukan password/client secret): ')
    save_google_client_id(client_id, env_file)
    print('Google Client ID tersimpan. Pengaturan admin dan database dipertahankan.')
    print('Tutup aplikasi AMIGA yang sedang berjalan, lalu jalankan ulang Start-AMIGA.cmd.')
    print('Buka http://localhost:5000/login dan gunakan Gmail admin /admin untuk aktivasi pertama.')
    print('Penyimpanan konfigurasi ini belum menyatakan login Google berhasil diverifikasi.')
