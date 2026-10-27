"""Lifecycle tests use the real HTTP policy and isolated, disposable SQLite."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func
import test_api
from backend.models import Voucher, Audit, RequestLifecycle, Setting, User, InvoiceVersion
from backend.application import create_app


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.a = test_api.ApiTests()
        self.a.setUp()

    def tearDown(self):
        self.a.tearDown()

    def detail(self, req):
        return self.a.actor('owner').get('/api/requests/' + req['id']).json['data']

    def transition(self, req, action='CLOSE', actor='company', **overrides):
        payload = dict(action=action, reason='Hasil sudah diperiksa oleh klien.',
                       expected_lifecycle_revision=req['lifecycle']['revision'],
                       expected_versions={i['id']: i['current_version'] for i in req['invoices']})
        payload.update(overrides)
        return self.a.call(actor, 'POST', f"/api/requests/{req['id']}/lifecycle", json=payload)

    def download(self, req, actor='company', index=0):
        inv = req['invoices'][index]
        return self.a.call(actor, 'POST', f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download",
                           json={'expected_version': inv['current_version']})

    def ready(self):
        req = self.a.take(self.a.confirmed())
        self.assertEqual(self.a.decision(req).status_code, 200)
        self.assertEqual(self.download(req).status_code, 200)
        return self.detail(req)

    def test_progress_is_responsibility_not_automatic_validation(self):
        req = self.a.processed()
        self.assertEqual(req['work_status'], 'WAITING_UPLOADER')
        req = self.a.take(req)
        self.assertEqual(req['work_status'], 'IN_REVIEW')
        self.a.decision(req, action='reject', reason='Lengkapi rincian biaya.')
        self.assertEqual(self.detail(req)['work_status'], 'WAITING_CLIENT')
        self.assertEqual(self.a.revise(req, fields={**req['invoices'][0]['fields'], 'vendor_name': 'Vendor Uji Terkoreksi'}).status_code, 200)
        self.assertEqual(self.detail(req)['work_status'], 'WAITING_UPLOADER')

    def test_only_client_can_close_after_all_latest_vouchers_downloaded(self):
        req = self.a.take(self.a.confirmed())
        self.assertEqual(self.transition(req).status_code, 409)
        self.a.decision(req)
        self.assertEqual(self.detail(req)['work_status'], 'VOUCHER_READY')
        self.download(req, 'finance')
        self.assertEqual(self.transition(req).status_code, 409)
        self.download(req)
        req = self.detail(req)
        self.assertEqual(req['work_status'], 'AWAITING_CLIENT_CLOSE')
        for actor, status in [('finance',403), ('admin',403), ('lead',403), ('other',404)]:
            self.assertEqual(self.transition(req, actor=actor).status_code, status)
        closed = self.transition(req)
        self.assertEqual(closed.status_code, 200, closed.json)
        self.assertEqual(closed.json['data']['lifecycle']['state'], 'CLOSED')
        self.assertEqual(closed.json['data']['status'], 'SENT_TO_CLIENT')
        self.assertEqual(closed.json['data']['work_status'], 'CLOSED')
        self.assertEqual(self.download(req).status_code, 200)

    def test_closed_mutations_blocked_but_history_pdf_and_download_retained(self):
        req = self.ready()
        self.transition(req)
        closed = self.detail(req)
        self.assertNotIn('EDIT', closed['invoices'][0]['allowed_actions'])
        self.assertEqual(self.a.revise(req).status_code, 409)
        self.assertEqual(self.a.decision(req).status_code, 409)
        base = '/api/requests/' + req['id']
        for suffix, data in [('/process', {'mode':'REEXTRACT'}),('/evidence', {})]:
            response = self.a.call('owner','POST',base+suffix,json=data)
            self.assertEqual(response.json['error']['code'], 'REQUEST_CLOSED')
        self.assertEqual(self.a.actor('owner').get(base+'/audit').status_code,200)
        self.assertEqual(self.a.actor('finance2').get('/api/tasks').json['data']['total'],0)
        self.assertEqual(self.a.call('admin','PATCH',base+'/assignment',json={'pic_id':'finance2'}).status_code,409)

    def test_reopen_creates_pending_versions_preserves_history_and_releases_disabled_pic(self):
        req = self.ready()
        req = self.transition(req).json['data']
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.get(User,'finance').account_status='DISABLED'
            old_pdf = db.scalar(select(Voucher)).pdf
        response = self.transition(req, 'REQUEST_REVISION', reason='Sesuaikan rincian biaya kedua.')
        self.assertEqual(response.status_code,200,response.json)
        fresh = response.json['data']
        self.assertEqual(fresh['work_status'],'WAITING_UPLOADER')
        self.assertEqual(fresh['lifecycle']['state'],'OPEN')
        self.assertEqual(fresh['invoices'][0]['review_status'],'PENDING')
        self.assertEqual(fresh['invoices'][0]['current_version'],3)
        self.assertIsNone(fresh['invoices'][0]['expected_item_count'])
        self.assertEqual(fresh['client_revision_note'],'Sesuaikan rincian biaya kedua.')
        self.assertEqual(self.download(fresh).status_code,403)
        self.assertEqual(self.transition(fresh).status_code,409)
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(Voucher)).pdf,old_pdf)
            self.assertEqual(db.scalar(select(func.count()).select_from(InvoiceVersion)),3)
            self.assertEqual(db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='CLIENT_REVISION_REQUESTED')),1)
        self.a.take(fresh,'finance2')

    def test_stale_lifecycle_and_invoice_versions_cannot_close_new_work(self):
        req = self.ready()
        self.assertEqual(self.transition(req, expected_lifecycle_revision=True).status_code,422)
        self.assertEqual(self.transition(req, expected_versions={}).status_code,409)
        fresh = self.transition(req,'REQUEST_REVISION').json['data']
        self.assertEqual(self.transition(req).status_code,409)
        self.assertEqual(self.transition(fresh,'REQUEST_REVISION').status_code,409)

    def test_double_close_has_one_winner_and_one_audit(self):
        req = self.ready()
        # Separate clients/cookies represent two browser sessions of the same tenant.
        self.a.actor('company2')
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda actor:self.transition(req,actor=actor).status_code,['company','company2']))
        self.assertEqual(sorted(statuses),[200,409])
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='REQUEST_CLOSED')),1)

    def test_close_racing_invoice_edit_cannot_leave_a_closed_unreviewed_request(self):
        req = self.ready()
        self.a.actor('company2')
        with ThreadPoolExecutor(max_workers=2) as pool:
            close = pool.submit(self.transition, req)
            edit = pool.submit(self.a.revise, req, 'owner', fields={**req['invoices'][0]['fields'],'vendor_name':'Vendor terkoreksi'})
            self.assertEqual(sorted([close.result().status_code,edit.result().status_code]),[200,409])
        fresh = self.detail(req)
        if fresh['lifecycle']['state']=='CLOSED':
            self.assertEqual(fresh['invoices'][0]['review_status'],'APPROVED')
        else:
            self.assertEqual(fresh['invoices'][0]['review_status'],'PENDING')

    def test_all_invoice_handover_required_and_partial_voucher_is_discoverable(self):
        self.a.rows.append(test_api.invoice_fields('SECOND'))
        req = self.a.processed()
        for inv in req['invoices']:
            self.assertEqual(self.a.revise({**req,'invoices':[inv]}).status_code,200)
        req = self.a.take(self.detail(req))
        self.a.decision(req)
        self.download(req)
        listing = self.a.actor('owner').get('/api/requests?has_voucher=1').json['data']
        self.assertEqual(listing['total'],1)
        self.assertEqual(listing['items'][0]['voucher_count'],1)
        self.assertEqual(self.transition(req).status_code,409)
        self.a.decision({**req,'invoices':[req['invoices'][1]]})
        self.assertEqual(self.transition(req).status_code,409)
        self.download(req,index=1)
        self.assertEqual(self.transition(req).status_code,200)

    def test_v2_sqlite_upgrade_is_additive_and_preserves_request(self):
        req = self.a.processed()
        engine = self.a.app.extensions['amiga_engine']
        RequestLifecycle.__table__.drop(engine)
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.get(Setting,'schema_version').value='2'
        config = {k:self.a.app.config[k] for k in ('DATABASE_URL','UPLOAD_DIR','SECRET_KEY')}
        app = create_app({**config,'TESTING':True,'START_QUEUE_WORKER':False,'OPENAI_API_KEY':''})
        try:
            with app.extensions['amiga_db']() as db:
                self.assertEqual(db.get(Setting,'schema_version').value,'8')
                self.assertEqual(db.scalar(select(func.count()).select_from(RequestLifecycle)),0)
            self.assertEqual(self.detail(req)['lifecycle']['state'],'OPEN')
        finally:
            app.extensions['amiga_engine'].dispose()
