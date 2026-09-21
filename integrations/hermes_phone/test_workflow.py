import asyncio
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import zipfile

pkg=types.ModuleType('workflow_unit');pkg.__path__=[str(Path(__file__).parent)];sys.modules[pkg.__name__]=pkg
workflow=importlib.import_module('workflow_unit.workflow')
performance=importlib.import_module('workflow_unit.performance')
ledger=importlib.import_module('workflow_unit.ledger')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.perf=performance.Performance(Path(self.tmp.name)/'journal.sqlite3')
        self.spec={'goal':'Research a company and deliver findings','format':'markdown','channel':'email',
                   'recipient':'owner@example.com','title':'Company research','preauthorized':True,'approval_quote':'Research and email me the findings'}
        self.doc={'title':'Company research','summary':'A concise, sourced company overview.',
            'sections':[{'heading':'Activities','text':'The company builds software for scheduling.'},
                        {'heading':'Competitors','text':'Compare the product scope and published pricing before drawing conclusions.'}],
            'sources':[{'title':'Official company page','url':'https://example.org/company'}]}
    def job(self,stage,dependency=None):
        return {'id':stage,'root_id':stage,'actor':'owner@example.com',
            'plan':{'operation':'workflow_step','workflow':dict(self.spec),'stage':stage,'workflow_root':'root'},
            'dependency_results':[{'id':'previous','result':dependency}] if dependency is not None else []}
    def manifest(self,fmt='markdown'):
        self.spec['format']=fmt;job=self.job('create')
        made=workflow.build_artifact(self.perf,job,self.doc)
        verified=workflow.verify_artifact(made);workflow.save_manifest(self.perf,job,verified)
        return verified
    def test_f_actual_pptx_exists_and_is_verified(self):
        manifest=self.manifest('pptx')
        self.assertTrue(Path(manifest['path']).is_file())
        with zipfile.ZipFile(manifest['path']) as z:
            self.assertIn('ppt/presentation.xml',z.namelist())
            self.assertIn(b'Company research',z.read('ppt/slides/slide1.xml'))
        self.assertTrue(manifest['verified'])
    def test_tampered_artifact_cannot_deliver(self):
        manifest=self.manifest();Path(manifest['path']).write_text('changed')
        with self.assertRaises(ValueError):workflow.load_delivery(self.job('deliver',json.dumps(manifest)),self.perf)
    def test_sources_cannot_be_invented_during_creation(self):
        with self.assertRaises(ValueError):workflow.parse_document(json.dumps(self.doc),'No source URL')
    def test_g_confirmation_before_third_party_delivery(self):
        manifest=self.manifest();self.spec.update(recipient='guest@example.org',preauthorized=False)
        call=Mock();result=workflow.deliver(self.job('deliver',json.dumps(manifest)),{},self.perf,invoke=call)
        self.assertTrue(result['waiting_for_input']);call.assert_not_called()
    def test_actual_verified_send_receipt_once_and_no_false_completion(self):
        manifest=self.manifest();job=self.job('deliver',json.dumps(manifest));sent=[]
        def invoke(name,args):
            if name=='email_send':sent.append(args);return {'message_id':'msg-1','thread_id':'thread-1','task':{'task_id':'tracking-1'}}
            return {'success':True}
        svc=types.SimpleNamespace(mail=types.SimpleNamespace(get_message=lambda _: {
            'message_id':'msg-1','to':[self.spec['recipient']],'subject':manifest['title'],'text':manifest['body']}))
        first=workflow.deliver(job,{},self.perf,invoke=invoke,services=svc)
        again=workflow.deliver(job,{},self.perf,invoke=invoke,services=svc)
        self.assertTrue(first['success'] and first['source_verified']);self.assertEqual(first,again)
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['text'],manifest['body'])
        confirm=asyncio.run(workflow.execute(self.job('confirm',json.dumps(first)),{},self.perf,None))
        self.assertIn('verified provider receipt',confirm['result'])
    def test_unknown_send_result_is_never_retried_or_confirmed(self):
        manifest=self.manifest();job=self.job('deliver',json.dumps(manifest))
        call=Mock(side_effect=TimeoutError());svc=types.SimpleNamespace(mail=Mock())
        for _ in range(2):self.assertFalse(workflow.deliver(job,{},self.perf,invoke=call,services=svc)['success'])
        self.assertEqual(call.call_count,1)
        with self.assertRaises(ValueError):asyncio.run(workflow.execute(self.job('confirm',json.dumps({'success':False})),{},self.perf,None))
    def test_research_cannot_bypass_effect_fence_via_shell_or_send(self):
        for tool in ['terminal','execute_code','email_send','send_message','GOOGLECALENDAR_CREATE_EVENT']:
            self.assertTrue(workflow.guard(self.job('research'),tool,{},self.perf)['block'])
        self.assertIsNone(workflow.guard(self.job('research'),'web_search',{},self.perf))
    def test_l_restart_reads_existing_delivery_receipt(self):
        manifest=self.manifest();job=self.job('deliver',json.dumps(manifest))
        call=Mock(return_value={});svc=types.SimpleNamespace(mail=Mock())
        workflow.deliver(job,{},self.perf,invoke=call,services=svc)
        restored=performance.Performance(self.perf.path)
        workflow.deliver(job,{},restored,invoke=call,services=svc)
        self.assertEqual(call.call_count,1)
    def test_delivery_passes_full_native_guard_only_for_exact_verified_artifact(self):
        manifest=self.manifest();job=self.job('deliver',json.dumps(manifest));job['plan']['atomic_kind']='deliver'
        job['transcript']='Research the company and email me the findings'
        args={'to':[self.spec['recipient']],'subject':manifest['title'],'text':manifest['body'],'attachments':[]}
        with patch.object(performance,'current',return_value=(self.perf,job,job['transcript'])):
            self.assertIsNone(performance.before_tool({},tool_name='email_send',args=args))
            args['to']=['another@example.org']
            self.assertTrue(performance.before_tool({},tool_name='email_send',args=args)['block'])
    def test_create_step_json_is_not_rewritten_as_spoken_status(self):
        raw=json.dumps({**self.doc,'summary':'A product announcement said: I have already sent the invitation.'})
        job=self.job('create');job['transcript']='Research this product and email me a presentation'
        self.assertEqual(performance.verified_answer(self.perf,job,raw),raw)

if __name__=='__main__':unittest.main()
