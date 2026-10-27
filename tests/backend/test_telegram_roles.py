"""Telegram recipient, official voucher dispatch and private admin settings. No network."""
import json
import unittest
from pathlib import Path
from unittest.mock import Mock
from sqlalchemy import select
import test_workflow_agents as workflow
from backend.models import Audit,Setting
from backend.telegram_config import bot_dto
from backend.telegram_service import TelegramError


class TelegramRoleTests(unittest.TestCase):
    setUp=workflow.WorkflowAgentTests.setUp
    tearDown=workflow.WorkflowAgentTests.tearDown
    detail=workflow.WorkflowAgentTests.detail
    prepare=workflow.WorkflowAgentTests.prepare
    confirm=workflow.WorkflowAgentTests.confirm
    chat=workflow.WorkflowAgentTests.chat
    linked=workflow.WorkflowAgentTests.linked
    preview=workflow.WorkflowAgentTests.preview
    def save_bot(self,token=None,actor='admin',revision=None):
        state=self.a.actor('admin').get('/api/admin/telegram-bot').json['data']
        return self.a.call(actor,'PATCH','/api/admin/telegram-bot',json={
            'token':token or '123456789:'+('x'*35),
            'expected_revision':revision if revision is not None else state['revision']})

    def bot_transport(self):
        return Mock(side_effect=lambda method,payload,pdf: {'id':123456789,'is_bot':True,'username':'amiga_fixture_bot'}
                    if method=='getMe' else {'url':''} if method=='getWebhookInfo' else {'message_id':123})

    def test_bot_settings_only_admin_and_token_never_returned_or_audited(self):
        transport=self.bot_transport();self.a.app.config['TELEGRAM_TRANSPORT']=transport
        for actor in ('owner','finance','lead'):
            self.assertEqual(self.a.actor(actor).get('/api/admin/telegram-bot').status_code,403)
            self.assertEqual(self.save_bot(actor=actor).status_code,403)
        self.assertEqual(self.a.actor('admin').patch('/api/admin/telegram-bot',json={}).status_code,403)
        token='123456789:'+('x'*35)
        result=self.save_bot(token)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['data']['username'],'amiga_fixture_bot')
        self.assertEqual(result.json['data']['bot_id'],'123456789')
        self.assertNotIn(token,result.get_data(as_text=True))
        self.assertEqual([call.args[0] for call in transport.call_args_list],['getMe','getWebhookInfo'])
        path=Path(self.a.app.config['UPLOAD_DIR']).parent/'.telegram-bot.json'
        self.assertEqual(json.loads(path.read_text())['token'],token)
        with self.a.app.extensions['amiga_db']() as db:
            self.assertNotIn(token,repr(list(db.scalars(select(Audit.changes)))))
            self.assertNotIn(token,repr(list(db.scalars(select(Setting.value)))))
        self.assertNotIn(token,self.a.actor('company').get('/api/telegram/status').get_data(as_text=True))

    def test_failed_verification_and_webhook_preserve_previous_configuration(self):
        original=bot_dto(self.a.app.config)
        for transport in (Mock(side_effect=TelegramError('TELEGRAM_REJECTED')),
                          Mock(side_effect=lambda method,*args:{'id':123456789,'is_bot':True,'username':'amiga_fixture_bot'} if method=='getMe' else {'url':'https://fictional.invalid/hook'})):
            self.a.app.config['TELEGRAM_TRANSPORT']=transport
            self.assertIn(self.save_bot().status_code,(409,422))
            self.assertEqual(bot_dto(self.a.app.config),original)
        self.assertEqual(self.save_bot(revision='stale').status_code,409)

    def test_contact_without_start_is_never_a_send_destination(self):
        self.assertEqual(self.a.call('company','PATCH','/api/telegram/contact',json={}).status_code,422)
        self.assertEqual(self.a.call('company','PATCH','/api/telegram/contact',json={'contact':'+628111234567'}).status_code,422)
        saved=self.a.call('company','PATCH','/api/telegram/contact',json={'contact':'@Fictional_Owner'})
        self.assertEqual(saved.status_code,200,saved.json)
        self.assertEqual(saved.json['data']['contact'],'@fictional_owner')
        self.assertFalse(saved.json['data']['connected'])
        self.assertEqual(self.a.call('finance','PATCH','/api/telegram/contact',json={'contact':'123456'}).status_code,403)
        req=self.prepare();self.a.take(req)
        self.assertEqual(self.preview(req).status_code,409)

    def test_start_must_match_declared_contact_and_no_send_occurs(self):
        self.a.app.config['TELEGRAM_BOT_TOKEN']='fictional-token'
        self.a.call('company','PATCH','/api/telegram/contact',json={'contact':'@correct_owner'})
        url=self.a.call('company','POST','/api/telegram/link',json={}).json['data']['url']
        token=url.split('start=')[1]
        def event(username,number):
            return [{'update_id':number,'message':{'text':'/start '+token,'chat':{'type':'private','id':123456},'from':{'id':123456,'username':username}}}]
        transport=Mock(return_value=event('wrong_owner',1));self.a.app.config['TELEGRAM_TRANSPORT']=transport
        result=self.a.call('company','POST','/api/telegram/verify',json={})
        self.assertFalse(result.json['data']['connected'])
        transport.return_value=event('correct_owner',2)
        result=self.a.call('company','POST','/api/telegram/verify',json={})
        self.assertTrue(result.json['data']['connected'])
        self.assertTrue(all(call.args[0]=='getUpdates' for call in transport.call_args_list))

    def test_admin_can_forward_official_voucher_but_cannot_approve_it(self):
        req=self.prepare();self.a.take(req);self.linked();inv=req['invoices'][0]
        endpoint=f"/api/requests/{req['id']}/invoices/{inv['id']}"
        self.assertEqual(self.a.call('admin','POST',endpoint+'/approve',json={'expected_version':1}).status_code,403)
        turn=self.chat(req,actor='admin').json['data']
        self.assertEqual(self.a.call('admin','POST',endpoint+'/telegram-preview',json={'expected_version':1,'turn_id':turn['id']}).status_code,409)
        self.assertEqual(self.a.decision(req).status_code,200)
        # Model elapsed time without sleeping or relaxing the actual rate limit.
        from backend.models import AgentTurn
        with self.a.app.extensions['amiga_db'].begin() as db:
            for old in db.scalars(select(AgentTurn).where(AgentTurn.user_id=='admin')):
                old.created_at='2000-01-01T00:00:00.000000Z'
        turn=self.chat(req,actor='admin').json['data']
        response=self.a.call('admin','POST',endpoint+'/telegram-preview',json={'expected_version':1,'turn_id':turn['id']})
        self.assertEqual(response.status_code,201,response.json)
        row=response.json['data'];self.assertTrue(row['has_voucher'])
        transport=Mock(return_value={'message_id':42});self.a.app.config['TELEGRAM_TRANSPORT']=transport
        path='/api/telegram/previews/'+row['id']+'/send'
        self.assertEqual(self.a.call('admin','POST',path,json={'approved':False,'preview_hash':row['preview_hash']}).status_code,422)
        self.assertEqual(self.a.call('admin','POST',path,json={'approved':True,'preview_hash':row['preview_hash']}).json['data']['state'],'SENT')
        self.assertEqual(transport.call_args.args[0],'sendDocument')
        self.assertTrue(transport.call_args.args[2].startswith(b'%PDF'))
        transport.assert_called_once()

    def test_bot_change_invalidates_link_challenge_and_old_preview(self):
        req=self.prepare();self.a.take(req);self.linked();row=self.preview(req).json['data']
        self.a.call('company','POST','/api/telegram/link',json={})
        transport=self.bot_transport();self.a.app.config['TELEGRAM_TRANSPORT']=transport
        self.assertEqual(self.save_bot().status_code,200)
        self.assertFalse(self.a.actor('company').get('/api/telegram/status').json['data']['connected'])
        self.assertEqual(self.a.call('company','POST','/api/telegram/verify',json={}).status_code,409)
        self.assertEqual(self.a.call('finance','POST','/api/telegram/previews/'+row['id']+'/send',json={'approved':True,'preview_hash':row['preview_hash']}).status_code,409)
        self.assertTrue(all(call.args[0] in ('getMe','getWebhookInfo') for call in transport.call_args_list))

    def test_contact_change_invalidates_link_and_pending_preview(self):
        req=self.prepare();self.a.take(req);self.linked();row=self.preview(req).json['data']
        result=self.a.call('company','PATCH','/api/telegram/contact',json={'contact':'@new_contact'})
        self.assertFalse(result.json['data']['connected'])
        self.assertEqual(self.a.call('finance','POST','/api/telegram/previews/'+row['id']+'/send',json={'approved':True,'preview_hash':row['preview_hash']}).status_code,409)
