import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from backend.doctor import inspect_configuration, print_report


class DoctorTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / '.runtime-temp'
        root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=root)
        self.path = Path(self.directory.name) / '.env'

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_config_reports_development_separately_from_live_activation(self):
        report = inspect_configuration(self.path, environ={})
        self.assertTrue(report['development_available'])
        self.assertFalse(report['external_activation_complete'])
        self.assertEqual(report['database']['kind'], 'sqlite')
        self.assertNotIn('GOOGLE_CLIENT_ID', report['missing_configuration'])
        self.assertEqual(report['authentication']['method'], 'local_password')

    def test_bootstrap_and_marker_are_preserved_without_activating_account(self):
        self.path.write_text('ADMIN_BOOTSTRAP_EMAIL=owner@example.test\n', encoding='utf-8')
        report = inspect_configuration(self.path, environ={})
        self.assertTrue(report['first_admin']['allowlist_configured'])
        self.assertEqual(report['first_admin']['activation_marker'], '/admin')
        self.assertTrue(report['first_admin']['identity_verification_required'])
        self.assertFalse((self.path.parent / 'amiga.db').exists())

    def test_database_and_aws_secrets_never_appear_in_report(self):
        self.path.write_text('DATABASE_URL=postgresql://private_user:private_password@localhost/private_db\n'
                             'AWS_ACCESS_KEY_ID=private_access_key\nAWS_SECRET_ACCESS_KEY=private_secret_key\n', encoding='utf-8')
        with patch.dict('os.environ', {}, clear=True):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(print_report(self.path), 0)
        for secret in ('private_user', 'private_password', 'private_db', 'private_access_key', 'private_secret_key'):
            self.assertNotIn(secret, output.getvalue())
        self.assertIn('postgresql', output.getvalue())

    def test_configured_services_are_not_reported_as_verified(self):
        self.path.write_text('AI_PROVIDER=bedrock\nGOOGLE_CLIENT_ID=web-client\nADMIN_BOOTSTRAP_EMAIL=owner@example.test\n'
                             'BEDROCK_MODEL_ID=model-id\n', encoding='utf-8')
        report = inspect_configuration(self.path, environ={})
        self.assertEqual(report['missing_configuration'], [])
        self.assertFalse(report['google']['live_login_verified'])
        self.assertFalse(report['extraction']['live_extraction_verified'])

    def test_environment_precedence_and_invalid_url_do_not_expose_input(self):
        self.path.write_text('GOOGLE_CLIENT_ID=old\n', encoding='utf-8')
        report = inspect_configuration(self.path, environ={'GOOGLE_CLIENT_ID': 'new', 'DATABASE_URL': 'invalid-secret-url'})
        self.assertTrue(report['google']['client_id_present'])
        self.assertFalse(report['development_available'])
        self.assertNotIn('invalid-secret-url', json.dumps(report))
