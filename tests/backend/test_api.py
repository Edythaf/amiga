"""Isolated integration tests. Google/AWS are injected ONLY with TESTING=True."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from sqlalchemy import select, delete, func, text
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas
from backend.app import create_app
from backend.models import (User, Role, Client, Membership, WorkRequest, Document,
                            Invoice, InvoiceVersion, Extraction, Voucher, Handover, Review, Audit, AuthSession)
from backend.processing import process_one, claim
from backend.repository import fields_for
from backend.validation import normalize, validate, InvalidDraft

ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS = {
    'company': ('company.a@example.test', ['COMPANY_CLIENT'], ['A']),
    'company2': ('company.second@example.test', ['COMPANY_CLIENT'], ['A']),
    'company_other': ('company.b@example.test', ['COMPANY_CLIENT'], ['B']),
    'owner': ('owner.a@example.test', ['CLIENT_OWNER'], ['A']),
    'other': ('owner.b@example.test', ['CLIENT_OWNER'], ['B']),
    'finance': ('finance@example.test', ['FINANCE_REVIEWER'], ['A', 'B']),
    'finance2': ('finance2@example.test', ['FINANCE_REVIEWER'], ['A']),
    'lead': ('lead@example.test', ['SERVICE_LEAD'], ['A']),
    'admin': ('admin@example.test', ['SYSTEM_ADMIN'], ['A']),
    'dual': ('dual@example.test', ['CLIENT_OWNER', 'FINANCE_REVIEWER'], ['A']),
}


def invoice_fields(number='INV-A'):
    return dict(vendor_name='Vendor <Uji> & Rekan', invoice_number=number, invoice_date='2026-01-02',
        due_date=None, currency='IDR', subtotal='220.20', invoice_discount_amount='10.10',
        invoice_tax_amount='0', total_amount='210.10', bank_name='Bank Fiktif', account_number='0000123',
        account_holder='Vendor Uji', line_items=[dict(description='Barang <b> & jasa', quantity='2',
            unit_price='100.10', discount_amount='0', tax_amount='20', line_total='220.20')])


def pdf_bytes(label='Invoice', pages=1):
    output = BytesIO()
    canvas = Canvas(output)
    for _ in range(pages):
        canvas.drawString(50, 700, label)
        canvas.showPage()
    canvas.save()
    return output.getvalue()


class ApiTests(unittest.TestCase):
    def setUp(self):
        temp_root = ROOT / '.runtime-temp'
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.path = Path(self.temp.name)
        self.extractions = 0
        self.rows = [invoice_fields()]
        def extractor(path, config):
            self.extractions += 1
            return {'invoices': copy.deepcopy(self.rows), 'ocr_text': 'immutable OCR original'}
        self.claims = {key: {'sub': 'sub_' + key, 'email': email, 'email_verified': True,
                             'aud': 'test-client', 'iss': 'https://accounts.google.com',
                             'exp': datetime.now(timezone.utc).timestamp() + 3600, 'name': key}
                       for key, (email, _, _) in ACCOUNTS.items()}
        self.app = create_app(dict(TESTING=True, START_QUEUE_WORKER=False, SECRET_KEY='isolated-test-key',
            DATABASE_URL='sqlite:///' + (self.path / 'test.db').as_posix(), UPLOAD_DIR=self.path / 'documents',
            AUTH_METHOD='google', AI_PROVIDER='bedrock', OPENAI_API_KEY='', GOOGLE_CLIENT_ID='test-client', TOKEN_VERIFIER=lambda token, aud: self.claims[token], EXTRACTOR=extractor))
        self.app.config['INITIAL_ANALYZER']=lambda *args:{'analysis':{'summary':'Fixture: bandingkan data dengan sumber.','risk':'LOW','findings':[],'next_steps':['Periksa dokumen.']},'model':'fixture-only'}
        with self.app.extensions['amiga_db'].begin() as db:
            db.add_all([Client(id='A', name='Klien A'), Client(id='B', name='Klien B')])
            for key, (email, user_roles, assignments) in ACCOUNTS.items():
                db.add(User(id=key, email=email, display_name=key, account_status='ACTIVE'))
            db.flush()
            for key, (_, user_roles, assignments) in ACCOUNTS.items():
                db.add_all([Role(user_id=key, role=r) for r in user_roles])
                db.add_all([Membership(user_id=key, client_id=c) for c in assignments])
        self.clients = {}

    def tearDown(self):
        self.app.extensions['amiga_engine'].dispose()
        self.temp.cleanup()

    def login(self, account='owner', email_input=None, expect=200):
        client = self.app.test_client()
        csrf = client.get('/api/auth/csrf').json['data']['csrf_token']
        response = client.post('/api/auth/google', json={'credential': account,
            'email_input': email_input or self.claims[account]['email']}, headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, expect, response.json)
        if response.status_code == 200:
            client.csrf_token = response.json['data']['csrf_token']
            self.clients[account] = client
        return client, response

    def actor(self, name):
        return self.clients.get(name) or self.login(name)[0]

    def call(self, name, method, url, data=None, json=None):
        client = self.actor(name)
        return client.open(url, method=method, json=json, data=data, headers={'X-CSRF-Token': client.csrf_token})

    def upload(self, account='owner', client_id='A', content=None, evidence=True, expect=201):
        data = {'client_id': client_id, 'request_type': 'Invoice vendor', 'channel': 'Portal',
                'request_date': '2026-01-01', 'deadline': '2026-01-05',
                'invoice_file': (BytesIO(content or pdf_bytes()), 'invoice.pdf')}
        if evidence:
            data['evidence_files[]'] = (BytesIO(pdf_bytes('Bukti')), 'bukti.pdf')
        response = self.call(account, 'POST', '/api/requests', data=data)
        self.assertEqual(response.status_code, expect, response.json)
        return response.json.get('data')

    def processed(self, **kwargs):
        req = self.upload(**kwargs)
        self.assertTrue(process_one(self.app, req['id']))
        return self.actor(kwargs.get('account', 'owner')).get('/api/requests/' + req['id']).json['data']

    def revise(self, req, account='owner', fields=None, **extra):
        inv = req['invoices'][0]
        return self.call(account, 'PATCH', f"/api/requests/{req['id']}/invoices/{inv['id']}",
            json={'expected_version': inv['current_version'], 'fields': fields or inv['fields'],
                  'item_count_confirmed': True, 'reason': 'Seluruh item dibandingkan dengan PDF.', **extra})

    def decision(self, req, account='finance', action='approve', **data):
        if action=='approve':self.prepare_review(req)
        inv = req['invoices'][0]
        return self.call(account, 'POST', f"/api/requests/{req['id']}/invoices/{inv['id']}/{action}",
                         json={'expected_version': inv['current_version'], **data})

    def take(self, req, account='finance'):
        self.prepare_review(req)
        response = self.call(account, 'POST', f"/api/tasks/{req['id']}/claim", json={})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['data']

    def prepare_review(self,req):
        """Unrelated legacy tests enter the same real uploader gate as the UI."""
        from backend.initial_analysis import process_initial_one
        while process_initial_one(self.app,req['id']):pass
        actor=req.get('uploaded_by','owner')
        current=self.actor(actor).get('/api/requests/'+req['id']).json.get('data')
        if not current:return
        versions={i['id']:i['current_version'] for i in current['invoices']}
        requested=[i['id'] for i in req['invoices']]
        if any(versions.get(i['id'])!=i['current_version'] for i in req['invoices']):return
        for inv in current['invoices']:
            if not inv['uploader_confirmation']['confirmed'] and inv['initial_analysis']['state']=='READY':
                response=self.call(actor,'POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/confirm-uploader",json={
                    'expected_version':inv['current_version'],'acknowledged':True,'item_count_confirmed':True})
                if response.status_code==200:current=response.json['data']
        req.update({**current,'invoices':[i for i in current['invoices'] if i['id'] in requested]})

    def confirmed(self, **kwargs):
        req = self.processed(**kwargs)
        response = self.revise(req)
        self.assertEqual(response.status_code, 200, response.json)
        req['invoices'][0] = response.json['data']
        self.prepare_review(req)
        return req

    def test_portal_and_legacy_routes(self):
        client = self.app.test_client()
        for route in ['/login', '/admin', '/client', '/pending', '/portal/src/js/portal.js']:
            response = client.get(route)
            self.assertEqual(response.status_code, 200)
            response.close()
        for route in ['/queue/data', '/abc/original', '/abc/review', '/abc/voucher/preview.pdf', '/backend/storage/amiga.db']:
            self.assertEqual(client.get(route).status_code, 404)
        self.assertEqual(client.get('/api/requests').status_code, 401)
        headers = client.get('/api/auth/csrf').headers
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer-when-downgrade')
        self.assertEqual(headers['Cross-Origin-Opener-Policy'], 'same-origin-allow-popups')

    def test_csrf_rotation_logout_and_claim_checks(self):
        client = self.app.test_client()
        self.assertEqual(client.post('/api/auth/google', json={}).status_code, 403)
        token = client.get('/api/auth/csrf').json['data']['csrf_token']
        self.assertEqual(client.post('/api/auth/google', json={'credential': 'owner', 'email_input': 'wrong@example.test'}, headers={'X-CSRF-Token': token}).status_code, 422)
        for key, value in [('aud', 'wrong'), ('iss', 'evil'), ('email_verified', False), ('exp', 0)]:
            original = self.claims['owner'][key]
            self.claims['owner'][key] = value
            self.assertEqual(client.post('/api/auth/google', json={'credential': 'owner', 'email_input': self.claims['owner']['email']}, headers={'X-CSRF-Token': token}).status_code, 401)
            self.claims['owner'][key] = original
        client, response = self.login()
        self.assertNotEqual(token, response.json['data']['csrf_token'])
        cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        self.assertEqual(client.post('/api/auth/logout', json={}, headers={'X-CSRF-Token': 'wrong'}).status_code, 403)
        self.assertEqual(self.call('owner', 'POST', '/api/auth/logout', json={}).status_code, 200)
        self.assertEqual(client.get('/api/auth/me').status_code, 401)

    def test_admin_is_request_and_persistent_admin_role(self):
        self.claims['new'] = {**self.claims['owner'], 'sub': 'new-sub', 'email': 'new@example.test'}
        client, response = self.login('new', 'new@example.test /admin')
        self.assertEqual(response.json['data']['user']['account_status'], 'PENDING_ADMIN')
        self.assertEqual(response.json['data']['user']['roles'], [])
        self.assertEqual(client.get('/api/requests').status_code, 403)
        self.assertEqual(client.get('/api/auth/me').status_code, 200)
        _, response = self.login('admin')
        self.assertEqual(response.json['data']['portal'], 'admin')
        self.assertIn('SYSTEM_ADMIN', response.json['data']['user']['roles'])

    def test_first_admin_requires_allowlist_and_cannot_repeat(self):
        with self.app.extensions['amiga_db'].begin() as db:
            db.execute(delete(Role).where(Role.user_id == 'admin'))
        self.app.config['ADMIN_BOOTSTRAP_EMAIL'] = 'first@example.test'
        self.claims['first'] = {**self.claims['owner'], 'sub': 'first-sub', 'email': 'first@example.test'}
        _, response = self.login('first', 'first@example.test /admin')
        self.assertEqual(response.json['data']['user']['roles'], ['SYSTEM_ADMIN'])
        self.assertEqual(response.json['data']['user']['email'], 'first@example.test')
        _, response = self.login('first')
        self.assertEqual(response.json['data']['portal'], 'admin')
        self.app.config['ADMIN_BOOTSTRAP_EMAIL'] = 'second@example.test'
        self.claims['second'] = {**self.claims['first'], 'sub': 'second-sub', 'email': 'second@example.test'}
        _, response = self.login('second', 'second@example.test /admin')
        self.assertEqual(response.json['data']['user']['account_status'], 'PENDING_ADMIN')

    def test_tenant_isolation_all_object_routes(self):
        req = self.processed()
        inv, doc = req['invoices'][0], req['documents'][0]
        other = self.actor('other')
        self.assertEqual(other.get('/api/requests').json['data']['total'], 0)
        base = '/api/requests/' + req['id']
        for route in [base, base + '/audit', base + '/documents/' + doc['id'],
                      base + '/invoices/' + inv['id'] + '/voucher/preview.pdf']:
            self.assertEqual(other.get(route).status_code, 404, route)
        for action in ['validate', 'approve', 'reject', 'resolve', 'voucher/download']:
            response = self.call('other', 'POST', base + '/invoices/' + inv['id'] + '/' + action,
                                 json={'expected_version': 1, 'reason': 'Tidak boleh'})
            self.assertEqual(response.status_code, 404, action)
        self.assertEqual(self.call('other', 'PATCH', base + '/invoices/' + inv['id'], json={'expected_version': 1}).status_code, 404)
        self.upload(account='other', client_id='A', expect=403)
        response = self.actor('owner').get(base + '/documents/' + doc['id'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        response.get_data()
        response.close()

    def test_pdf_checks_are_atomic(self):
        self.upload(content=b'%PDF-not-valid', expect=422)
        self.upload(content=pdf_bytes(pages=6), expect=422)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt('password')
        output = BytesIO()
        writer.write(output)
        self.upload(content=output.getvalue(), expect=422)
        self.assertEqual(self.actor('owner').get('/api/requests').json['data']['total'], 0)
        self.assertEqual(list((self.path / 'documents').iterdir()), [])

    def test_revalidation_does_not_extract_and_raw_never_changes(self):
        req = self.confirmed()
        self.take(req)
        inv = req['invoices'][0]
        self.assertEqual(self.extractions, 1)
        response = self.decision(req, account='owner', action='validate')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data']['current_version'], 2)
        self.assertEqual(self.extractions, 1)
        with self.app.extensions['amiga_db']() as db:
            raw = db.scalar(select(Extraction)).payload
            self.assertEqual(raw['ocr_text'], 'immutable OCR original')
            self.assertEqual(raw['invoices'][0], invoice_fields())
            self.assertEqual(db.scalar(select(func.count()).select_from(InvoiceVersion)), 2)
        stale = self.call('finance', 'POST', f"/api/requests/{req['id']}/invoices/{inv['id']}/approve", json={'expected_version': 1})
        self.assertEqual(stale.status_code, 409)

    def test_approval_roles_independence_and_validation(self):
        self.rows[0]['bank_name']=None
        req = self.processed()
        for actor in ['owner', 'admin', 'lead']:
            self.assertEqual(self.decision(req, account=actor).status_code, 403)
        self.take(req)
        self.assertEqual(self.decision(req).status_code, 422)  # missing bank still blocks approval after uploader confirmation
        own = self.processed(account='dual', content=pdf_bytes('Different'))
        self.assertEqual(self.decision(own, account='dual').status_code, 403)
        response = self.call('finance', 'POST', '/api/requests/' + req['id'] + '/evidence',
                             data={'evidence_file': (BytesIO(pdf_bytes('Finance uploaded')), 'evidence.pdf')})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.decision(req, account='finance').status_code, 403)
        with self.app.extensions['amiga_db'].begin() as db:
            db.add(Role(user_id='finance2', role='SYSTEM_ADMIN'))
        self.assertEqual(self.decision(req, account='finance2').status_code, 403)

    def test_bank_revision_requires_same_request_evidence(self):
        req = self.processed()
        changed = copy.deepcopy(req['invoices'][0]['fields'])
        changed['account_number'] = '0000999'
        self.assertEqual(self.revise(req, fields=changed).status_code, 422)
        foreign = self.processed(content=pdf_bytes('Foreign evidence'))
        foreign_doc = next(d for d in foreign['documents'] if d['type'] == 'EVIDENCE')
        self.assertEqual(self.revise(req, fields=changed, field_sources={'account_number': {'document_id': foreign_doc['id'], 'source_type': 'EVIDENCE'}}).status_code, 422)
        own_doc = next(d for d in req['documents'] if d['type'] == 'EVIDENCE')
        response = self.revise(req, fields=changed, field_sources={'account_number': {'document_id': own_doc['id'], 'source_type': 'EVIDENCE'}})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['data']['fields']['account_number'], '0000999')

    def test_duplicate_resolution_is_versioned_and_math_not_overridable(self):
        original_pdf = pdf_bytes()
        first = self.confirmed(content=original_pdf)
        second = self.confirmed(content=pdf_bytes('Different bytes'))
        self.take(second)
        inv = second['invoices'][0]
        self.assertIn('POSSIBLE_DUPLICATE', [i['code'] for i in inv['validation']['issues']])
        self.assertEqual(self.decision(second).status_code, 422)
        base = f"/api/requests/{second['id']}/invoices/{inv['id']}/resolve"
        self.assertEqual(self.call('owner', 'POST', base, json={'expected_version': 2, 'issue_code': 'POSSIBLE_DUPLICATE', 'reason': 'Test'}).status_code, 403)
        self.assertEqual(self.call('finance', 'POST', base, json={'expected_version': 2, 'issue_code': 'TOTAL_MISMATCH', 'reason': 'Test'}).status_code, 422)
        resolved = self.call('finance', 'POST', base, json={'expected_version': 2, 'issue_code': 'POSSIBLE_DUPLICATE', 'reason': 'Tagihan berbeda telah diperiksa dari bukti.'})
        self.assertEqual(resolved.status_code, 200, resolved.json)
        self.assertTrue(resolved.json['data']['validation']['valid'])
        response = self.revise(second, fields={**inv['fields'], 'due_date': '2026-02-01'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json['data']['validation']['valid'])
        third = self.processed(content=original_pdf)
        self.assertIn('DUPLICATE_FILE', [i['code'] for i in third['invoices'][0]['validation']['issues']])

    def test_pdf_approval_snapshot_handover_and_revision(self):
        req = self.confirmed()
        self.take(req)
        inv = req['invoices'][0]
        base = f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/"
        draft = self.actor('owner').get(base + 'preview.pdf?version=2')
        self.assertIn('DRAFT', ''.join(p.extract_text() for p in PdfReader(BytesIO(draft.data)).pages))
        self.assertEqual(self.call('company', 'POST', base + 'download', json={'expected_version': 2}).status_code, 403)
        self.assertEqual(self.decision(req).status_code, 200)
        self.assertEqual(self.actor('owner').get('/api/requests/' + req['id']).json['data']['status'], 'AMIGA_REVIEWED')
        preview = self.actor('owner').get(base + 'preview.pdf?version=2')
        text_content = ''.join(p.extract_text() for p in PdfReader(BytesIO(preview.data)).pages)
        self.assertNotIn('DRAFT', text_content)
        self.assertIn('0000123', text_content)
        self.assertIn('Persetujuan pembayaran', text_content)
        self.assertIn('Barang <b> & jasa', text_content)
        official = self.call('company', 'POST', base + 'download', json={'expected_version': 2})
        self.assertEqual(official.status_code, 200)
        self.assertEqual(official.data, preview.data)
        self.assertTrue(official.headers['X-Voucher-ID'])
        self.assertEqual(self.actor('owner').get('/api/requests/' + req['id']).json['data']['status'], 'SENT_TO_CLIENT')
        self.assertEqual(self.revise(req, fields={**inv['fields'], 'vendor_name': 'Vendor Uji Terkoreksi'}).status_code, 200)
        self.assertEqual(self.call('company', 'POST', base + 'download', json={'expected_version': 3}).status_code, 403)
        historical = self.actor('owner').get(base + 'preview.pdf?version=2')
        self.assertEqual(historical.data, official.data)
        with self.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Voucher)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(Handover)), 1)
            self.assertEqual(db.scalar(select(Review)).validation_snapshot['version'], 2)

    def test_multi_invoice_requires_all_handover(self):
        self.rows = [invoice_fields('INV-A'), invoice_fields('INV-B')]
        req = self.processed()
        self.assertEqual(len(req['invoices']), 2)
        self.take(req)
        approved = []
        for inv in req['invoices']:
            single = {**req, 'invoices': [inv]}
            revised = self.revise(single, fields={**inv['fields'], 'vendor_name': 'Vendor Uji Terkoreksi'})
            self.assertEqual(revised.status_code, 200, revised.json)
            single['invoices'][0] = revised.json['data']
            self.assertEqual(self.decision(single).status_code, 200)
            approved.append(single['invoices'][0])
        self.assertEqual(self.actor('owner').get('/api/requests/' + req['id']).json['data']['status'], 'AMIGA_REVIEWED')
        for index, inv in enumerate(approved):
            result = self.call('company', 'POST', f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download", json={'expected_version': 2})
            self.assertEqual(result.status_code, 200)
            status = self.actor('owner').get('/api/requests/' + req['id']).json['data']['status']
            self.assertEqual(status, 'SENT_TO_CLIENT' if index == 1 else 'AMIGA_REVIEWED')

    def test_assignment_and_account_administration(self):
        req = self.confirmed()
        base = '/api/requests/' + req['id'] + '/assignment'
        self.assertEqual(self.call('admin', 'PATCH', base, json={'pic_id': 'finance'}).status_code, 200)
        self.assertEqual(self.call('lead', 'PATCH', base, json={'pic_id': 'owner'}).status_code, 422)
        self.assertEqual(self.call('lead', 'PATCH', base, json={'pic_id': 'finance2'}).status_code, 200)
        self.assertEqual(self.decision(req, account='finance').status_code, 404)
        self.assertEqual(self.actor('owner').get('/api/admin/users').status_code, 403)
        self.assertEqual(self.call('admin', 'PATCH', '/api/admin/users/admin', json={'account_status': 'DISABLED'}).status_code, 403)
        self.assertEqual(self.call('admin', 'PATCH', '/api/admin/users/finance', json={'roles': ['SYSTEM_ADMIN', 'FINANCE_REVIEWER']}).status_code, 422)
        target = self.actor('owner')
        self.assertEqual(self.call('admin', 'PATCH', '/api/admin/users/owner', json={'account_status': 'DISABLED'}).status_code, 200)
        self.assertEqual(target.get('/api/auth/me').status_code, 401)
        with self.app.extensions['amiga_db']() as db:
            self.assertTrue(db.scalar(select(Audit).where(Audit.action == 'USER_ACCESS_UPDATED')))

    def test_reextract_is_explicit_preserves_history_and_failed_config_visible(self):
        self.rows = [invoice_fields('INV-A'), invoice_fields('INV-B')]
        req = self.processed()
        url = '/api/requests/' + req['id'] + '/process'
        self.assertEqual(self.call('owner', 'POST', url, json={'mode': 'REEXTRACT', 'expected_version': 1, 'reason': 'Baca ulang'}).status_code, 409)
        expected = {inv['id']: inv['current_version'] for inv in req['invoices']}
        self.assertEqual(self.call('owner', 'POST', url, json={'mode': 'REEXTRACT', 'expected_versions': expected, 'reason': 'Baca ulang PDF'}).status_code, 200)
        process_one(self.app, req['id'])
        self.assertEqual(self.extractions, 2)
        with self.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Extraction)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(Invoice)), 4)
        self.app.config['EXTRACTOR'] = None
        failed = self.upload(content=pdf_bytes('Unconfigured'))
        self.app.config['BEDROCK_MODEL_ID'] = ''
        process_one(self.app, failed['id'])
        result = self.actor('owner').get('/api/requests/' + failed['id']).json['data']
        self.assertEqual(result['status'], 'EXCEPTION')
        self.assertEqual(result['processing']['error_code'], 'EXTRACTION_NOT_CONFIGURED')
        self.assertEqual(result['invoices'], [])

    def test_queue_claim_and_simultaneous_revision_conflict(self):
        req = self.processed()
        self.take(req)
        inv = req['invoices'][0]
        self.assertIsNone(claim(self.app, req['id']))
        self.actor('owner')
        self.actor('finance')
        def revise_actor(actor):
            return self.revise(req, actor, fields={**inv['fields'], 'vendor_name': 'Vendor revisi '+actor}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(revise_actor, ['owner', 'finance']))
        self.assertEqual(sorted(results), [200, 409])
        with self.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(InvoiceVersion)), 2)

    def test_email_dots_and_plus_not_collapsed_and_expired_session(self):
        self.claims['plus'] = {**self.claims['owner'], 'sub': 'plus-sub', 'email': 'a.b+work@example.test'}
        _, response = self.login('plus', email_input='a.b+work@example.test/uploder')
        self.assertEqual(response.json['data']['user']['email'], 'a.b+work@example.test')
        self.assertEqual(response.json['data']['portal'], 'uploader')
        owner = self.actor('owner')
        with self.app.extensions['amiga_db'].begin() as db:
            for record in db.scalars(select(AuthSession).where(AuthSession.user_id == 'owner')):
                record.expires_at = '2000-01-01T00:00:00Z'
        self.assertEqual(owner.get('/api/auth/me').status_code, 401)

    def test_new_google_company_has_no_membership_and_suffix_cannot_change_it(self):
        self.claims['new_company'] = {**self.claims['owner'], 'sub': 'new-company-sub', 'email': 'new.company@example.test'}
        client = self.app.test_client()
        token = client.get('/api/auth/csrf').json['data']['csrf_token']
        response = client.post('/api/auth/google', json={'credential':'new_company',
            'email_input':'new.company@example.test', 'company_name':'PT Demo'}, headers={'X-CSRF-Token':token})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['data']['user']['account_status'],'PENDING_COMPANY')
        self.assertEqual(response.json['data']['user']['clients'],[])
        self.assertEqual(response.json['data']['user']['roles'],[])
        self.assertEqual(client.get('/api/requests').status_code,403)
        self.login('new_company',email_input='new.company@example.test/uploder',expect=403)

    def test_bad_dependency_injection_rejected_outside_tests(self):
        with self.assertRaises(RuntimeError):
            create_app({'TESTING': False, 'TOKEN_VERIFIER': lambda a, b: {}, 'START_QUEUE_WORKER': False})

    def test_real_google_verifier_checks_signature_with_offline_test_certificate(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from datetime import timedelta
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from google.auth import jwt, crypt
        import json
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AMIGA isolated test certificate')])
        current = datetime.now(timezone.utc)
        cert = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()) \
            .serial_number(x509.random_serial_number()).not_valid_before(current - timedelta(days=1)) \
            .not_valid_after(current + timedelta(days=1)).sign(key, hashes.SHA256())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        signer = crypt.RSASigner.from_string(pem, key_id='isolated-key')
        claims = {**self.claims['owner'], 'iat': int(current.timestamp()) - 10, 'exp': int(current.timestamp()) + 300}
        signed = jwt.encode(signer, claims).decode('ascii')
        self.app.config['TOKEN_VERIFIER'] = None
        certificates = json.dumps({'isolated-key': cert.public_bytes(serialization.Encoding.PEM).decode('ascii')}).encode()
        transport = lambda *args, **kwargs: SimpleNamespace(status=200, data=certificates)
        client = self.app.test_client()
        csrf = client.get('/api/auth/csrf').json['data']['csrf_token']
        with patch('google.auth.transport.requests.Request', return_value=transport):
            response = client.post('/api/auth/google', json={'credential': signed, 'email_input': claims['email']}, headers={'X-CSRF-Token': csrf})
            self.assertEqual(response.status_code, 200, response.json)
            token_parts = signed.split('.')
            token_parts[-1] = ('A' if token_parts[-1][0] != 'A' else 'B') + token_parts[-1][1:]
            response = client.post('/api/auth/google', json={'credential': '.'.join(token_parts), 'email_input': claims['email']}, headers={'X-CSRF-Token': response.json['data']['csrf_token']})
            self.assertEqual(response.status_code, 401, response.json)

    def test_retained_sources_become_manual_on_edit_and_clear_is_honored(self):
        req = self.processed()
        inv = req['invoices'][0]
        changed = copy.deepcopy(inv['fields'])
        changed['vendor_name'] = 'Vendor corrected'
        response = self.revise(req, fields=changed, field_sources=inv['field_sources'])
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['data']['field_sources']['vendor_name']['source_type'], 'MANUAL')
        req['invoices'][0] = response.json['data']
        response = self.revise(req, field_sources={'account_number': None})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIn('ACCOUNT_SOURCE_REQUIRED', [i['code'] for i in response.json['data']['validation']['issues']])

    def test_simultaneous_approval_creates_one_voucher(self):
        req = self.confirmed()
        self.take(req)
        clients = [self.login('finance')[0], self.login('finance')[0]]
        inv = req['invoices'][0]
        def approve(client):
            return client.post(f"/api/requests/{req['id']}/invoices/{inv['id']}/approve",
                json={'expected_version': inv['current_version']}, headers={'X-CSRF-Token': client.csrf_token}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(approve, clients))
        self.assertEqual(sorted(results), [200, 409])
        with self.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Voucher)), 1)

    def test_legacy_data_and_session_survive_factory_restart(self):
        client = self.actor('owner')
        cookie = client.get_cookie('amiga_local_review_session').value
        with self.app.extensions['amiga_engine'].begin() as connection:
            connection.execute(text('CREATE TABLE queue_items (document_id TEXT PRIMARY KEY, status TEXT)'))
            connection.execute(text("INSERT INTO queue_items VALUES ('legacy-private', 'APPROVED')"))
        other_app = create_app({**self.app.config, 'START_QUEUE_WORKER': False})
        try:
            other_client = other_app.test_client()
            other_client.set_cookie('amiga_local_review_session', cookie)
            self.assertEqual(other_client.get('/api/auth/me').status_code, 200)
            self.assertEqual(other_client.get('/api/requests').json['data']['total'], 0)
            with other_app.extensions['amiga_engine'].connect() as connection:
                self.assertEqual(connection.execute(text('SELECT status FROM queue_items')).scalar_one(), 'APPROVED')
        finally:
            other_app.extensions['amiga_engine'].dispose()

    def test_failed_extraction_keeps_raw_instead_of_partial_invoices(self):
        self.rows = [invoice_fields(), {**invoice_fields('INV-B'), 'total_amount': 'NaN'}]
        req = self.processed()
        self.assertEqual(req['status'], 'EXCEPTION')
        self.assertEqual(req['invoices'], [])
        with self.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(Extraction)).payload['invoices'][1]['total_amount'], 'NaN')

    def test_rejected_invoice_requires_revision_before_new_approval(self):
        req = self.confirmed()
        self.take(req)
        result = self.decision(req, action='reject', reason='Periksa kembali data rekening.')
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['data']['review_status'], 'REJECTED')
        self.assertNotIn('APPROVE', result.json['data']['allowed_actions'])
        # A rejection is terminal for this revision, so it cannot be silently reversed.
        self.assertEqual(self.decision(req).status_code, 409)
        revised = self.revise(req, fields={**req['invoices'][0]['fields'], 'vendor_name': 'Vendor Uji Terkoreksi'})
        self.assertEqual(revised.status_code, 200)
        req['invoices'][0] = revised.json['data']
        self.assertEqual(self.decision(req).status_code, 200)

    def test_process_requires_real_integer_versions_not_null_or_boolean(self):
        req = self.processed()
        inv = req['invoices'][0]
        url = '/api/requests/' + req['id'] + '/process'
        for bad in [None, True, '1']:
            response = self.call('owner', 'POST', url, json={'mode': 'REVALIDATE', 'invoice_id': inv['id'], 'expected_version': bad})
            self.assertEqual(response.status_code, 422)
        response = self.call('owner', 'POST', url, json={'mode': 'REEXTRACT', 'expected_versions': {inv['id']: True}, 'reason': 'Uji versi boolean'})
        self.assertEqual(response.status_code, 422)

    def test_invalid_source_id_is_validation_error_instead_of_server_error(self):
        req = self.processed()
        response = self.revise(req, field_sources={'account_number': {'document_id': [], 'source_type': 'EVIDENCE'}})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json['error']['code'], 'INVALID_SOURCE')


class ValidationTests(unittest.TestCase):
    def test_exact_decimal_discounts_and_no_double_tax(self):
        fields = normalize(invoice_fields())
        result = validate(fields, 1, 1)
        self.assertTrue(result['valid'], result)
        self.assertEqual(result['calculated']['total'], '210.10')
        self.assertEqual(result['calculated']['delta'], '0.00')

    def test_unknown_and_nonfinite_never_become_zero(self):
        for value in ['NaN', 'Infinity', '-1', True, 0.1, '1e6', '1,000']:
            draft = invoice_fields()
            draft['total_amount'] = value
            with self.assertRaises(InvalidDraft, msg=str(value)):
                normalize(draft)
        draft = invoice_fields()
        draft['invoice_tax_amount'] = None
        result = validate(normalize(draft), 1, 1)
        self.assertFalse(result['valid'])
        self.assertIsNone(result['calculated']['total'])

    def test_mismatch_missing_items_and_large_exact_values(self):
        draft = invoice_fields()
        draft['total_amount'] = '250'
        self.assertIn('TOTAL_MISMATCH', [i['code'] for i in validate(normalize(draft), 1, 1)['issues']])
        draft['line_items'] = []
        self.assertFalse(validate(normalize(draft), 1, 0)['valid'])


if __name__ == '__main__':
    unittest.main()
