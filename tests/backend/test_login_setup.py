import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from dotenv import dotenv_values
from backend.login_setup import save_google_client_id, configure_google

CLIENT = '1234567890-isolated-test-client.apps.googleusercontent.com'


class LoginSetupTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / '.runtime-temp'
        root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.path = Path(self.directory.name) / '.env'

    def tearDown(self):
        self.directory.cleanup()

    def test_saves_public_client_id_and_preserves_admin_database_and_secret(self):
        self.path.write_text('GOOGLE_CLIENT_ID=\nADMIN_BOOTSTRAP_EMAIL=owner@example.test\n'
                             'DATABASE_URL=postgresql://owner:private_password@localhost/amiga\nSECRET_KEY=private_secret\n', encoding='utf-8')
        before = dotenv_values(self.path)
        save_google_client_id(CLIENT, self.path)
        after = dotenv_values(self.path)
        self.assertEqual(after.pop('GOOGLE_CLIENT_ID'), CLIENT)
        before.pop('GOOGLE_CLIENT_ID')
        self.assertEqual(after, before)
        self.assertEqual(list(self.path.parent.glob('.env.tmp-*')), [])

    def test_invalid_client_never_changes_file(self):
        self.path.write_text('ADMIN_BOOTSTRAP_EMAIL=owner@example.test\n', encoding='utf-8')
        original = self.path.read_bytes()
        for value in ['', 'owner@gmail.com', 'password', CLIENT + '\nSECRET_KEY=injected', None]:
            with self.assertRaises(ValueError):
                save_google_client_id(value, self.path)
            self.assertEqual(self.path.read_bytes(), original)

    def test_new_file_contains_no_account_activation_or_fabricated_secret(self):
        save_google_client_id(CLIENT, self.path)
        self.assertEqual(dict(dotenv_values(self.path)), {'GOOGLE_CLIENT_ID': CLIENT})
        self.assertFalse((self.path.parent / 'amiga.db').exists())

    def test_report_does_not_expose_existing_secrets(self):
        self.path.write_text('SECRET_KEY=private_secret\n', encoding='utf-8')
        output = io.StringIO()
        with redirect_stdout(output):
            configure_google(self.path, CLIENT)
        self.assertNotIn('private_secret', output.getvalue())
        self.assertIn('belum menyatakan login Google berhasil', output.getvalue())

    def test_duplicate_assignments_are_consistent_after_update(self):
        self.path.write_text('GOOGLE_CLIENT_ID=old\nexport GOOGLE_CLIENT_ID=another\n', encoding='utf-8')
        save_google_client_id(CLIENT, self.path)
        self.assertEqual(self.path.read_text(encoding='utf-8').count('GOOGLE_CLIENT_ID=' + CLIENT), 2)
