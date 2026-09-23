import asyncio,importlib,json,sys,time,types,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch

pkg=types.ModuleType('cross_unit');pkg.__path__=[str(Path(__file__).parent)];sys.modules[pkg.__name__]=pkg
cross=importlib.import_module('cross_unit.cross_channel')


class CrossChannelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'journal.sqlite3'
        self.source=types.SimpleNamespace(platform=types.SimpleNamespace(value='whatsapp'),chat_type='dm',user_id='user1',chat_id='chat1')
        self.event=types.SimpleNamespace(source=self.source,text='Cancel the presentation task',message_id='msg1')
        self.gateway=Mock();self.gateway._is_user_authorized.return_value=True
        self.settings={'identities':{'owner@example.com':{'user_id':'user1'}}}
    def hook(self):
        with patch.object(cross,'path',return_value=self.db),patch.object(cross,'_ready',True):return cross.hook(self.settings,event=self.event,gateway=self.gateway)
    def test_authorized_task_is_persisted_once_and_original_dispatch_consumed(self):
        self.assertEqual(self.hook()['action'],'skip');self.assertEqual(self.hook()['action'],'skip')
        self.assertEqual(len(cross.ready(self.db)),1)
    def test_unauthorized_group_or_unmapped_sender_cannot_control_ledger(self):
        self.gateway._is_user_authorized.return_value=False;self.assertIsNone(self.hook())
        self.gateway._is_user_authorized.return_value=True;self.source.chat_type='group';self.assertIsNone(self.hook())
        self.source.chat_type='dm';self.source.user_id='stranger';self.assertIsNone(self.hook())
    def test_chat_and_internal_phone_work_keep_native_pipeline(self):
        self.event.text='What is your name?';self.assertIsNone(self.hook())
        self.event.text='Send the document';self.source.platform.value='eli_phone';self.assertIsNone(self.hook())
    def test_calls_from_either_registered_chat_identity_are_captured(self):
        self.settings['identities']['operator@example.com']={'user_id':'user2'}
        for platform in ['photon','bluebubbles','whatsapp']:
            for user in ['user1','user2']:
                self.source.platform.value=platform;self.source.user_id=user
                for text in ['Call me','Can you call me?','Please call Dr. Shaye and tell him hello',
                             'Call Fabio and tell him hello','Can you give me a call?','Eli, call me']:
                    with self.subTest(platform=platform,user=user,text=text):
                        self.event.text=text;self.event.message_id=platform+user+text
                        self.assertEqual(self.hook()['action'],'skip')
        with cross.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM task_ingress').fetchone()[0],36)
    def test_call_history_and_capability_questions_remain_conversation(self):
        for text in ['What did I ask on our last call?','How can you call me?','Can you call people?',
                     'Did you call Dr. Shaye?','My phone is broken','I enjoyed our last call']:
            with self.subTest(text=text):
                self.event.text=text;self.assertIsNone(self.hook())
    def test_restart_preserves_ingress_message_id(self):
        self.hook();first=cross.ready(self.db)
        self.assertEqual(cross.ready(self.db),first)
        self.assertEqual(first[0]['state'],'pending')
    def test_old_voice_questions_do_not_capture_text_conversation(self):
        with cross.connect(self.db) as db:db.execute('INSERT INTO task_question_actors VALUES (?,?,?)',('owner@example.com',1,1))
        for text in ['Who are you?','Hello?','Helloooo Eli?','?','What was the last message Dr Shaye sent','Yes','One hour, Pacific time']:
            with self.subTest(text=text):
                self.event.text=text;self.assertIsNone(self.hook())
        self.assertEqual(cross.ready(self.db),[])
    def test_freeform_answer_requires_question_in_same_text_conversation(self):
        with cross.connect(self.db) as db:db.execute('INSERT INTO task_text_questions VALUES (?,?,?,?,?)',('owner@example.com','whatsapp','chat1','question1',time.time()))
        self.event.text='One hour, Pacific time'
        self.assertEqual(self.hook()['action'],'skip')
        self.source.chat_id='another-chat';self.assertIsNone(self.hook())
        self.source.chat_id='chat1';self.source.platform.value='photon';self.assertIsNone(self.hook())
        self.source.platform.value='whatsapp'
        for text in ['Who are you?','Hello?','Are you there?','?']:
            self.event.text=text;self.assertIsNone(self.hook())
    def adapter(self):
        return types.SimpleNamespace(journal=types.SimpleNamespace(path=self.db),_running=True,
                                     _message_handler=types.SimpleNamespace(__self__=self.gateway))
    def restored_source(self,saved):
        return types.SimpleNamespace(**saved,delivered_via_upstream_relay=False)
    def api(self,path,payload):
        if path.endswith('/utterance'):return {'intake_id':'intake1','call_id':'call1'}
        if path.endswith('/capabilities'):return {'ledger_version':1,'text_ingress':True}
        if path.endswith('/state'):return {'questions':[{'id':'question1'}]}
        return {'notices':[{'id':'question1','state':'waiting_for_input','content':'Which recipient?'}],'settled':False}
    def test_handoff_delivers_question_once_and_routes_its_answer(self):
        self.hook();adapter=self.adapter();target=types.SimpleNamespace(send=AsyncMock(return_value=types.SimpleNamespace(success=True)))
        self.gateway._adapter_for_source.return_value=target
        with patch.object(cross,'restore_source',side_effect=self.restored_source):
            asyncio.run(cross.process_item(adapter,self.api,self.gateway,cross.ready(self.db)[0]))
            asyncio.run(cross.process_item(adapter,self.api,self.gateway,cross.ready(self.db)[0]))
        self.assertEqual(target.send.await_count,1)
        self.event.message_id='answer1';self.event.text='Fabio'
        self.assertEqual(self.hook()['action'],'skip')
    def test_transport_unknown_outcome_is_not_resent(self):
        self.hook();adapter=self.adapter();target=types.SimpleNamespace(send=AsyncMock(side_effect=TimeoutError()))
        self.gateway._adapter_for_source.return_value=target
        with patch.object(cross,'restore_source',side_effect=self.restored_source):
            with self.assertRaises(TimeoutError):asyncio.run(cross.process_item(adapter,self.api,self.gateway,cross.ready(self.db)[0]))
            asyncio.run(cross.process_item(adapter,self.api,self.gateway,cross.ready(self.db)[0]))
        self.assertEqual(target.send.await_count,1)
        with cross.connect(self.db) as db:self.assertEqual(db.execute('SELECT state FROM task_text_notices').fetchone()[0],'uncertain')
    def test_failed_item_backs_off_without_blocking_next_message(self):
        self.hook();self.event.message_id='msg2';self.hook();adapter=self.adapter();seen=[]
        async def process(adapter,api,gateway,item):
            seen.append(item['id'])
            if len(seen)==1:raise AttributeError('contract failure')
            adapter._running=False
        with patch.object(cross,'process_item',side_effect=process),patch.object(cross,'_ready',True):
            asyncio.run(cross.pump(adapter,self.api))
        self.assertEqual(len(seen),2)
        with cross.connect(self.db) as db:
            first=dict(db.execute('SELECT * FROM task_ingress WHERE id=?',(seen[0],)).fetchone())
        self.assertEqual(first['error'],'AttributeError');self.assertGreater(first['next_attempt'],first['created'])
    def test_revoked_identity_never_reaches_backend(self):
        self.hook();self.gateway._is_user_authorized.return_value=False;api=Mock()
        with patch.object(cross,'restore_source',side_effect=self.restored_source):
            asyncio.run(cross.process_item(self.adapter(),api,self.gateway,cross.ready(self.db)[0]))
        api.assert_not_called();self.assertEqual(cross.ready(self.db),[])

if __name__=='__main__':unittest.main()
