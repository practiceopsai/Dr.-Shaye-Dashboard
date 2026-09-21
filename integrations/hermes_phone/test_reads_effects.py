import importlib.util,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock

root=Path(__file__).parent
pkg=types.ModuleType('phone_read_tests');pkg.__path__=[str(root)];sys.modules[pkg.__name__]=pkg
from phone_read_tests import performance,reads,effects


class ReadEffectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.perf=performance.Performance(Path(self.tmp.name)/'test.db')
        self.identity={'name':'Test','user_id':'owner','phone':'test'}
        self.settings={'identities':{'owner@example.com':self.identity}}
        self.job={'id':'one','actor':'owner@example.com','identity':self.identity,'plan':json.dumps({'kind':'latest_email','mailbox':'eli'})}
        self.config={'memory':{'eli_vault':{'allowed_user_ids':['owner']}},
            'plugins':{'entries':{'eli_persona':{'settings':{'principal_user_ids':['owner']}}}}}

    def test_direct_eli_read_has_freshness_and_reuses_short_snapshot(self):
        fn=Mock(return_value={'success':True,'message':{'message_id':'1','subject':'Hello'}})
        result=reads.run(self.job,self.settings,self.perf,config=self.config,eli_read=fn,now=100)
        self.assertEqual(result['snapshot_as_of'],100)
        self.assertFalse(result['cached'])
        self.assertTrue(reads.run(self.job,self.settings,self.perf,config=self.config,eli_read=fn,now=110)['cached'])
        self.assertEqual(fn.call_count,1)
        reads.run(self.job,self.settings,self.perf,config=self.config,eli_read=fn,now=116)
        self.assertEqual(fn.call_count,2)

    def test_operator_personal_email_never_substitutes_principal_account(self):
        self.job['plan']=json.dumps({'kind':'latest_email','mailbox':'personal'})
        fn=Mock()
        result=reads.run(self.job,self.settings,self.perf,config={},invoke=fn)
        self.assertIn('clarification',result);fn.assert_not_called()

    def test_gmail_read_metadata_only_explicit_account(self):
        self.job['plan']=json.dumps({'kind':'latest_email','mailbox':'personal'})
        fn=Mock(return_value={'messages':[{'messageId':'1','subject':'Hello','body':'should not escape'}]})
        result=reads.run(self.job,self.settings,self.perf,config=self.config,invoke=fn)
        self.assertNotIn('body',result['messages'][0])
        slug,args,account=fn.call_args.args
        self.assertEqual(account,'gmail_actual-glazy');self.assertFalse(args['include_payload']);self.assertEqual(args['max_results'],1)

    def test_missing_calendar_timezone_never_guesses(self):
        self.job['plan']=json.dumps({'kind':'calendar','window':'tomorrow'})
        with self.assertRaises(ValueError):reads.run(self.job,self.settings,self.perf,config=self.config,invoke=Mock(return_value={}))

    def test_calendar_is_bounded_and_reports_partial_coverage(self):
        self.job['plan']=json.dumps({'kind':'calendar','window':'tomorrow'})
        fn=Mock(side_effect=[{'timeZone':'America/Los_Angeles'}, {'event_data':{'event_data':[{'id':'1','summary':'Hello'}]},'nextPageToken':'more'}])
        result=reads.run(self.job,self.settings,self.perf,config=self.config,invoke=fn)
        self.assertTrue(result['truncated']);self.assertEqual(result['events'][0]['id'],'1')
        self.assertEqual(fn.call_args.args[1]['max_results'],25)

    def test_unknown_provider_response_is_not_empty_success(self):
        self.job['plan']=json.dumps({'kind':'latest_email','mailbox':'personal'})
        with self.assertRaises(ValueError):reads.run(self.job,self.settings,self.perf,config=self.config,invoke=Mock(return_value={}))

    def test_native_mcp_string_envelope_and_errors(self):
        data={'result':json.dumps({'data':{'results':[{'response':{'successful':True,'data':{'messages':[]}}}]},'successful':True})}
        self.assertEqual(reads.unwrap(data),{'messages':[]})
        with self.assertRaises(ValueError):reads.unwrap({'result':json.dumps({'successful':False,'error':'unavailable'})})

    def test_sensitive_read_does_not_enter_snapshot(self):
        result=reads.run(self.job,self.settings,self.perf,config=self.config,eli_read=Mock(return_value={'success':True,'text':'Patient Jane Doe MRN: 1234'}))
        self.assertFalse(result['success'])
        with self.perf.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM read_snapshots').fetchone()[0],0)

    def test_crash_after_provider_acceptance_never_replays_effect(self):
        args={'to':['test@example.com'],'subject':'Hello','text':'hello'}
        self.assertIsNone(effects.begin(self.perf,self.job,'email_send',args))
        # The provider performed the write; crash before local result. Reopen.
        reopened=performance.Performance(self.perf.path)
        self.assertTrue(effects.begin(reopened,self.job,'email_send',args)['block'])
        effects.finish(reopened,self.job,'email_send',args,{'success':True,'message_id':'provider-1'},'ok')
        self.assertEqual(effects.review(reopened,self.job)[0]['state'],'accepted')
        self.assertTrue(effects.begin(reopened,self.job,'email_send',args)['block'])
        self.job['id']='continuation';self.job['root_id']='one'
        self.assertTrue(effects.begin(reopened,self.job,'email_send',args)['block'])

    def test_partial_batch_keeps_separate_success_and_uncertainty(self):
        effects.begin(self.perf,self.job,'email_send',{'to':'a'})
        effects.finish(self.perf,self.job,'email_send',{'to':'a'},{'message_id':'id','success':True,'source_verified':True},'ok')
        effects.begin(self.perf,self.job,'calendar_create',{'title':'b'})
        effects.finish(self.perf,self.job,'calendar_create',{'title':'b'},{'error':'timeout'},'error')
        self.assertEqual({r['state'] for r in effects.review(self.perf,self.job)},{'verified','uncertain'})

    def test_multi_tool_child_is_not_replayed_in_changed_batch(self):
        a={'tool_slug':'GMAIL_SEND_EMAIL','arguments':{'to':'a','body':'Hello'},'account':'a'}
        b={'tool_slug':'GOOGLECALENDAR_CREATE_EVENT','arguments':{'summary':'B'},'account':'b'}
        name='mcp_eli_COMPOSIO_MULTI_EXECUTE_TOOL'
        self.assertIsNone(effects.begin(self.perf,self.job,name,{'tools':[a,b]}))
        result={'result':json.dumps({'data':{'results':[
            {'index':0,'response':{'successful':True,'data':{'id':'sent-one'}}},
            {'index':1,'response':{'successful':False,'error':'timeout'}}]}})}
        effects.finish(self.perf,self.job,name,{'tools':[a,b]},result,'ok')
        self.assertEqual({r['state'] for r in effects.review(self.perf,self.job)},{'accepted','uncertain'})
        self.assertTrue(effects.begin(self.perf,self.job,name,{'tools':[a]})['block'])
        self.assertTrue(effects.begin(self.perf,self.job,name,{'tools':[b,a]})['block'])
        effects.verified_provider(self.perf,self.job,'sent-one')
        self.assertEqual({r['state'] for r in effects.review(self.perf,self.job)},{'verified','uncertain'})
        answer=performance.verified_answer(self.perf,self.job,'Done, I created everything.')
        self.assertIn('verification is still pending',answer)

    def test_repeated_operation_within_initial_batch_is_blocked(self):
        a={'tool_slug':'GMAIL_SEND_EMAIL','arguments':{'to':'a'},'account':'a'}
        self.assertTrue(effects.begin(self.perf,self.job,'COMPOSIO_MULTI_EXECUTE_TOOL',{'tools':[a,a]})['block'])
        self.assertEqual(effects.review(self.perf,self.job),[])

    def test_changed_agent_tracking_note_cannot_repeat_same_email(self):
        args={'to':['a@example.com'],'subject':'Hello','text':'Hello','mandate':'one'}
        effects.begin(self.perf,self.job,'email_send',args)
        self.assertTrue(effects.begin(self.perf,self.job,'email_send',{**args,'mandate':'two'})['block'])

    def test_provider_acceptance_reconciles_by_read_after_restart(self):
        args={'to':['test@example.com'],'subject':'Hello'}
        effects.begin(self.perf,self.job,'email_send',args)
        effects.finish(self.perf,self.job,'email_send',args,{'message_id':'id-one','thread_id':'thread'},'ok')
        reopened=performance.Performance(self.perf.path)
        read=Mock(return_value={'message_id':'id-one','thread_id':'thread'})
        effects.reconcile(reopened,self.job,read)
        self.assertEqual(read.call_count,1)
        self.assertEqual(effects.review(reopened,self.job)[0]['state'],'verified')
        self.assertTrue(effects.begin(reopened,self.job,'email_send',args)['block'])

    def test_calendar_readback_must_match_accepted_resource(self):
        args={'tools':[{'tool_slug':'GOOGLECALENDAR_CREATE_EVENT','arguments':{'calendar_id':'primary'},'account':'calendar'}]}
        tool='COMPOSIO_MULTI_EXECUTE_TOOL';event={'id':'new','summary':'Meeting','start':{'dateTime':'tomorrow'},'end':{'dateTime':'later'}}
        effects.begin(self.perf,self.job,tool,args)
        effects.finish(self.perf,self.job,tool,args,{'results':[{'response':{'data':event}}]},'ok')
        effects.reconcile(self.perf,self.job,Mock(return_value={**event,'id':'other'}))
        self.assertEqual(effects.review(self.perf,self.job)[0]['state'],'accepted')


if __name__=='__main__':unittest.main()
