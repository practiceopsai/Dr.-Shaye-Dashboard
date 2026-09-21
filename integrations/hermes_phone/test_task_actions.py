import json,sys,tempfile,types,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock,patch

pkg=types.ModuleType('phone_task_tests');pkg.__path__=[str(Path(__file__).parent)];sys.modules[pkg.__name__]=pkg
from phone_task_tests import articles,calendar_invites as calendars,performance,messaging,effects

FEED=b'''<rss><channel><item><title>AI article</title><link>https://news.google.com/rss/articles/test</link><pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate><source>Example</source></item></channel></rss>'''


class TaskActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name);(self.home/'state').mkdir()
        self.perf=performance.Performance(self.home/'state/eli-phone.sqlite3')
        self.identity={'name':'Fabio','phone':'+12025550101','user_id':'operator'}
        self.settings={'identities':{'fabio@example.com':self.identity}}
        self.job={'id':'revision-one','root_id':'root-one','actor':'fabio@example.com','identity':self.identity}
        self.session={'HERMES_SESSION_PLATFORM':'eli_phone','HERMES_SESSION_CHAT_TYPE':'dm','HERMES_SESSION_USER_ID':'operator','HERMES_SESSION_MESSAGE_ID':self.job['id']}
        with self.perf.db() as db:db.execute('CREATE TABLE work(id TEXT PRIMARY KEY,payload TEXT,state TEXT)')
        self.perf_patch=patch.object(performance,'current',side_effect=lambda *a,**kw:(self.perf,self.job,self.job['transcript']))
        self.perf_patch.start();self.addCleanup(self.perf_patch.stop)
        self.quote="Send Fabio a calendar invitation titled AI Test Meeting tomorrow at 2 PM Pacific for one hour from Eli's email."
        self.spec={'title':'AI Test Meeting','date':'2027-09-22','time':'14:00','timezone':'America/Los_Angeles','duration_minutes':'60','organizer':'eli','recipient':'fabio@example.com','approval_quote':self.quote}
        self.job.update(transcript='New caller speech: '+self.quote,plan={'operation':'calendar_invitation','atomic_kind':'calendar','calendar':self.spec,'required_receipts':['calendar']})
        self.mail=Mock();self.svc=types.SimpleNamespace(mail=self.mail,settings=types.SimpleNamespace(effective_from_address='eli@example.com',principal_addresses=['shaye@example.com','shaye-work@example.com']))
        self.sent=[]
        def invoke(name,args):
            if name=='email_send':
                self.sent.append(args)
                self.mail.get_message.return_value={'message_id':'invitation-one','subject':args['subject'],'to':args['to'],'attachments':[{'filename':'invitation.ics','attachment_id':'attachment-one'}]}
                self.mail.download_attachment.return_value=args['attachments'][0]
                return {'message_id':'invitation-one','thread_id':'thread','task':{'task_id':'task'}}
            return {'success':True}
        self.invoke=Mock(side_effect=invoke)

    def calendar(self,**kw):return calendars.run(self.job,self.settings,self.perf,services=self.svc,invoke=self.invoke,now=0,**kw)

    def test_eli_invites_principal_and_guest_and_survives_repeat(self):
        first=self.calendar();second=self.calendar()
        self.assertTrue(first['source_verified']);self.assertEqual(first['recipients'],['shaye@example.com','fabio@example.com'])
        self.assertTrue(second['already_attempted_for_this_request']);self.assertEqual(len(self.sent),1)
        ics=Path(self.sent[0]['attachments'][0]).read_text().replace('\n ','')
        for text in ['METHOD:REQUEST','ORGANIZER:mailto:eli@example.com','mailto:shaye@example.com','mailto:fabio@example.com','DTSTART:20270922T210000Z','DTEND:20270922T220000Z']:
            self.assertIn(text,ics)
        self.assertFalse(performance.missing_send_receipt(self.perf,self.job))

    def test_calendar_wrong_recipients_or_missing_attachment_never_completes(self):
        self.mail.get_message.side_effect=lambda *a:{'message_id':'invitation-one','subject':'AI Test Meeting','to':['fabio@example.com'],'attachments':[]}
        result=self.calendar();self.assertFalse(result['success']);self.assertEqual(result['state'],'uncertain')
        self.calendar();self.assertEqual(len(self.sent),1)
        self.assertTrue(performance.missing_send_receipt(self.perf,self.job))

    def test_provider_timeout_never_replays_invitation(self):
        self.invoke.side_effect=TimeoutError()
        self.assertFalse(self.calendar()['success']);self.calendar();self.invoke.assert_called_once()

    def test_title_proposal_requires_the_callers_recorded_affirmation(self):
        self.quote="Send Fabio a calendar invitation tomorrow at 2 PM Pacific for one hour from Eli's email.\nYes, correct"
        self.job['transcript']='New caller speech: '+self.quote;self.spec['approval_quote']=self.quote
        self.spec['confirmed_proposals']=[{'spoken_prompt':'Shall I title it AI Test Meeting?','answer':'Yes, correct','question_id':'question-one'}]
        self.assertTrue(self.calendar()['source_verified'])
        self.spec['confirmed_proposals'][0]['answer']='No'
        with self.assertRaises(ValueError):self.calendar()

    def test_principal_calendar_cannot_be_mutated_by_operator(self):
        self.spec['organizer']='principal';connector=Mock()
        result=self.calendar(config={},calendar_call=connector)
        self.assertEqual(result['state'],'blocked');connector.assert_not_called();self.invoke.assert_not_called()

    def test_principal_calendar_requires_readback_and_notifies_guest(self):
        self.spec['organizer']='principal'
        config={'memory':{'eli_vault':{'allowed_user_ids':['operator']}},'plugins':{'entries':{'eli_persona':{'settings':{'principal_user_ids':['operator']}}}}}
        event={'id':'event-one','summary':'AI Test Meeting','status':'confirmed','attendees':[{'email':'fabio@example.com'}],
            'start':{'dateTime':'2027-09-22T14:00:00-07:00'},'end':{'dateTime':'2027-09-22T15:00:00-07:00'}}
        connector=Mock(side_effect=[{'data':{'response_data':event}},{'data':{'event_data':event}}])
        result=self.calendar(config=config,calendar_call=connector)
        self.assertTrue(result['source_verified']);self.assertEqual(connector.call_args_list[0].args[1]['send_updates'],'all')
        self.assertFalse(connector.call_args_list[0].args[1]['create_meeting_room']);self.invoke.assert_not_called()

    def article(self):
        quote='Find any AI article and send the link to Fabio by WhatsApp.'
        self.job.update(transcript='New caller speech: '+quote,plan={'operation':'find_send_article','atomic_kind':'article','required_receipts':['whatsapp'],
            'article':{'channel':'whatsapp','query':'AI','selection':'any','recipient':self.identity['phone'],'approval_quote':quote}})
        with self.perf.db() as db:db.execute('INSERT OR REPLACE INTO work VALUES (?,?,?)',(self.job['id'],json.dumps(self.job),'running'))
        sender=Mock(return_value={'success':True,'message_id':'article-one'})
        def send(channel,args):return messaging.send_message(args,self.settings,channel=channel,home=self.home,
            session=lambda k,d='':self.session.get(k,d),sender=sender)
        return send,sender

    def test_article_selected_content_is_authorized_without_dictating_url(self):
        send,sender=self.article()
        for _ in range(2):self.assertTrue(articles.run(self.job,self.settings,self.perf,fetch=lambda u:FEED,send=send)['success'])
        sender.assert_called_once();self.assertIn('https://news.google.com/',sender.call_args.args[0]['message'])
        self.assertFalse(performance.missing_send_receipt(self.perf,self.job))
        with self.perf.db() as db:args=json.loads(db.execute('SELECT payload FROM phone_article_artifacts').fetchone()[0])['args']
        args['message']='A different unapproved message'
        self.assertFalse(send('whatsapp',args)['success']);sender.assert_called_once()

    def test_article_receipt_does_not_complete_calendar(self):
        calendar=self.job.copy();send,sender=self.article()
        articles.run(self.job,self.settings,self.perf,fetch=lambda u:FEED,send=send)
        self.assertTrue(performance.missing_send_receipt(self.perf,calendar))

    def test_article_short_channel_confirmation_survives_native_guard(self):
        send,sender=self.article()
        quote='Find any AI article and send the link to Fabio.\nYes, correct'
        self.job['transcript']='New caller speech: '+quote
        self.job['plan']['article'].update(approval_quote=quote,confirmed_proposals=[{'question_id':'article-question','spoken_prompt':'Send the article by WhatsApp, correct?','answer':'Yes, correct'}])
        with self.perf.db() as db:db.execute('UPDATE work SET payload=? WHERE id=?',(json.dumps(self.job),self.job['id']))
        self.assertTrue(articles.run(self.job,self.settings,self.perf,fetch=lambda u:FEED,send=send)['success'])
        sender.assert_called_once()
        spec=self.job['plan']['article']
        spec['confirmed_proposals'][0]['spoken_prompt']='Email or WhatsApp?'
        self.assertFalse(articles.channel_approved(spec,quote))
        spec['confirmed_proposals'][0]['spoken_prompt']='Send it by WhatsApp?'
        spec['confirmed_proposals'][0]['answer']='No'
        self.assertFalse(articles.channel_approved(spec,quote))

    def test_article_email_confirmation_reaches_email_guard(self):
        from phone_task_tests import operations
        quote='Find an AI article and send the link to Fabio.\nYes, correct'
        self.job.update(transcript='New caller speech: '+quote,plan={'operation':'find_send_article','atomic_kind':'article','required_receipts':['email'],
            'article':{'channel':'email','query':'AI','selection':'any','recipient':'fabio@example.com','approval_quote':quote,
                'confirmed_proposals':[{'question_id':'article-question','spoken_prompt':'Send the article by email, correct?','answer':'Yes, correct'}]}})
        self.mail.get_message.return_value={'message_id':'article-email-one','to':['fabio@example.com'],'subject':'Message from Eli'}
        invoke=Mock(side_effect=lambda name,args:{'message_id':'article-email-one','thread_id':'thread','task':{'task_id':'task'}} if name=='email_send' else {'success':True})
        with patch.object(operations,'current',return_value=(self.perf,self.job,self.job['transcript'])):
            send=lambda channel,args:operations.send_email(args,self.settings,services=self.svc,invoke=invoke)
            result=articles.run(self.job,self.settings,self.perf,fetch=lambda u:FEED,send=send)
        self.assertTrue(result['source_verified']);self.assertFalse(performance.missing_send_receipt(self.perf,self.job))
        self.assertEqual(sum(c.args[0]=='email_send' for c in invoke.call_args_list),1)

    def test_feed_failure_never_sends(self):
        send,sender=self.article()
        self.assertFalse(articles.run(self.job,self.settings,self.perf,fetch=lambda u:b'<!DOCTYPE rss><rss/>',send=send)['success'])
        sender.assert_not_called()

    def test_calendar_and_article_both_complete_only_after_distinct_receipts(self):
        calendar=self.job.copy();self.assertTrue(self.calendar()['success'])
        self.job={**self.job,'id':'revision-two','root_id':'root-two'};self.session['HERMES_SESSION_MESSAGE_ID']=self.job['id']
        send,sender=self.article();result=articles.run(self.job,self.settings,self.perf,fetch=lambda u:FEED,send=send)
        self.assertTrue(result['success']);self.assertFalse(performance.missing_send_receipt(self.perf,self.job))
        self.assertFalse(performance.missing_send_receipt(self.perf,calendar));self.assertEqual(len(self.sent),1);sender.assert_called_once()

    def test_verified_email_receipt_counts_and_promotes_existing_accepted_event(self):
        self.job['plan']={'atomic_kind':'email'}
        self.perf.record(self.job['id'],'action','email_send','verified')
        self.assertFalse(performance.missing_send_receipt(self.perf,self.job))
        performance.after_tool(self.settings,tool_name='email_send',result={'success':True,'message_id':'mail-one'})
        performance.after_tool(self.settings,tool_name='eli_phone_send_email',result={'success':True,'message_id':'mail-one','source_verified':True})
        with self.perf.db() as db:self.assertEqual(db.execute("SELECT status FROM execution_events WHERE fingerprint!='' AND kind='action'").fetchone()[0],'sent')


if __name__=='__main__':unittest.main()
