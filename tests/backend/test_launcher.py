from io import BytesIO
import unittest
from unittest.mock import patch, Mock
from backend.launcher import check_port, open_login_when_ready


class LauncherTests(unittest.TestCase):
    def test_busy_port_reports_restart_without_stopping_any_process(self):
        with patch('backend.launcher.socket.socket') as socket:
            socket.return_value.__enter__.return_value.bind.side_effect=OSError('busy')
            with self.assertRaisesRegex(ValueError,r'Ctrl\+C'):
                check_port(5000)

    def test_browser_opens_only_this_launch_with_setup_in_fragment(self):
        response=BytesIO(b'{"service":"AMIGA","run_id":"current-run"}')
        with patch('backend.launcher.urlopen',return_value=response) as request, patch('backend.launcher.webbrowser.open',return_value=True) as browser:
            thread=open_login_when_ready(5000,'current-run','fictional-setup-token')
            thread.join(2)
            self.assertFalse(thread.is_alive())
            request.assert_called_once_with('http://127.0.0.1:5000/health',timeout=.4)
            browser.assert_called_once_with('http://127.0.0.1:5000/login#owner-setup=fictional-setup-token')

    def test_another_server_never_receives_setup_fragment(self):
        with patch('backend.launcher.urlopen',side_effect=lambda *a,**k:BytesIO(b'{"service":"AMIGA","run_id":"old-run"}')), patch('backend.launcher.webbrowser.open') as browser, patch('backend.launcher.time.sleep'), patch('builtins.print'):
            thread=open_login_when_ready(5000,'current-run','fictional-token')
            thread.join(2)
            self.assertFalse(thread.is_alive())
            browser.assert_not_called()
