"""Local launch helpers. Never stop an unrelated process or expose setup tokens in logs."""
import json
import socket
import threading
import time
from urllib.request import urlopen
import webbrowser


def check_port(port):
    if not 1 <= port <= 65535:
        raise ValueError('Port harus 1–65535.')
    try:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', port))
    except OSError as exc:
        raise ValueError(f'Port {port} sedang dipakai. Tutup terminal AMIGA lama dengan Ctrl+C, lalu jalankan Start-AMIGA.cmd lagi.') from exc


def open_login_when_ready(port, run_id, setup_token=None):
    """Open only after this launch answers health, including under the reloader."""
    origin = f'http://127.0.0.1:{port}'
    def open_page():
        for _ in range(60):
            try:
                with urlopen(origin + '/health', timeout=.4) as response:
                    value = json.load(response)
                if value.get('service') == 'AMIGA' and value.get('run_id') == run_id:
                    target = origin + '/login' + ('#owner-setup=' + setup_token if setup_token else '')
                    if not webbrowser.open(target):
                        print('Browser belum terbuka. Jalankan Start-AMIGA.cmd dari terminal Windows biasa.')
                    return
            except (OSError, ValueError, webbrowser.Error):
                pass
            time.sleep(.5)
        print('AMIGA belum merespons. Periksa apakah terminal server lama masih terbuka, lalu jalankan ulang launcher.')
    thread = threading.Thread(target=open_page, name='amiga-browser-launch', daemon=True)
    thread.start()
    return thread
