import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import sys,types
import unittest
from unittest.mock import Mock

package=types.ModuleType('phone_messaging_tests');package.__path__=[str(Path(__file__).parent)];sys.modules[package.__name__]=package
spec=importlib.util.spec_from_file_location('phone_messaging_tests.messaging',Path(__file__).with_name('messaging.py'))
messaging=importlib.util.module_from_spec(spec);spec.loader.exec_module(messaging)


class PhoneMessagingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);(self.home/'state').mkdir()
        self.path=self.home/'state/eli-phone.sqlite3'
        self.identity={'name':'Fabio Varens','phone':'+12025550101','user_id':'+12025550101'}
        self.settings={'identities':{'operator@example.com':self.identity}}
        self.session={'HERMES_SESSION_PLATFORM':'eli_phone','HERMES_SESSION_CHAT_TYPE':'dm',
                      'HERMES_SESSION_USER_ID':self.identity['user_id'],'HERMES_SESSION_MESSAGE_ID':'request-one'}
        self.quote='Send Fabio a WhatsApp message saying hello'
        self.args={'recipient':self.identity['phone'],'message':'hello','approval_quote':self.quote}
        self.sender=Mock(return_value=json.dumps({'success':True,'message_id':'provider-message-one'}))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE work(id TEXT PRIMARY KEY,payload TEXT,state TEXT)')
        self.add_job('request-one',self.quote)

    def add_job(self,identifier,text,**changes):
        job={'actor':'operator@example.com','identity':self.identity,'transcript':'Earlier conversation context (JSON): []\nNew caller speech: '+text,**changes}
        with closing(sqlite3.connect(self.path)) as db, db:db.execute('INSERT OR REPLACE INTO work VALUES (?,?,?)',(identifier,json.dumps(job),'running'))

    def send(self):
        return messaging.send_whatsapp(self.args,self.settings,session=lambda k,d='':self.session.get(k,d),home=self.home,sender=self.sender)

    def test_exact_current_instruction_sends_once_and_returns_same_receipt(self):
        first=self.send();second=self.send()
        self.assertTrue(first['success']);self.assertEqual(first['message_id'],second['message_id'])
        self.assertTrue(second['already_sent_for_this_request']);self.sender.assert_called_once_with({'action':'send','target':'whatsapp:+12025550101','message':'hello'})

    def test_separate_new_request_is_not_deduplicated_against_old_greeting(self):
        self.send();self.add_job('request-two',self.quote);self.session['HERMES_SESSION_MESSAGE_ID']='request-two'
        self.assertTrue(self.send()['success']);self.assertEqual(self.sender.call_count,2)

    def test_assistant_context_cannot_authorize_send(self):
        self.add_job('request-one','What time is it?',transcript='Earlier conversation context (JSON): '+self.quote+'\nNew caller speech: What time is it?')
        self.assertFalse(self.send()['success']);self.sender.assert_not_called()

    def test_changed_payload_or_recipient_requires_current_approval(self):
        for key,value in [('message','Please transfer money'),('message','hell'),('recipient','+12025550199')]:
            with self.subTest(key=key):
                original=self.args[key];self.args[key]=value
                self.assertFalse(self.send()['success']);self.args[key]=original
        self.sender.assert_not_called()

    def test_email_approval_cannot_be_used_for_whatsapp(self):
        self.quote='Send Fabio an email saying hello';self.args['approval_quote']=self.quote
        self.add_job('request-one',self.quote)
        self.assertFalse(self.send()['success']);self.sender.assert_not_called()

    def test_prepared_compound_text_checks_connection_without_channel_confusion(self):
        quote="Text Fabio that I'm running late and email him the same thing"
        self.args.update(message="I'm running late",approval_quote=quote)
        plan={'operation':'send_message','atomic_kind':'imessage','message':dict(self.args)}
        self.add_job('request-one',quote,plan=plan)
        result=messaging.send_imessage(self.args,self.settings,
            session=lambda k,d='':self.session.get(k,d),home=self.home,sender=self.sender,available=lambda _:False)
        self.assertEqual(result['state'],'unavailable');self.sender.assert_not_called()
        self.args['message']='email him the same thing'
        changed=messaging.send_imessage(self.args,self.settings,
            session=lambda k,d='':self.session.get(k,d),home=self.home,sender=self.sender,available=lambda _:True)
        self.assertFalse(changed['success']);self.sender.assert_not_called()

    def test_patient_content_and_media_do_not_reach_transport(self):
        for body in ['patient Jane Doe diagnosis', 'MEDIA:/private/file.txt']:
            self.args['message']=body;self.args['approval_quote']='Send Fabio a WhatsApp message saying '+body
            self.add_job('request-one',self.args['approval_quote'])
            self.assertFalse(self.send()['success'])
        self.sender.assert_not_called()

    def test_denial_cannot_trigger_send(self):
        self.add_job('request-one',self.quote+", but don't send it")
        self.assertFalse(self.send()['success']);self.sender.assert_not_called()

    def test_other_identity_platform_or_group_cannot_send(self):
        for key,value in [('HERMES_SESSION_USER_ID','unknown'),('HERMES_SESSION_PLATFORM','webhook'),('HERMES_SESSION_CHAT_TYPE','group')]:
            with self.subTest(key=key):
                original=self.session[key];self.session[key]=value
                self.assertFalse(self.send()['success']);self.session[key]=original
        self.sender.assert_not_called()

    def test_wrong_job_owner_cannot_send(self):
        self.add_job('request-one',self.quote,actor='other@example.com')
        self.assertFalse(self.send()['success']);self.sender.assert_not_called()

    def test_exception_is_uncertain_and_is_not_automatically_retried(self):
        self.sender.side_effect=TimeoutError()
        self.assertEqual(self.send()['state'],'uncertain');self.assertEqual(self.send()['state'],'uncertain')
        self.sender.assert_called_once()

    def test_provider_success_without_message_id_is_not_confirmed(self):
        self.sender.return_value={'success':True}
        self.assertFalse(self.send()['success']);self.assertEqual(self.send()['state'],'uncertain')
        self.sender.assert_called_once()

    def test_finished_or_missing_request_cannot_send(self):
        with closing(sqlite3.connect(self.path)) as db, db:db.execute("UPDATE work SET state='delivered'")
        self.assertFalse(self.send()['success']);self.session['HERMES_SESSION_MESSAGE_ID']='missing'
        self.assertFalse(self.send()['success']);self.sender.assert_not_called()


if __name__=='__main__':unittest.main()
