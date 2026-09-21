import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import test_operations as support
from phone_unit import presence


class PresenceTests(unittest.TestCase):
    setUp=support.OperationsTests.setUp

    def test_operator_gets_current_character_but_not_principal_rag(self):
        (self.home/'persona').mkdir()
        (self.home/'persona/CHARACTER.md').write_text('Warm and direct.\n## Evidence\nPrivate examples',encoding='utf-8')
        compiler=Mock()
        svc=SimpleNamespace(settings={'principal_user_ids':['principal'],'principal_platforms':['eli_phone']},
                            store=SimpleNamespace(path=lambda p:self.home/p),compiler=compiler)
        config={'model':{'default':'native-model'},'memory':{'eli_vault':{'allowed_user_ids':['principal']}}}
        result=presence.build_packet(config,self.identity,svc)
        self.assertEqual(result['scope'],'operator');self.assertEqual(result['native_model'],'native-model')
        self.assertIn('Warm and direct',result['personality']);self.assertNotIn('Private examples',json.dumps(result))
        compiler.compile.assert_not_called();compiler.index.search.assert_not_called()

    def test_principal_snapshot_uses_existing_compiler_and_shared_index(self):
        (self.home/'persona').mkdir();(self.home/'persona/CHARACTER.md').write_text('Character')
        compiler=Mock();compiler.compile.return_value={'text':'Learned current character and rank','stable_hash':'rev'}
        compiler.index.search.return_value=[(1,'memory/facts/team.md','Team','Alex is the coordinator.')]
        svc=SimpleNamespace(settings={'principal_user_ids':[self.identity['user_id']],'principal_platforms':['eli_phone']},
                            store=SimpleNamespace(path=lambda p:self.home/p),compiler=compiler)
        config={'memory':{'eli_vault':{'allowed_user_ids':[self.identity['user_id']]}}}
        with patch.object(presence,'persona_module',return_value=SimpleNamespace(safe_text=lambda text,limit:text)):
            result=presence.build_packet(config,self.identity,svc)
        self.assertEqual(result['scope'],'principal');self.assertEqual(result['personality_revision'],'rev')
        self.assertEqual(result['recalled_context'][0]['source'],'memory/facts/team.md')
        compiler.compile.assert_called_once();compiler.index.search.assert_called_once()

    def test_callback_requires_present_caller_not_inferred_intent(self):
        self.job['claim']='claim';self.job['transcript']='New caller speech: Please call me back.'
        with self.perf.db() as db: db.execute('UPDATE work SET payload=?',(json.dumps(self.job),))
        api=Mock(return_value={'status':'requested'})
        self.assertEqual(presence.request_callback({'quote':'Please call me back.'},self.settings,api=api,**self.kw)['status'],'requested')
        api.assert_called_once();api.reset_mock()
        for quote in ['Call me when done','Do not call me back.','Give Fabio a call','']:
            self.assertFalse(presence.request_callback({'quote':quote},self.settings,api=api,**self.kw)['success'])
        api.assert_not_called()


if __name__=='__main__': unittest.main()
