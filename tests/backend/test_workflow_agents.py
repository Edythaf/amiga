"""Real HTTP workflows with disposable data and mocked Luna/Telegram transports."""
import copy,json,unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from io import BytesIO
from unittest.mock import Mock
from unittest.mock import patch
from sqlalchemy import select,func,delete
import test_api
from backend.initial_analysis import process_initial_one
from backend.models import (InvoiceAssistance,TelegramLink,TelegramDelivery,AgentTurn,Document,Invoice,User,Role,Membership,AuthSession)
from backend.workflow import source_document
from backend.telegram_service import TelegramError
from backend.telegram_config import set_preference,bot_fingerprint
from backend.agent_service import reply
from test_tasks import ANALYSIS


class WorkflowAgentTests(unittest.TestCase):
    def setUp(self):
        self.a=test_api.ApiTests();self.a.setUp()
        self.a.app.config.update(INITIAL_ANALYZER=lambda *args:{'analysis':copy.deepcopy(ANALYSIS),'model':'gpt-6-luna'},
            AGENT_RESPONDER=lambda q,c,h,k:{'answer':'Ringkasan hasil pemeriksaan tersimpan.','next_steps':['Periksa dokumen.'],'intent':'ANSWER'},
            TELEGRAM_BOT_TOKEN='',TELEGRAM_BOT_USERNAME='amiga_test_bot')

    def tearDown(self):self.a.tearDown()

    def detail(self,req):return self.a.actor('owner').get('/api/requests/'+req['id']).json['data']

    def prepare(self,confirm=True):
        req=self.a.processed()
        while process_initial_one(self.a.app,req['id']):pass
        if confirm:self.confirm(req)
        return self.detail(req)

    def confirm(self,req,actor='owner',**changes):
        inv=self.detail(req)['invoices'][0]
        return self.a.call(actor,'POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/confirm-uploader",json={
            'expected_version':inv['current_version'],'acknowledged':True,'item_count_confirmed':True,**changes})

    def chat(self,req,actor='finance',question='Ringkas hasil review invoice ini.'):
        return self.a.call(actor,'POST','/api/agents/chat',json={'request_id':req['id'],'question':question})

    def linked(self):
        self.a.app.config['TELEGRAM_BOT_TOKEN']='fictional-token'
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.add(TelegramLink(user_id='company',chat_id='123456',username='fictional_owner'))
            set_preference(db,'link','company',bot_fingerprint(self.a.app.config))

    def preview(self,req,ensure_official=True,**changes):
        if ensure_official and self.detail(req)['invoices'][0]['review_status']!='APPROVED':
            self.assertEqual(self.a.decision(req).status_code,200)
        turn=self.chat(req).json['data'];inv=self.detail(req)['invoices'][0]
        return self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/telegram-preview",json={
            'turn_id':turn['id'],'expected_version':inv['current_version'],**changes})

    def test_initial_ai_then_uploader_confirmation_gates_board_claim_and_approval(self):
        req=self.a.processed()
        self.assertEqual(self.detail(req)['work_status'],'WAITING_UPLOADER')
        self.assertEqual(self.a.actor('finance').get('/api/tasks').json['data']['total'],0)
        self.assertEqual(self.a.call('finance','POST',f"/api/tasks/{req['id']}/claim",json={}).status_code,409)
        self.assertEqual(self.confirm(req).status_code,409)
        process_initial_one(self.a.app,req['id'])
        self.assertEqual(self.confirm(req,actor='other').status_code,404)
        self.assertEqual(self.confirm(req,acknowledged=False).status_code,422)
        self.assertEqual(self.confirm(req,item_count_confirmed=False).status_code,422)
        self.assertEqual(self.confirm(req).status_code,200)
        req=self.detail(req)
        self.assertEqual(req['work_status'],'UNCLAIMED')
        self.assertTrue(req['invoices'][0]['validation']['valid'])
        self.a.take(req)
        self.assertEqual(self.a.decision(req).status_code,200)

    def test_failed_initial_can_retry_but_cannot_be_confirmed_or_auto_approved(self):
        self.a.app.config['INITIAL_ANALYZER']=Mock(side_effect=RuntimeError('private-provider-detail'))
        req=self.a.processed();process_initial_one(self.a.app,req['id'])
        inv=self.detail(req)['invoices'][0]
        self.assertEqual(inv['initial_analysis']['state'],'FAILED')
        self.assertNotIn('private-provider-detail',json.dumps(inv))
        self.assertEqual(self.confirm(req).status_code,409)
        url=f"/api/requests/{req['id']}/invoices/{inv['id']}/initial-analysis/retry"
        self.assertEqual(self.a.call('owner','POST',url,json={'expected_version':1}).status_code,200)
        self.a.app.config['INITIAL_ANALYZER']=lambda *args:{'analysis':copy.deepcopy(ANALYSIS)}
        process_initial_one(self.a.app,req['id'])
        self.assertEqual(self.confirm(req).status_code,200)

    def test_edit_invalidates_confirmation_and_requires_uploader_again(self):
        req=self.prepare();self.a.take(req)
        fields=copy.deepcopy(req['invoices'][0]['fields']);fields['vendor_name']='Revised vendor'
        response=self.a.revise(req,account='finance',fields=fields)
        self.assertEqual(response.status_code,200)
        req=self.detail(req)
        self.assertFalse(req['invoices'][0]['uploader_confirmation']['confirmed'])
        inv=req['invoices'][0]
        self.assertEqual(self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/approve",json={'expected_version':inv['current_version']}).status_code,409)
        process_initial_one(self.a.app,req['id']);self.assertEqual(self.confirm(req).status_code,200)
        self.assertEqual(self.a.decision(req).status_code,200)

    def test_unchanged_save_after_confirmation_preserves_version_queue_and_analysis(self):
        req=self.prepare();original=req['invoices'][0]
        self.assertTrue(original['uploader_confirmation']['confirmed'])
        # This is the browser payload, including all retained sources and the
        # item count confirmed by the uploader rather than an earlier revision.
        result=self.a.revise(req,field_sources=original['field_sources'])
        self.assertEqual(result.status_code,200,result.json)
        self.assertFalse(result.json['data']['revision_created'])
        current=self.detail(req);inv=current['invoices'][0]
        self.assertEqual(inv['current_version'],original['current_version'])
        self.assertEqual(inv['uploader_confirmation'],original['uploader_confirmation'])
        self.assertEqual(inv['initial_analysis'],original['initial_analysis'])
        self.assertTrue(current['ready_for_review'])
        self.assertEqual(self.a.actor('finance').get('/api/tasks').json['data']['total'],1)
        self.a.take(current)
        result=self.a.revise(current,account='finance',field_sources=inv['field_sources'])
        self.assertEqual(result.status_code,200,result.json)
        self.assertFalse(result.json['data']['revision_created'])
        current=self.detail(req)
        self.assertTrue(current['ready_for_review'])
        self.assertEqual(current['invoices'][0]['current_version'],original['current_version'])
        self.assertEqual(self.a.decision(current).status_code,200)

    def test_confirmation_count_change_still_creates_revision_and_blocks_queue(self):
        req=self.prepare();original=req['invoices'][0]
        response=self.a.revise(req,item_count_confirmed=False,field_sources=original['field_sources'])
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(response.json['data']['revision_created'])
        current=self.detail(req)
        self.assertEqual(current['invoices'][0]['current_version'],original['current_version']+1)
        self.assertFalse(current['ready_for_review'])
        self.assertFalse(current['invoices'][0]['uploader_confirmation']['confirmed'])

    def test_new_pdf_retains_request_history_and_queues_latest_source(self):
        req=self.prepare();old=req['documents'][0]['id'];inv=req['invoices'][0]
        response=self.a.call('owner','POST',f"/api/requests/{req['id']}/document-revision",data={
            'expected_versions':json.dumps({inv['id']:1}),'reason':'Sumber invoice perlu diganti.',
            'category':'SOURCE_ERROR','invoice_file':(BytesIO(test_api.pdf_bytes('Revised fictional source')),'revision.pdf')})
        self.assertEqual(response.status_code,201,response.json)
        revised=response.json['data'];self.assertEqual(revised['id'],req['id']);self.assertEqual(revised['invoices'],[])
        with self.a.app.extensions['amiga_db']() as db:
            self.assertNotEqual(source_document(db,db.get(__import__('backend.models',fromlist=['WorkRequest']).WorkRequest,req['id'])).id,old)
            self.assertIsNotNone(db.get(Document,old));self.assertEqual(db.get(Invoice,inv['id']).active,0)
        from backend.processing import process_one
        process_one(self.a.app,req['id']);self.assertEqual(self.detail(req)['work_status'],'WAITING_UPLOADER')

    def test_agent_role_scope_caching_and_daily_limit(self):
        req=self.prepare()
        denied=self.chat(req,'other');self.assertEqual(denied.status_code,404)
        first=self.chat(req,'owner');self.assertEqual(first.status_code,200,first.json)
        self.assertEqual(self.chat(req,'owner').json['data']['cached'],True)
        self.assertEqual(self.a.actor('owner').get('/api/agents/overview').json['data']['role'],'uploader')
        self.assertNotIn('performance',self.a.actor('owner').get('/api/agents/overview').json['data'])
        self.assertIn('performance',self.a.actor('admin').get('/api/agents/overview').json['data'])
        self.a.app.config['AGENT_DAILY_LIMIT']=1
        self.assertEqual(self.chat(req,'owner','Pertanyaan invoice baru').status_code,429)

    def test_access_revocation_during_agent_analysis_drops_response(self):
        req=self.prepare();self.a.take(req)
        def revoke(*args):
            with self.a.app.extensions['amiga_db'].begin() as db:
                db.get(User,'finance').account_status='DISABLED';db.execute(delete(AuthSession).where(AuthSession.user_id=='finance'))
            return {'answer':'PRIVATE_RESPONSE','next_steps':[],'intent':'ANSWER'}
        self.a.app.config['AGENT_RESPONDER']=revoke
        response=self.chat(req)
        self.assertEqual(response.status_code,401);self.assertNotIn('PRIVATE_RESPONSE',response.get_data(as_text=True))

    def test_telegram_absent_is_optional_and_cannot_send(self):
        req=self.prepare();self.a.take(req)
        self.assertFalse(self.a.actor('company').get('/api/telegram/status').json['data']['connected'])
        self.assertEqual(self.preview(req).status_code,409)
        self.assertEqual(self.a.actor('owner').get('/api/requests').status_code,200)

    def test_telegram_preview_is_not_a_send_and_requires_exact_approval(self):
        req=self.prepare();self.a.take(req);self.linked()
        transport=Mock(return_value={'message_id':123})
        self.a.app.config['TELEGRAM_TRANSPORT']=transport
        row=self.preview(req).json['data'];transport.assert_not_called()
        path='/api/telegram/previews/'+row['id']+'/send'
        self.assertEqual(self.a.call('finance','POST',path,json={'approved':False,'preview_hash':row['preview_hash']}).status_code,422)
        self.assertEqual(self.a.call('other','POST',path,json={}).status_code,404)
        data={'approved':True,'preview_hash':row['preview_hash']}
        self.assertEqual(self.a.call('finance','POST',path,json=data).json['data']['state'],'SENT')
        self.assertEqual(self.a.call('finance','POST',path,json=data).json['data']['state'],'SENT')
        transport.assert_called_once()
        self.assertEqual(transport.call_args.args[1]['chat_id'],'123456')

    def test_changed_preview_cancels_old_consent_and_version_change_blocks_send(self):
        req=self.prepare();self.a.take(req);self.linked()
        old=self.preview(req).json['data'];new=self.preview(req,message='Pesan hasil yang sudah diperbarui.').json['data']
        self.assertEqual(self.a.call('finance','POST','/api/telegram/previews/'+old['id']+'/send',json={'approved':True,'preview_hash':old['preview_hash']}).status_code,409)
        fields=copy.deepcopy(req['invoices'][0]['fields']);fields['vendor_name']='Vendor hasil revisi'
        self.assertEqual(self.a.revise(req,fields=fields).status_code,200)
        self.assertEqual(self.a.call('finance','POST','/api/telegram/previews/'+new['id']+'/send',json={'approved':True,'preview_hash':new['preview_hash']}).status_code,409)

    def test_timeout_is_unknown_and_never_auto_retried(self):
        req=self.prepare();self.a.take(req);self.linked()
        transport=Mock(side_effect=TelegramError('TELEGRAM_UNCERTAIN',True));self.a.app.config['TELEGRAM_TRANSPORT']=transport
        row=self.preview(req).json['data'];path='/api/telegram/previews/'+row['id']+'/send';data={'approved':True,'preview_hash':row['preview_hash']}
        self.assertEqual(self.a.call('finance','POST',path,json=data).json['data']['state'],'UNKNOWN')
        self.assertEqual(self.a.call('finance','POST',path,json=data).status_code,409)
        transport.assert_called_once()

    def test_private_bot_challenge_verifies_and_unlink_stales_preview(self):
        self.a.app.config['TELEGRAM_BOT_TOKEN']='fictional-token'
        linked=self.a.call('company','POST','/api/telegram/link',json={}).json['data']
        token=linked['url'].split('start=')[1]
        updates=[{'update_id':1,'message':{'text':'/start '+token,'chat':{'type':'private','id':123456},'from':{'id':123456,'username':'fictional'}}}]
        self.a.app.config['TELEGRAM_TRANSPORT']=lambda *args:updates
        result=self.a.call('company','POST','/api/telegram/verify',json={})
        self.assertTrue(result.json['data']['connected'])
        req=self.prepare();self.a.take(req);row=self.preview(req).json['data']
        self.a.call('company','DELETE','/api/telegram/link',json={})
        sent=self.a.call('finance','POST','/api/telegram/previews/'+row['id']+'/send',json={'approved':True,'preview_hash':row['preview_hash']})
        self.assertEqual(sent.status_code,409)

    def test_admin_metrics_require_complete_work_and_client_acceptance(self):
        req=self.prepare();self.a.take(req);self.a.decision(req)
        report=self.a.actor('admin').get('/api/agents/overview').json['data']['performance']
        row=next(r for r in report['reviewers'] if r['reviewer_id']=='finance')
        self.assertEqual((row['taken'],row['completed'],row['accepted']),(1,1,0))
        inv=req['invoices'][0]
        self.a.call('company','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/voucher/download",json={'expected_version':1})
        current=self.detail(req)
        self.assertEqual(self.a.call('company','POST',f"/api/requests/{req['id']}/lifecycle",json={
            'action':'CLOSE','reason':'Hasil telah diperiksa dan diterima.','expected_lifecycle_revision':current['lifecycle']['revision'],
            'expected_versions':{inv['id']:1}}).status_code,200)
        report=self.a.actor('admin').get('/api/agents/overview').json['data']['performance']
        row=next(r for r in report['reviewers'] if r['reviewer_id']=='finance')
        self.assertEqual((row['accepted'],row['accepted_without_revision'],row['first_pass_rate']),(1,1,100))
        self.assertNotIn('performance',self.a.actor('finance').get('/api/agents/overview').json['data'])

    def test_partial_multi_invoice_is_not_counted_as_completed_request(self):
        self.a.rows=[test_api.invoice_fields('ONE'),test_api.invoice_fields('TWO')]
        req=self.prepare();self.a.take(req)
        self.assertEqual(self.a.decision({**req,'invoices':[req['invoices'][0]]}).status_code,200)
        rows=self.a.actor('admin').get('/api/agents/overview').json['data']['performance']['reviewers']
        self.assertEqual(next(r for r in rows if r['reviewer_id']=='finance')['completed'],0)

    def test_agent_transport_keeps_luna_no_storage_and_bounded_output(self):
        value={'answer':'Periksa invoice tersimpan.','next_steps':[],'intent':'ANSWER'}
        response=Mock(status_code=200)
        response.json.return_value={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch('backend.openai_extractor.requests.post',return_value=response) as post:
            result=reply('Periksa invoice',{'role':'reviewer'},[],{'AGENT_MODEL':'gpt-6-luna','OPENAI_API_KEY':'fictional-key'})
        self.assertEqual(result,value)
        payload=post.call_args.kwargs['json']
        self.assertEqual(payload['model'],'gpt-6-luna');self.assertFalse(payload['store'])
        self.assertEqual(payload['max_output_tokens'],1600);self.assertNotIn('tools',payload)

    def test_initial_result_fenced_after_evidence_changes_and_budget_is_shared(self):
        req=self.a.processed()
        def changed(*args):
            self.a.call('owner','POST',f"/api/requests/{req['id']}/evidence",data={'evidence_file':(BytesIO(test_api.pdf_bytes('New evidence')),'evidence.pdf')})
            return {'analysis':copy.deepcopy(ANALYSIS)}
        analyzer=Mock(side_effect=changed);self.a.app.config['INITIAL_ANALYZER']=analyzer
        process_initial_one(self.a.app,req['id'])
        self.assertEqual(self.detail(req)['invoices'][0]['initial_analysis']['state'],'PENDING')
        self.a.app.config['AGENT_DAILY_LIMIT']=1
        process_initial_one(self.a.app,req['id'])
        inv=self.detail(req)['invoices'][0]
        self.assertEqual(inv['initial_analysis']['error_code'],'AGENT_DAILY_LIMIT')
        analyzer.assert_called_once();self.assertEqual(self.confirm(req).status_code,409)

    def test_draft_voucher_cannot_be_sent_as_official_attachment(self):
        req=self.prepare();self.a.take(req);self.linked()
        self.assertEqual(self.preview(req,ensure_official=False,include_voucher=True).status_code,409)

    def test_concurrent_send_uses_one_transport_call(self):
        req=self.prepare();self.a.take(req);self.linked()
        row=self.preview(req).json['data'];started=Event();release=Event()
        def transport(*args):started.set();release.wait(5);return {'message_id':123}
        mock=Mock(side_effect=transport);self.a.app.config['TELEGRAM_TRANSPORT']=mock
        first=self.a.login('finance')[0];second=self.a.login('finance')[0]
        path='/api/telegram/previews/'+row['id']+'/send';data={'approved':True,'preview_hash':row['preview_hash']}
        def send(client):
            csrf=client.get('/api/auth/csrf').json['data']['csrf_token']
            return client.post(path,json=data,headers={'X-CSRF-Token':csrf})
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(send,first)
            self.assertTrue(started.wait(5))
            duplicate=send(second);release.set();result=future.result()
        self.assertEqual(result.status_code,200);self.assertEqual(duplicate.status_code,409);mock.assert_called_once()

    def test_replacing_published_source_requires_consent_and_preserves_downloadable_archive(self):
        self.a.rows=[test_api.invoice_fields('ONE'),test_api.invoice_fields('TWO')]
        req=self.prepare();self.a.take(req)
        self.assertEqual(self.a.decision({**req,'invoices':[req['invoices'][0]]}).status_code,200)
        from backend.models import Voucher,Handover
        with self.a.app.extensions['amiga_db']() as db:
            voucher=db.scalar(select(Voucher));voucher_id=voucher.id;original=voucher.pdf
            handovers=db.scalar(select(func.count()).select_from(Handover))
        url=f"/api/requests/{req['id']}/document-revision"
        def upload(ack=False):
            return self.a.call('owner','POST',url,data={'expected_versions':json.dumps({i['id']:i['current_version'] for i in req['invoices']}),
                'reason':'Koreksi dokumen sumber terbaru.','supersede_published':'true' if ack else 'false',
                'invoice_file':(BytesIO(test_api.pdf_bytes('Revised fictional invoice')),'revision.pdf')})
        self.assertEqual(upload().status_code,422)
        self.assertEqual(upload(True).status_code,201)
        listing=self.a.actor('owner').get(f"/api/requests/{req['id']}/voucher-history")
        self.assertEqual(listing.json['data']['items'][0]['id'],voucher_id)
        path=f"/api/requests/{req['id']}/vouchers/{voucher_id}/archive-download"
        self.assertEqual(self.a.call('owner','POST',path,json={}).data,original)
        self.assertEqual(self.a.call('other','POST',path,json={}).status_code,404)
        self.assertEqual(self.a.actor('other').get(f"/api/requests/{req['id']}/voucher-history").status_code,404)
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Handover)),handovers)
        events=self.a.actor('owner').get(f"/api/requests/{req['id']}/audit").json['data']['items']
        self.assertTrue(any(e['action']=='CLIENT_REVISION_REQUESTED' for e in events))

    def test_additive_migration_repairs_partial_v4_and_is_idempotent(self):
        from sqlalchemy import text,inspect
        from backend.schema import ensure_workflow_columns
        engine=self.a.app.extensions['amiga_engine']
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE amiga_agent_turns DROP COLUMN request_hash'))
            conn.execute(text('ALTER TABLE amiga_uploader_confirmations DROP COLUMN item_count'))
        ensure_workflow_columns(engine);ensure_workflow_columns(engine)
        self.assertIn('request_hash',{c['name'] for c in inspect(engine).get_columns('amiga_agent_turns')})
        self.assertIn('item_count',{c['name'] for c in inspect(engine).get_columns('amiga_uploader_confirmations')})
        self.assertEqual(self.a.actor('owner').get('/api/auth/me').status_code,200)
