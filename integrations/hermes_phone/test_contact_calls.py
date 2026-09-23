import importlib,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch
pkg=types.ModuleType('contact_call_unit');pkg.__path__=[str(Path(__file__).parent)];sys.modules[pkg.__name__]=pkg
calls=importlib.import_module('contact_call_unit.contact_calls')


class ContactCallTests(unittest.TestCase):
    def test_receipt_only_after_provider_accepts_and_same_job_reused(self):
        api=Mock(side_effect=[{'state':'approved','id':'one'},
            {'state':'queued','call_sid':'CA123','content':'Call accepted; not confirmed heard.'}])
        perf=Mock();job={'id':'job1','claim':'claim'}
        with patch.object(calls.time,'sleep'):
            result=calls.run(job,{},perf,api=api)
        self.assertTrue(result['success']);self.assertEqual(result['message_id'],'CA123')
        self.assertEqual(api.call_args_list[0],api.call_args_list[1])
        self.assertEqual(sum(c.args[1]=='action' for c in perf.record.call_args_list),1)
    def test_failed_or_unknown_call_is_not_claimed_successful(self):
        for outcome in [{'terminal':True,'state':'no-answer','content':'Not answered'},TimeoutError()]:
            perf=Mock();api=Mock(side_effect=outcome if isinstance(outcome,Exception) else [outcome])
            result=calls.run({'id':'job1','claim':'claim'},{},perf,api=api)
            self.assertFalse(result['success']);self.assertEqual(api.call_count,1)
            self.assertFalse(any(c.args[1]=='action' for c in perf.record.call_args_list))

if __name__=='__main__':unittest.main()
