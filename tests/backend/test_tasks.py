"""Task pool, ownership, revocation, and advisory AI: real API, isolated data."""
import copy
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
from sqlalchemy import select, delete, func
import test_api
from backend.models import Membership, WorkRequest, Audit, InvoiceVersion, Voucher, User, AuthSession
from backend.review_analysis import analyze

ANALYSIS = {'summary': 'Bandingkan nilai dan rekening dengan dokumen.', 'risk': 'MEDIUM',
            'findings': [{'severity': 'WARNING', 'field': 'total_amount', 'observation': 'Periksa total.',
                          'recommendation': 'Bandingkan seluruh baris.'}], 'next_steps': ['Periksa PDF asli.']}


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.a = test_api.ApiTests()
        self.a.setUp()

    def tearDown(self):
        self.a.tearDown()

    def test_board_cross_client_summary_only_and_exclusive_claim_without_membership(self):
        a = self.a
        req = a.processed(account='other', client_id='B')
        a.prepare_review(req)
        inv, doc = req['invoices'][0], req['documents'][0]
        with a.app.extensions['amiga_db'].begin() as db:
            db.execute(delete(Membership).where(Membership.user_id == 'finance2'))
        board = a.actor('finance2').get('/api/tasks').json['data']
        self.assertEqual([r['id'] for r in board['items']], [req['id']])
        self.assertNotIn('documents', board['items'][0])
        self.assertNotIn('account_number', str(board))
        base = '/api/requests/' + req['id']
        self.assertEqual(a.actor('finance2').get(base).status_code, 404)
        self.assertEqual(a.actor('finance2').get(base + '/documents/' + doc['id']).status_code, 404)
        self.assertEqual(a.actor('owner').get('/api/tasks').status_code, 403)
        a.take(req, 'finance2')
        self.assertEqual(a.actor('finance2').get(base).status_code, 200)
        self.assertEqual(a.actor('finance').get('/api/tasks').json['data']['total'], 0)
        self.assertEqual(a.actor('finance').get(base).status_code, 404)
        self.assertEqual(a.actor('finance2').get('/api/requests?scope=mine').json['data']['total'], 1)
        self.assertEqual(a.actor('owner').get(base).status_code, 404)
        monitor = a.actor('admin').get('/api/tasks?scope=all').json['data']['items'][0]
        self.assertEqual(monitor['pic_id'], 'finance2')
        self.assertEqual(monitor['pic_name'], 'finance2')
        self.assertEqual(a.actor('finance').get('/api/tasks?scope=all').status_code, 403)

    def test_two_reviewers_claim_simultaneously_only_one_wins(self):
        a = self.a
        req = a.confirmed()
        for actor in ['finance', 'finance2']:
            a.actor(actor)
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda actor:a.call(actor,'POST',f"/api/tasks/{req['id']}/claim",json={}).status_code,
                                     ['finance', 'finance2']))
        self.assertEqual(sorted(statuses), [200, 409])
        with a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Audit).where(Audit.action == 'TASK_CLAIMED')), 1)

    def test_release_revokes_document_access_and_retains_history(self):
        a = self.a
        req = a.processed()
        a.take(req)
        url = f"/api/tasks/{req['id']}/release"
        self.assertEqual(a.call('other','POST',url,json={'reason':'Invalid access'}).status_code,404)
        self.assertEqual(a.call('owner','POST',url,json={'reason':'Invalid access'}).status_code,403)
        self.assertEqual(a.call('finance','POST',url,json={'reason':'Tugas dikembalikan.'}).status_code,200)
        self.assertEqual(a.actor('finance').get('/api/requests/'+req['id']).status_code,404)
        a.take(req,'finance2')
        events=a.actor('admin').get('/api/requests/'+req['id']+'/audit').json['data']['items']
        self.assertEqual([e['action'] for e in events if e['action'].startswith('TASK_')],['TASK_CLAIMED','TASK_RELEASED','TASK_CLAIMED'])

    def test_disable_reviewer_revokes_sessions_releases_only_unfinished_tasks(self):
        a=self.a
        completed=a.confirmed()
        a.take(completed)
        self.assertEqual(a.decision(completed).status_code,200)
        a.rows[0]['invoice_number']='INV-SECOND'
        unfinished=a.processed(content=test_api.pdf_bytes('Second'))
        a.take(unfinished)
        old=a.actor('finance')
        self.assertEqual(a.call('admin','PATCH','/api/admin/users/finance',json={'account_status':'DISABLED'}).status_code,200)
        self.assertEqual(old.get('/api/auth/me').status_code,401)
        self.assertEqual(old.get('/api/tasks').status_code,401)
        with a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.get(WorkRequest,completed['id']).pic_id,'finance')
            self.assertIsNone(db.get(WorkRequest,unfinished['id']).pic_id)
            self.assertEqual(db.scalar(select(func.count()).select_from(Voucher)),1)
        a.take(unfinished,'finance2')

    def test_no_self_claim_and_admin_no_review(self):
        a=self.a
        req=a.processed(account='dual')
        self.assertEqual(a.call('dual','POST',f"/api/tasks/{req['id']}/claim",json={}).status_code,403)
        self.assertEqual(a.call('admin','POST',f"/api/tasks/{req['id']}/claim",json={}).status_code,403)

    def test_removed_client_membership_does_not_keep_uploader_access(self):
        a=self.a
        req=a.processed()
        response=a.call('admin','PATCH','/api/admin/users/owner',json={'client_ids':['B']})
        self.assertEqual(response.status_code,200)
        a.login('owner')
        self.assertEqual(a.actor('owner').get('/api/requests/'+req['id']).status_code,404)

    def test_complete_invoice_without_separate_evidence_and_missing_bank_code(self):
        a=self.a
        req=a.confirmed(evidence=False)
        self.assertTrue(req['invoices'][0]['validation']['valid'])
        a.rows[0]['account_number']=None
        missing=a.processed(content=test_api.pdf_bytes('No bank'))
        self.assertEqual(missing['status'],'EXCEPTION')
        self.assertIn('MISSING_EVIDENCE',[i['code'] for i in missing['invoices'][0]['validation']['issues']])

    def test_reviewer_download_does_not_mark_client_handover(self):
        a=self.a
        req=a.confirmed()
        a.take(req)
        self.assertEqual(a.decision(req).status_code,200)
        inv=req['invoices'][0]
        url=f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download"
        internal=a.call('finance','POST',url,json={'expected_version':2})
        self.assertEqual(internal.status_code,200)
        self.assertEqual(internal.headers['X-Handover-Recorded'],'false')
        internal.close()
        self.assertEqual(a.actor('owner').get('/api/requests/'+req['id']).json['data']['status'],'AMIGA_REVIEWED')
        external=a.call('company','POST',url,json={'expected_version':2})
        self.assertEqual(external.headers['X-Handover-Recorded'],'true')
        external.close()
        self.assertEqual(a.actor('owner').get('/api/requests/'+req['id']).json['data']['status'],'SENT_TO_CLIENT')

    def test_analysis_is_authorized_cached_audited_and_does_not_edit_or_approve(self):
        a=self.a
        req=a.confirmed()
        inv=req['invoices'][0]
        url=f"/api/requests/{req['id']}/invoices/{inv['id']}/analysis"
        payload={'expected_version':2,'question':'Periksa nilai'}
        analyzer=Mock(return_value={'analysis':copy.deepcopy(ANALYSIS),'model':'fixture-only'})
        a.app.config['REVIEW_ANALYZER']=analyzer
        self.assertEqual(a.call('finance','POST',url,json=payload).status_code,404)
        self.assertEqual(a.call('owner','POST',url,json=payload).status_code,403)
        a.take(req)
        first=a.call('finance','POST',url,json=payload)
        self.assertEqual(first.status_code,200,first.json)
        self.assertFalse(first.json['data']['cached'])
        self.assertEqual(a.call('finance','POST',url,json=payload).json['data']['cached'],True)
        self.assertEqual(analyzer.call_count,1)
        self.assertEqual(analyzer.call_args.args[0]['question'],'Periksa nilai')
        self.assertTrue(analyzer.call_args.args[1][0][1].startswith(b'%PDF-'))
        latest=a.actor('finance').get(url).json['data']['result']
        self.assertEqual(latest['analysis'],ANALYSIS)
        self.assertFalse(latest['stale'])
        with a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(InvoiceVersion)),2)
            self.assertEqual(db.scalar(select(func.count()).select_from(Voucher)),0)
            self.assertEqual(db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='REVIEW_AI_ANALYSIS')),1)
        self.assertEqual(a.call('finance','POST',url,json={**payload,'question':'Pertanyaan lain'}).status_code,429)

    def test_analysis_failure_and_access_revoked_during_call_never_publish(self):
        a=self.a
        req=a.confirmed();a.take(req)
        inv=req['invoices'][0];url=f"/api/requests/{req['id']}/invoices/{inv['id']}/analysis"
        a.app.config['REVIEW_ANALYZER']=Mock(side_effect=RuntimeError('provider failed'))
        self.assertEqual(a.call('finance','POST',url,json={'expected_version':2}).status_code,502)
        def disable(*args):
            with a.app.extensions['amiga_db'].begin() as db:
                db.get(User,'finance').account_status='DISABLED'
                db.execute(delete(AuthSession).where(AuthSession.user_id=='finance'))
            return {'analysis':copy.deepcopy(ANALYSIS)}
        a.app.config['REVIEW_ANALYZER']=disable
        self.assertEqual(a.call('finance','POST',url,json={'expected_version':2}).status_code,401)
        with a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='REVIEW_AI_ANALYSIS')),0)

    def test_analysis_transport_uses_pdf_structured_outputs_without_provider_storage(self):
        response=Mock(status_code=200)
        import json
        response.json.return_value={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(ANALYSIS)}]}]}
        with patch('backend.openai_extractor.requests.post',return_value=response) as post:
            result=analyze({'fields':{},'question':'Periksa'},[('invoice.pdf',test_api.pdf_bytes())],
                           {'AI_PROVIDER':'bedrock','OPENAI_MODEL':'configured-model','OPENAI_API_KEY':'fixture-key'})
        self.assertEqual(result['analysis'],ANALYSIS)
        payload=post.call_args.kwargs['json']
        self.assertFalse(payload['store'])
        self.assertEqual(payload['text']['format']['type'],'json_schema')
        self.assertTrue(payload['text']['format']['strict'])
        self.assertEqual(payload['input'][0]['content'][0]['type'],'input_file')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_revision_after_reviewer_disabled_reopens_pool(self):
        a=self.a
        req=a.confirmed();a.take(req)
        self.assertEqual(a.decision(req).status_code,200)
        self.assertEqual(a.call('admin','PATCH','/api/admin/users/finance',json={'account_status':'DISABLED'}).status_code,200)
        self.assertEqual(a.revise(req,fields={**req['invoices'][0]['fields'],'vendor_name':'Vendor Uji Terkoreksi'}).status_code,200)
        req=a.actor('owner').get('/api/requests/'+req['id']).json['data']
        a.prepare_review(req)
        board=a.actor('finance2').get('/api/tasks').json['data']
        self.assertEqual([r['id'] for r in board['items']],[req['id']])
        self.assertEqual(board['items'][0]['status'],'READY_FOR_REVIEW')

    def test_ai_result_is_rejected_if_evidence_changes_during_analysis(self):
        a=self.a
        req=a.confirmed();a.take(req)
        inv=req['invoices'][0]
        def revise_context(*args):
            with a.app.extensions['amiga_db'].begin() as db:
                record=db.get(InvoiceVersion,(inv['id'],2))
                record.vendor_name='Concurrent update fixture'
            return {'analysis':copy.deepcopy(ANALYSIS)}
        a.app.config['REVIEW_ANALYZER']=revise_context
        response=a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/analysis",json={'expected_version':2})
        self.assertEqual(response.status_code,409,response.json)
        self.assertEqual(response.json['error']['code'],'ANALYSIS_CONTEXT_CHANGED')
