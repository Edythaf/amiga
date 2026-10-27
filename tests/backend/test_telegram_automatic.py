"""Automatic delivery uses isolated databases and a fake transport only."""
import copy,unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import Mock,patch
from sqlalchemy import select,delete,func
import test_api
from backend.models import (TelegramDelivery,TelegramAutomaticDelivery,TelegramLink,
    Voucher,Handover,Membership,User,Invoice,WorkRequest,Review)
from backend.telegram_config import set_preference,bot_fingerprint
from backend.telegram_automatic import (process_automatic_one,enqueue_automatic,automatic_consent)
from backend.telegram_service import TelegramError


class AutomaticTelegramTests(unittest.TestCase):
    def setUp(self):
        self.a=test_api.ApiTests();self.a.setUp()
        self.transport=Mock(return_value={'message_id':42})
        self.a.app.config.update(TELEGRAM_BOT_TOKEN='fictional',TELEGRAM_BOT_USERNAME='fictional_bot',TELEGRAM_TRANSPORT=self.transport)
    def tearDown(self):self.a.tearDown()
    def link(self,user='company',chat='123456'):
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.add(TelegramLink(user_id=user,chat_id=chat,username='fictional'))
            set_preference(db,'link',user,bot_fingerprint(self.a.app.config))
    def opt(self,enabled=True,user='company'):
        response=self.a.call(user,'PATCH','/api/telegram/automatic',json={'enabled':enabled})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['data']
    def ready(self,opt=True):
        self.link()
        if opt:self.opt()
        req=self.a.processed();self.a.take(req);return req
    def publish(self,**kwargs):
        req=self.ready(**kwargs)
        response=self.a.decision(req);self.assertEqual(response.status_code,200,response.json)
        return req
    def row(self):
        with self.a.app.extensions['amiga_db']() as db:return db.scalar(select(TelegramDelivery))
    def dispatch(self):return process_automatic_one(self.a.app)

    def test_only_verified_company_self_can_opt_in_and_status_has_no_secrets(self):
        for user in ['owner','finance','admin']:
            self.assertEqual(self.a.call(user,'PATCH','/api/telegram/automatic',json={'enabled':True}).status_code,403)
        self.assertEqual(self.a.call('company','PATCH','/api/telegram/automatic',json={'enabled':True}).status_code,409)
        self.link()
        for enabled in ['true',1,None]:
            self.assertEqual(self.a.call('company','PATCH','/api/telegram/automatic',json={'enabled':enabled}).status_code,422)
        state=self.opt();self.assertTrue(state['automatic_enabled'])
        self.assertNotIn('chat_id',state);self.assertNotIn('token',str(state))
        self.transport.assert_not_called()

    def test_approval_commits_outbox_then_sends_exact_official_pdf_once(self):
        req=self.publish();self.transport.assert_not_called()
        self.assertEqual(self.row().state,'QUEUED')
        with self.a.app.extensions['amiga_db'].begin() as db:
            inv=db.get(Invoice,req['invoices'][0]['id']);parent=db.get(WorkRequest,req['id'])
            voucher=db.scalar(select(Voucher));expected=bytes(voucher.pdf)
            enqueue_automatic(db,parent,inv,voucher,'finance',self.a.app.config)
            self.assertEqual(db.scalar(select(func.count()).select_from(TelegramAutomaticDelivery)),1)
        self.assertTrue(self.dispatch());self.assertFalse(self.dispatch())
        self.transport.assert_called_once()
        method,payload,pdf=self.transport.call_args.args
        self.assertEqual(method,'sendDocument');self.assertEqual(pdf,expected)
        self.assertEqual(payload['chat_id'],'123456');self.assertIn('REQ-',payload['caption'])
        self.assertEqual(self.row().state,'SENT')
        with self.a.app.extensions['amiga_db']() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Handover)),0)
        detail=self.a.actor('company').get('/api/requests/'+req['id']).json['data']['telegram']['automatic']
        self.assertEqual(detail['items'][0]['state'],'SENT');self.assertNotIn('chat_id',str(detail))
        own=self.a.actor('company2').get('/api/requests/'+req['id']).json['data']['telegram']['automatic']
        self.assertEqual(own['items'],[])
        self.assertEqual(self.a.actor('company_other').get('/api/requests/'+req['id']).status_code,404)

    def test_no_backfill_or_send_without_recipient_opt_in(self):
        self.publish(opt=False)
        self.assertIsNone(self.row());self.opt();self.assertFalse(self.dispatch())
        self.transport.assert_not_called()

    def test_manual_final_pdf_including_signature_is_the_attachment(self):
        req=self.ready();inv=req['invoices'][0];pdf=test_api.pdf_bytes('Final revised voucher with manual signature')
        uploaded=self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/manual-pdf",data={
            'expected_version':1,'expected_previous_id':'','content_confirmed':'true',
            'review_pdf':(BytesIO(pdf),'final.pdf')})
        self.assertEqual(uploaded.status_code,201,uploaded.json)
        self.assertEqual(self.a.decision(req,voucher_pdf_source='MANUAL').status_code,200)
        self.dispatch();self.assertEqual(self.transport.call_args.args[2],pdf)

    def test_each_explicitly_opted_company_recipient_gets_one_copy_and_other_tenant_gets_none(self):
        req=self.ready()
        self.link('company2','234567');self.opt(user='company2')
        self.link('company_other','345678');self.opt(user='company_other')
        self.assertEqual(self.a.decision(req).status_code,200)
        while self.dispatch():pass
        self.assertEqual({call.args[1]['chat_id'] for call in self.transport.call_args_list},{'123456','234567'})
        self.assertEqual(self.transport.call_count,2)

    def test_approval_rollback_drops_voucher_and_outbox_together(self):
        req=self.ready()
        def enqueue_then_fail(*args):enqueue_automatic(*args);raise RuntimeError('fixture rollback')
        with patch('backend.telegram_automatic.enqueue_automatic',side_effect=enqueue_then_fail):
            with self.assertRaises(RuntimeError):self.a.decision(req)
        with self.a.app.extensions['amiga_db']() as db:
            for model in [Review,Voucher,TelegramDelivery,TelegramAutomaticDelivery]:
                self.assertEqual(db.scalar(select(func.count()).select_from(model)),0)
        self.assertFalse(self.dispatch());self.transport.assert_not_called()

    def test_disabling_cancels_queued_delivery_and_reenable_cannot_duplicate_it(self):
        self.publish();self.opt(False);self.opt()
        self.assertEqual(self.row().state,'CANCELLED');self.assertFalse(self.dispatch())
        self.transport.assert_not_called()

    def test_membership_revoked_before_dispatch_cancels_without_network(self):
        self.publish()
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.execute(delete(Membership).where(Membership.user_id=='company'))
        self.dispatch();self.assertEqual(self.row().state,'CANCELLED');self.transport.assert_not_called()

    def test_new_bot_requires_new_verification_and_opt_in(self):
        self.publish();self.a.app.config['TELEGRAM_BOT_TOKEN']='different-fictional-bot'
        self.dispatch();self.assertEqual(self.row().state,'CANCELLED');self.transport.assert_not_called()
        self.assertFalse(self.a.actor('company').get('/api/telegram/status').json['data']['automatic_enabled'])

    def test_reverified_recipient_invalidates_old_consent(self):
        self.publish()
        with self.a.app.extensions['amiga_db'].begin() as db:
            db.get(TelegramLink,'company').verified_at='2099-01-01T00:00:00Z'
            self.assertFalse(automatic_consent(db,'company',self.a.app.config))
        self.dispatch();self.assertEqual(self.row().state,'CANCELLED');self.transport.assert_not_called()

    def test_source_revision_cancels_old_version_and_next_publication_has_own_delivery(self):
        req=self.publish();fields=copy.deepcopy(req['invoices'][0]['fields']);fields['vendor_name']='Revised final'
        response=self.a.revise(req,fields=fields);self.assertEqual(response.status_code,200,response.json)
        self.dispatch();self.assertEqual(self.row().state,'CANCELLED');self.transport.assert_not_called()
        req=self.a.actor('owner').get('/api/requests/'+req['id']).json['data']
        self.assertEqual(self.a.decision(req).status_code,200)
        self.dispatch();self.transport.assert_called_once()
        with self.a.app.extensions['amiga_db']() as db:
            self.assertEqual([r.state for r in db.scalars(select(TelegramDelivery).order_by(TelegramDelivery.version))],['CANCELLED','SENT'])

    def test_concurrent_workers_cannot_send_same_job_twice(self):
        self.publish()
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:self.dispatch(),range(2)))
        self.transport.assert_called_once();self.assertEqual(self.row().state,'SENT')

    def test_consecutive_vouchers_to_one_recipient_are_spaced_without_dropping_jobs(self):
        req=self.publish();self.dispatch()
        fields=copy.deepcopy(req['invoices'][0]['fields']);fields['vendor_name']='Second final'
        self.assertEqual(self.a.revise(req,fields=fields).status_code,200)
        req=self.a.actor('owner').get('/api/requests/'+req['id']).json['data']
        self.assertEqual(self.a.decision(req).status_code,200)
        self.assertFalse(self.dispatch());self.transport.assert_called_once()
        with self.a.app.extensions['amiga_db'].begin() as db:
            first=db.scalar(select(TelegramDelivery).where(TelegramDelivery.version==1))
            first.sent_at='2000-01-01T00:00:00Z'
            self.assertEqual(db.scalar(select(TelegramDelivery.state).where(TelegramDelivery.version==2)),'QUEUED')
        self.assertTrue(self.dispatch());self.assertEqual(self.transport.call_count,2)

    def test_uncertain_and_interrupted_sends_are_terminal_and_never_retried(self):
        self.publish();self.transport.side_effect=TelegramError('TELEGRAM_UNCERTAIN',True)
        self.dispatch();self.assertEqual(self.row().state,'UNKNOWN')
        self.assertFalse(self.dispatch());self.transport.assert_called_once()
        with self.a.app.extensions['amiga_db'].begin() as db:
            row=db.scalar(select(TelegramDelivery));row.state='SENDING';row.expires_at='2000-01-01T00:00:00Z'
        self.dispatch();self.assertEqual(self.row().error_code,'AUTOMATIC_INTERRUPTED')
        self.assertFalse(self.dispatch());self.transport.assert_called_once()

    def test_definitive_failure_is_recorded_without_blocking_approved_voucher(self):
        req=self.publish();self.transport.side_effect=TelegramError('TELEGRAM_REJECTED')
        self.dispatch();self.assertEqual(self.row().state,'FAILED');self.assertFalse(self.dispatch())
        inv=self.a.actor('company').get('/api/requests/'+req['id']).json['data']['invoices'][0]
        self.assertIn('DOWNLOAD_VOUCHER',inv['allowed_actions']);self.transport.assert_called_once()

    def test_automatic_job_prevents_accidental_duplicate_manual_dispatch(self):
        req=self.publish()
        self.a.app.config['AGENT_RESPONDER']=lambda *args:{'answer':'Fixture result','next_steps':[],'intent':'ANSWER'}
        turn=self.a.call('finance','POST','/api/agents/chat',json={'request_id':req['id'],'question':'Ringkas hasil'}).json['data']
        inv=req['invoices'][0]
        result=self.a.call('finance','POST',f"/api/requests/{req['id']}/invoices/{inv['id']}/telegram-preview",json={
            'expected_version':1,'turn_id':turn['id']})
        self.assertEqual(result.status_code,409,result.json)
        self.assertEqual(result.json['error']['code'],'TELEGRAM_AUTOMATIC_EXISTS');self.transport.assert_not_called()
