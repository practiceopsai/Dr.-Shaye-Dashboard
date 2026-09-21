import json
import unittest
from unittest.mock import Mock, patch
import test_operations as support
from phone_unit import clarification


class ClarificationTests(unittest.TestCase):
    setUp=support.OperationsTests.setUp

    def test_question_is_durable_and_blocks_further_actions(self):
        result=clarification.clarify({'question':'What should I say?'},self.settings,**self.kw)
        self.assertEqual(result['state'],'waiting_for_input')
        self.assertEqual(clarification.question_for(self.perf,self.job['id']),'What should I say?')
        with patch.object(support.performance,'current',return_value=(self.perf,self.job,self.quote)):
            blocked=support.performance.before_tool(self.settings,tool_name='email_send',args={})
        self.assertTrue(blocked['block'])

    def test_question_does_not_overwrite_first_missing_detail(self):
        clarification.clarify({'question':'Which account?'},self.settings,**self.kw)
        result=clarification.clarify({'question':'What day?'},self.settings,**self.kw)
        self.assertEqual(result['question'],'Which account?')

    def test_answer_uses_real_open_task_and_current_words(self):
        self.job['open_questions']=[{'id':'question-one','question':'What should I say?'}]
        self.job['claim']='claim-for-current-job'
        self.job['transcript']='New caller speech: Say hello.'
        with self.perf.db() as db:
            db.execute('UPDATE work SET payload=?',(json.dumps(self.job),))
        api=Mock(return_value={'status':'resumed','job_id':'continuation'})
        result=clarification.answer_clarification({'request_id':'question-one','answer_quote':'Say hello.'},self.settings,api=api,**self.kw)
        self.assertTrue(result['success']);self.assertEqual(result['job_id'],'continuation')
        api.assert_called_once()
        api.reset_mock()
        for args in [{'request_id':'other-person','answer_quote':'Say hello.'},{'request_id':'question-one','answer_quote':'Invented message'}]:
            self.assertFalse(clarification.answer_clarification(args,self.settings,api=api,**self.kw)['success'])
        api.assert_not_called()

    def test_email_receipt_is_reused_across_resumed_job(self):
        first=support.operations.send_email(self.args,self.settings,invoke=self.invoke,services=self.services,**self.kw)
        self.assertTrue(first['success'])
        self.job.update(id='continuation',root_id='job-one')
        self.session['HERMES_SESSION_MESSAGE_ID']='continuation'
        with self.perf.db() as db:
            db.execute('INSERT INTO work VALUES (?,?,?)',('continuation',json.dumps(self.job),'running'))
        second=support.operations.send_email(self.args,self.settings,invoke=self.invoke,services=self.services,**self.kw)
        self.assertTrue(second['already_attempted_for_this_request'])
        self.assertEqual(sum(c.args[0]=='email_send' for c in self.invoke.call_args_list),1)

    def test_text_receipt_is_reused_across_resumed_job(self):
        self.quote='Send Fabio a WhatsApp message saying hello'
        self.job['transcript']='New caller speech: '+self.quote
        with self.perf.db() as db: db.execute('UPDATE work SET payload=?',(json.dumps(self.job),))
        args={'recipient':self.identity['phone'],'message':'hello','approval_quote':self.quote}
        sender=Mock(return_value={'success':True,'message_id':'test-receipt'})
        first=support.messaging.send_whatsapp(args,self.settings,sender=sender,**self.kw)
        self.assertTrue(first['success'])
        self.job.update(id='continuation',root_id='job-one');self.session['HERMES_SESSION_MESSAGE_ID']='continuation'
        with self.perf.db() as db:
            db.execute('INSERT INTO work VALUES (?,?,?)',('continuation',json.dumps(self.job),'running'))
        self.assertTrue(support.messaging.send_whatsapp(args,self.settings,sender=sender,**self.kw)['already_sent_for_this_request'])
        sender.assert_called_once()

    def test_question_fallback_does_not_treat_greeting_as_clarification(self):
        self.assertTrue(clarification.possible_question('Which account should I check?'))
        self.assertFalse(clarification.possible_question('Anything else?'))


if __name__=='__main__': unittest.main()
