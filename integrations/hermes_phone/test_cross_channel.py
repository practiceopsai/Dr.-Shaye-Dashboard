import importlib,sys,types,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch

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
    def test_restart_preserves_ingress_message_id(self):
        self.hook();first=cross.ready(self.db)
        self.assertEqual(cross.ready(self.db),first)
        self.assertEqual(first[0]['state'],'pending')
    def test_freeform_answer_routes_when_voice_question_is_pending(self):
        with cross.connect(self.db) as db:db.execute('INSERT INTO task_question_actors VALUES (?,?,?)',('owner@example.com',1,1))
        self.event.text='One hour, Pacific time'
        self.assertEqual(self.hook()['action'],'skip')

if __name__=='__main__':unittest.main()
