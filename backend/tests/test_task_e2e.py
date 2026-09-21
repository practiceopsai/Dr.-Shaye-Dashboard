"""Canonical queue through native artifact/effect guards into a fake provider.

Only the provider and model content are fixtures. Real task claims, revisions,
dependency results, generated files, effect reservations and readback run here.
"""
import asyncio
import importlib
import json
from pathlib import Path
import shutil
import sys
import types
import pytest
from app import phone,phone_dispatch as dispatch,task_ledger as ledger
from test_phone import setup
from test_phone_live import configured
from test_phone_two_layer import intake


@pytest.mark.parametrize('fmt,third_party',[('pptx',False),('markdown',True)])
def test_workflow_queue_artifact_approval_receipt_and_restart(configured,tmp_path,monkeypatch,fmt,third_party):
    plugin=Path(__file__).resolve().parents[2]/'integrations/hermes_phone'
    if fmt=='pptx' and (not shutil.which('node') or not (plugin/'node_modules/pptxgenjs').exists()):
        pytest.skip('Presentation writer is exercised by native CI and installed integration checks')
    package=types.ModuleType('native_e2e');package.__path__=[str(plugin)]
    monkeypatch.setitem(sys.modules,package.__name__,package)
    modules=[importlib.import_module('native_e2e.'+n) for n in ['workflow','performance','operations']]
    runner,performance,operations=modules
    def control(job):
        with phone.store().db() as db:return ledger.control(db,job['id'])
    package.api_control=control
    package.api_request=lambda path,payload:phone.task_effect(path.split('/')[-2],phone.TaskEffect(**payload))
    perf=performance.Performance(tmp_path/'native.sqlite3');active={};messages={};attempts=[]
    monkeypatch.setattr(performance,'current',lambda _: (perf,active['job'],active['job']['transcript']))
    def invoke(name,args):
        if name!='email_send':return {'success':True}
        blocked=performance.before_tool({},tool_name=name,args=args)
        assert not blocked,blocked
        identifier='fixture-'+str(len(messages)+1);attempts.append(args)
        messages[identifier]={'message_id':identifier,'to':args['to'],'subject':args['subject'],'text':args['text'],
            'attachments':[{'filename':Path(p).name,'attachment_id':p} for p in args['attachments']]}
        result={'success':True,'message_id':identifier,'thread_id':identifier,'task':{'task_id':identifier}}
        performance.after_tool({},tool_name=name,args=args,result=result)
        return result
    svc=types.SimpleNamespace(mail=types.SimpleNamespace(get_message=lambda identifier:messages[identifier],
        download_attachment=lambda message,attachment,*_:attachment))
    monkeypatch.setattr(operations,'native_call',invoke);monkeypatch.setattr(operations,'mail_services',lambda:svc)
    text='Research the subject and email '+('Operator' if third_party else 'me')+' the '+('presentation' if fmt=='pptx' else 'findings')
    call,row=intake(configured,text)
    root=dispatch.commit_plan(row,{'conversation_only':False,'jobs':[{'scope':text,'quotes':[text],'kind':'workflow',
        'recipient':'Operator' if third_party else 'me','after':[],'details':{'deliverable':fmt,'channel':'email'}}]})[0]
    document={'title':'Fixture findings','summary':'An overview supported by the cited source.',
        'sections':[{'heading':'Products','text':'The source describes scheduling software.'}],
        'sources':[{'title':'Source','url':'https://example.org/company'}]}
    states=[];waiting=0
    for _ in range(8):
        job=phone.claim_job()['job']
        if not job:break
        active['job']=job;plan=json.loads(job['plan']);stage=plan['stage']
        phone.update_job(job['id'],phone.JobUpdate(claim=job['claim'],state='running'))
        async def model():return 'The company sells scheduling software. https://example.org/company' if stage=='research' else json.dumps(document)
        result=asyncio.run(runner.execute(job,{},perf,model))
        state='waiting_for_input' if result.get('waiting_for_input') else 'completed'
        assert result.get('success') or state=='waiting_for_input',result
        with perf.db() as db:events=[dict(r) for r in db.execute("SELECT * FROM execution_events WHERE job_id=? AND kind='action'",(job['id'],))]
        for i,event in enumerate(events):phone.job_progress(job['id'],phone.JobProgress(claim=job['claim'],events=[
            phone.ProgressEvent(event_id='receipt-'+str(i),kind='action',tool=event['tool'],status=event['status'],content=event['content'])]))
        phone.update_job(job['id'],phone.JobUpdate(claim=job['claim'],state=state,result=result.get('result',''),question=result.get('question','')))
        states.append((stage,state))
        if state=='waiting_for_input':
            assert not messages;waiting+=1
            from app.task_workflow import approve_delivery
            with phone.store().db() as db:approve_delivery(db,call['actor'],job['id'],'Yes','fixture-approval')
        dispatch.settle_dependencies()
    assert len(messages)==len(attempts)==1
    assert waiting==int(third_party)
    assert attempts[0]['to']==['operator@example.com' if third_party else 'owner@example.com']
    assert bool(attempts[0]['attachments'])==(fmt=='pptx')
    with phone.store().db() as db:
        task=ledger.get(db,call['actor'],root)
        assert task['state']=='completed' and task['completion_allowed'],(task,states)
        assert task['irreversible_boundary_passed'] and not task['effect_in_flight']
    phone._stores.clear()  # Restart cannot create another executable effect.
    assert phone.claim_job()['job'] is None
    assert len(attempts)==1
