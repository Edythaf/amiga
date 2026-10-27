"""Company tenant boundaries and independent manual PDF publication. No paid API calls."""
import unittest
from io import BytesIO
from unittest.mock import Mock
from sqlalchemy import select,func
import test_api
from backend.models import ManualReviewPDF,Membership,User,TelegramLink,Role
from backend.telegram_config import set_preference,bot_fingerprint


class CompanyManualTests(unittest.TestCase):
    def setUp(self):
        self.a=test_api.ApiTests();self.a.setUp()
    def tearDown(self):self.a.tearDown()
    def ready(self):
        req=self.a.processed();self.a.take(req);return req
    def upload(self,req,actor='finance',previous='',content=None,version=None,confirmed='true'):
        inv=req['invoices'][0]
        return self.a.call(actor,'POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/manual-pdf",data={
            'expected_version':inv['current_version'] if version is None else version,'expected_previous_id':previous,
            'content_confirmed':confirmed,'review_pdf':(BytesIO(content or test_api.pdf_bytes('Manual review without signature')),'hasil-review.pdf')})
    def signature(self,req,row):
        inv=req['invoices'][0]
        return self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/manual-pdf/{row['id']}/signature",json={'expected_version':inv['current_version']})

    def test_company_scoped_read_only_uploader_and_reviewer_independent(self):
        req=self.ready();inv=req['invoices'][0];base=f"/api/requests/{req['id']}"
        client=self.a.actor('company')
        me=client.get('/api/auth/me').json['data'];self.assertEqual(me['portal'],'client')
        self.assertEqual(self.a.actor('owner').get('/api/auth/me').json['data']['portal'],'uploader')
        detail=client.get(base).json['data'];self.assertNotIn('EDIT',detail['invoices'][0]['allowed_actions'])
        self.assertIn('uploader_name',detail)
        self.assertEqual(self.a.actor('company_other').get(base).status_code,404)
        self.assertEqual(self.a.revise(req,account='company').status_code,403)
        self.assertEqual(self.a.call('company','POST',base+'/evidence',json={}).status_code,403)
        self.assertEqual(self.a.call('company','POST',f"/api/tasks/{req['id']}/claim",json={}).status_code,403)
        self.assertEqual(self.a.call('company','POST',base+f"/invoices/{inv['id']}/confirm-uploader",json={'expected_version':inv['current_version'],'acknowledged':True,'item_count_confirmed':True}).status_code,403)
        self.assertEqual(client.get('/api/agents/overview').status_code,403)
        self.assertEqual(self.a.actor('owner').get('/api/telegram/status').status_code,403)

    def test_admin_company_name_edit_and_separate_role_assignment(self):
        endpoint='/api/admin/clients/A'
        self.assertEqual(self.a.call('owner','PATCH',endpoint,json={'name':'New company','expected_name':'Klien A'}).status_code,403)
        result=self.a.call('admin','PATCH',endpoint,json={'name':'PT Perusahaan Demo','expected_name':'Klien A'})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.a.actor('company').get('/api/auth/me').json['data']['user']['clients'][0]['name'],'PT Perusahaan Demo')
        self.assertEqual(self.a.call('admin','PATCH',endpoint,json={'name':'Old tab','expected_name':'Klien A'}).status_code,409)
        for roles,clients in [(['COMPANY_CLIENT','CLIENT_OWNER'],['A']),(['COMPANY_CLIENT'],[])]:
            result=self.a.call('admin','PATCH','/api/admin/users/company_other',json={'roles':roles,'client_ids':clients,'account_status':'ACTIVE'})
            self.assertEqual(result.status_code,422)
        req=self.a.processed()
        self.assertEqual(self.a.actor('company_other').get('/api/requests/'+req['id']).status_code,404)
        self.assertEqual(self.a.call('admin','PATCH','/api/admin/users/company_other',json={'roles':['COMPANY_CLIENT'],'client_ids':['A'],'account_status':'ACTIVE'}).status_code,200)
        self.assertEqual(self.a.actor('company_other').get('/api/auth/me').status_code,401)
        self.a.clients.pop('company_other');self.assertEqual(self.a.actor('company_other').get('/api/requests/'+req['id']).status_code,200)

    def test_manual_unsigned_pdf_uploaded_analyzed_and_published_without_confirmation_reset(self):
        req=self.ready();inv=req['invoices'][0];pdf=test_api.pdf_bytes('Manually reviewed voucher, no signature')
        result=self.upload(req,content=pdf);self.assertEqual(result.status_code,201,result.json);row=result.json['data']
        analyzer=Mock(return_value={'status':'NOT_DETECTED','note':'Tidak terlihat tanda tangan.','pages':[]})
        self.a.app.config['SIGNATURE_ANALYZER']=analyzer
        self.assertEqual(self.signature(req,row).json['data']['signature_state'],'NOT_DETECTED')
        self.assertEqual(self.signature(req,row).status_code,200);analyzer.assert_called_once()
        detail=self.a.actor('owner').get('/api/requests/'+req['id']).json['data']
        self.assertTrue(detail['ready_for_review']);self.assertEqual(detail['invoices'][0]['current_version'],inv['current_version'])
        self.assertEqual([d['id'] for d in detail['documents']],[d['id'] for d in req['documents']])
        self.assertEqual(self.a.decision(req).status_code,200)
        download=self.a.call('company','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download",json={'expected_version':inv['current_version']})
        self.assertEqual(download.data,pdf);self.assertEqual(download.headers['X-Handover-Recorded'],'true')
        self.assertEqual(self.upload(req,previous=row['id']).status_code,409)

    def test_manual_pdf_permissions_staleness_archive_and_signature_failure_nonblocking(self):
        req=self.ready()
        for actor,status in [('owner',403),('company',403),('admin',403),('finance2',404)]:self.assertEqual(self.upload(req,actor=actor).status_code,status)
        self.assertEqual(self.upload(req,confirmed='false').status_code,422)
        self.assertEqual(self.upload(req,version=99).status_code,409)
        self.assertEqual(self.upload(req,content=b'not PDF').status_code,422)
        first=self.upload(req).json['data']
        self.assertEqual(self.upload(req).status_code,409)
        second=self.upload(req,previous=first['id']).json['data']
        self.assertEqual(self.signature(req,first).status_code,409)
        self.a.app.config['SIGNATURE_ANALYZER']=Mock(side_effect=RuntimeError('private credential details'))
        result=self.signature(req,second);self.assertEqual(result.json['data']['signature_state'],'FAILED')
        self.assertNotIn('private credential',result.get_data(as_text=True))
        self.assertEqual(self.a.decision(req).status_code,200)
        with self.a.app.extensions['amiga_db']() as db:self.assertEqual(db.scalar(select(func.count()).select_from(ManualReviewPDF)),2)

    def test_unsigned_pending_pdf_can_publish_without_ai_and_cannot_change_company_handover_as_uploader(self):
        req=self.ready();inv=req['invoices'][0]
        row=self.upload(req).json['data'];self.assertEqual(row['signature_state'],'PENDING')
        self.assertEqual(self.a.decision(req).status_code,200)
        download=self.a.call('owner','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download",json={'expected_version':inv['current_version']})
        self.assertEqual(download.headers['X-Handover-Recorded'],'false')
        self.assertEqual(self.a.call('owner','POST',f"/api/requests/{req['id']}/lifecycle",json={}).status_code,403)
