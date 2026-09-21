import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

# Load the pure operation modules without importing the installed gateway.
root = Path(__file__).parent
package = ModuleType('phone_unit'); package.__path__ = [str(root)]
sys.modules['phone_unit'] = package
for name in ['performance','messaging','operations']:
    spec = importlib.util.spec_from_file_location('phone_unit.'+name,root/(name+'.py'))
    module = importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
performance = sys.modules['phone_unit.performance']
operations = sys.modules['phone_unit.operations']
messaging = sys.modules['phone_unit.messaging']


class OperationsTests(unittest.TestCase):
    def test_mail_uses_loaded_plugin_instance_instead_of_directory_import(self):
        registry_module=ModuleType('tools.registry')
        factory=Mock(return_value='existing-service')
        handler=SimpleNamespace(__globals__={'services':factory})
        registry_module.registry=SimpleNamespace(get_entry=lambda name:SimpleNamespace(handler=handler))
        with patch.dict(sys.modules,{'tools.registry':registry_module}):
            self.assertEqual(operations.mail_services(),'existing-service')
        factory.assert_called_once()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);(self.home/'state').mkdir()
        self.perf=performance.Performance(self.home/'state/eli-phone.sqlite3')
        self.identity={'name':'Fabio','phone':'+12025550101','user_id':'+12025550101'}
        self.settings={'identities':{'operator@example.com':self.identity}}
        self.session={'HERMES_SESSION_PLATFORM':'eli_phone','HERMES_SESSION_CHAT_TYPE':'dm',
            'HERMES_SESSION_USER_ID':self.identity['user_id'],'HERMES_SESSION_MESSAGE_ID':'job-one'}
        self.quote='Send Fabio an email saying hello'
        self.job={'id':'job-one','actor':'operator@example.com','identity':self.identity,
                  'transcript':'New caller speech: '+self.quote}
        with self.perf.db() as db:
            db.execute('CREATE TABLE work(id TEXT PRIMARY KEY,payload TEXT,state TEXT)')
            db.execute('INSERT INTO work VALUES (?,?,?)',('job-one',json.dumps(self.job),'running'))
        self.kw={'home':self.home,'session':lambda k,d='':self.session.get(k,d)}
        self.args={'recipient':'operator@example.com','message':'hello','approval_quote':self.quote}
        self.mail=Mock()
        self.mail.get_message.return_value={'message_id':'mail-one','to':['operator@example.com'],'subject':'Message from Eli'}
        self.services=SimpleNamespace(mail=self.mail)
        def invoke(name,args):
            if name=='email_send':return {'success':True,'recorded':True,'message_id':'mail-one','thread_id':'thread-one','task':{'task_id':'task-one'}}
            return {'success':True}
        self.invoke=Mock(side_effect=invoke)

    def send(self):
        return operations.send_email(self.args,self.settings,invoke=self.invoke,services=self.services,**self.kw)

    def fresh(self,text):
        self.job['transcript']='New caller speech: '+text
        with self.perf.db() as db:db.execute('UPDATE work SET payload=?',(json.dumps(self.job),))

    def test_email_sends_verifies_closes_and_deduplicates(self):
        first=self.send();second=self.send()
        self.assertTrue(first['source_verified']);self.assertTrue(first['tracking_closed'])
        self.assertTrue(second['already_attempted_for_this_request'])
        self.assertEqual([c.args[0] for c in self.invoke.call_args_list],['email_send','email_registry','email_registry'])

    def test_status_question_is_not_a_fresh_send_instruction(self):
        quote='Did you send Fabio an email saying hello?'
        self.fresh(quote);self.args['approval_quote']=quote
        self.assertFalse(self.send()['success']);self.invoke.assert_not_called()

    def test_cleanup_failure_retains_send_receipt_without_retry(self):
        self.mail.get_message.side_effect=TimeoutError()
        first=self.send();self.send()
        self.assertTrue(first['success']);self.assertFalse(first['source_verified'])
        self.assertEqual(self.invoke.call_count,3)
        self.assertTrue(first['tracking_closed'])

    def test_uncertain_email_is_never_automatically_resent(self):
        self.invoke.side_effect=TimeoutError()
        self.assertEqual(self.send()['state'],'uncertain');self.send()
        self.invoke.assert_called_once()

    def test_mail_channel_recipient_body_and_current_approval(self):
        for field,value in [('recipient','elsewhere@example.com'),('message','invented'),('approval_quote','An old email'),('subject','Unapproved subject')]:
            with self.subTest(field=field):
                original=self.args[field] if field in self.args else None;self.args[field]=value
                self.assertFalse(self.send()['success'])
                if original is None:self.args.pop(field)
                else:self.args[field]=original
        self.fresh("Send Fabio an email saying hello, but don't send it")
        self.assertFalse(self.send()['success']);self.invoke.assert_not_called()

    def test_latest_mail_combines_received_lookup_and_fetch(self):
        self.mail.list_messages.return_value=[{'message_id':'incoming-one','subject':'Meeting'}]
        self.mail.get_message.return_value={'message_id':'incoming-one','subject':'Meeting','text':'Untrusted email text','attachments':[{'id':'do-not-download'}]}
        result=operations.latest_email({'mailbox':'eli'},self.settings,services=self.services,**self.kw)
        self.assertTrue(result['success']);self.assertEqual(result['mailbox'],'Eli AgentMail')
        self.mail.list_messages.assert_called_once_with(limit=1,labels=['received'])
        self.mail.get_message.assert_called_once_with('incoming-one');self.assertNotIn('attachments',result)
        self.assertFalse(operations.latest_email({'mailbox':'personal'},self.settings,services=self.services,**self.kw)['success'])

    def test_patient_preview_stops_before_fetch(self):
        self.mail.list_messages.return_value=[{'message_id':'restricted','subject':'Patient Jane Doe MRN 12345'}]
        self.assertFalse(operations.latest_email({'mailbox':'eli'},self.settings,services=self.services,**self.kw)['success'])
        self.mail.get_message.assert_not_called()

    def test_imessage_unavailable_is_prompt_and_does_not_fallback(self):
        quote='Text Fabio saying hello';self.fresh(quote)
        sender=Mock()
        result=messaging.send_imessage({'recipient':self.identity['phone'],'message':'hello','approval_quote':quote},
            self.settings,sender=sender,available=lambda home:False,**self.kw)
        self.assertEqual(result['state'],'unavailable');self.assertTrue(result['pending']);sender.assert_not_called()

    def test_explicit_whatsapp_and_default_imessage_never_cross(self):
        for channel,quote in [('whatsapp','Text Fabio saying hello'),('imessage','Send Fabio a WhatsApp message saying hello')]:
            self.fresh(quote);sender=Mock(return_value={'success':True,'message_id':'msg-one'})
            result=messaging.send_message({'recipient':self.identity['phone'],'message':'hello','approval_quote':quote},
                self.settings,channel=channel,sender=sender,available=lambda home:True,**self.kw)
            self.assertFalse(result['success']);sender.assert_not_called()

    def test_available_imessage_has_its_own_once_only_receipt(self):
        quote='Text Fabio saying hello';self.fresh(quote);sender=Mock(return_value={'success':True,'message_id':'im-one'})
        args={'recipient':self.identity['phone'],'message':'hello','approval_quote':quote}
        for _ in range(2):self.assertTrue(messaging.send_imessage(args,self.settings,sender=sender,available=lambda home:True,**self.kw)['success'])
        sender.assert_called_once_with({'action':'send','target':'imessage:+12025550101','message':'hello'})

    def test_metadata_feedback_survives_restart_without_content(self):
        active=performance.current(self.settings,**self.kw)
        with patch.object(performance,'current',return_value=active):
            performance.after_tool(self.settings,tool_name='search_files',args={'path':'private-content'},result={'error':'private error'},duration_ms=63000)
            blocked=performance.before_tool(self.settings,tool_name='search_files',args={'path':'private-content'})
            self.assertTrue(blocked['block'])
            ctx=performance.context(self.settings,operations.SCHEMAS)['context']
            self.assertIn('63000',ctx);self.assertNotIn('private-content',ctx);self.assertNotIn('private error',ctx)
        fresh=performance.Performance(self.perf.path)
        self.assertEqual(fresh.feedback()[0]['failures'],1)

    def test_action_progress_requires_receipt_and_is_idempotent(self):
        active=performance.current(self.settings,**self.kw)
        with patch.object(performance,'current',return_value=active):
            performance.after_tool(self.settings,tool_name='email_send',result={'success':True})
            self.assertFalse(any(e['kind']=='action' for e in self.perf.pending()))
            for _ in range(2):performance.after_tool(self.settings,tool_name='email_send',result={'success':True,'message_id':'receipt'})
        actions=[e for e in self.perf.pending() if e['kind']=='action']
        self.assertEqual(len(actions),1)
        self.perf.delivered([e['id'] for e in self.perf.pending()]);self.assertEqual(self.perf.pending(),[])

    def test_false_send_claim_is_replaced(self):
        text=performance.verified_answer(self.perf,self.job,'I sent the email to Fabio.')
        self.assertIn('do not have a fresh send confirmation',text)
        active=performance.current(self.settings,**self.kw)
        with patch.object(performance,'current',return_value=active):
            self.assertEqual(performance.transform_answer(self.settings,response_text='I sent the email to Fabio.'),text)

    def test_one_receipt_does_not_confirm_two_channels(self):
        self.job['transcript']='New caller speech: Send Fabio an email and an iMessage saying hello'
        self.perf.record('job-one','action','email_send','sent',content='Email confirmed.')
        result=performance.verified_answer(self.perf,self.job,'I sent both messages.')
        self.assertIn('Confirmed sent for this request: email.',result)
        self.assertIn('do not have a confirmed send for imessage',result)

    def test_observers_ignore_nonphone_and_mismatched_identity(self):
        for key,value in [('HERMES_SESSION_PLATFORM','whatsapp'),('HERMES_SESSION_USER_ID','somebody-else'),('HERMES_SESSION_MESSAGE_ID','missing')]:
            old=self.session[key];self.session[key]=value
            self.assertIsNone(performance.current(self.settings,**self.kw));self.session[key]=old


if __name__=='__main__':unittest.main()
