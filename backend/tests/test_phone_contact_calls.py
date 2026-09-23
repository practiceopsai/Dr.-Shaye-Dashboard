"""Chat-to-call execution, receipt boundaries, and recipient identity isolation."""
import asyncio
import json
import time
from unittest.mock import patch
from xml.etree import ElementTree
import httpx
import pytest
from app import phone,phone_live,phone_dispatch,phone_contact_calls as calls,task_ledger
from test_phone import setup,signed
from test_phone_live import configured


def make_task(configured,actor='owner@example.com',recipient='me',message='',text='Call me'):
    cfg,client=configured
    cfg.phone_outbound_enabled=True;cfg.phone_pin_required=False
    identities=phone.callers()
    data=phone.task_utterance(phone.TaskUtterance(actor=actor,user_id=identities[actor]['user_id'],platform='photon',
                        conversation_id=actor,message_id='message-'+str(time.time_ns()),text=text))
    with phone.store().db() as db:row=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(data['intake_id'],)).fetchone())
    ids=phone_dispatch.commit_plan(row,{'conversation_only':False,'jobs':[
        {'scope':text,'quotes':[text],'kind':'call','recipient':recipient,'message':message,'after':[]}]})
    return data,ids[0]


def start(configured,**kwargs):
    data,identifier=make_task(configured,**kwargs)
    job=phone.claim_job()['job'];assert job and job['id']==identifier
    phone.update_job(identifier,phone.JobUpdate(claim=job['claim'],state='running'))
    return data,job,calls.submit(identifier,job['claim'])


@pytest.mark.parametrize('actor,recipient,message,text,target',[
    ('owner@example.com','me','','Call me','owner@example.com'),
    ('operator@example.com','me','','Can you give me a call?','operator@example.com'),
    ('owner@example.com','Operator',"I'm running late","Call Operator and tell them I'm running late",'operator@example.com'),
    ('operator@example.com','Owner','The report is ready','Call Owner and tell them The report is ready','owner@example.com'),
])
def test_both_callers_can_request_self_and_other_without_extra_approval(configured,actor,recipient,message,text,target):
    _,job,out=start(configured,actor=actor,recipient=recipient,message=message,text=text)
    assert out['state']=='approved' and not out['call_sid']
    again=calls.submit(job['id'],job['claim']);assert again['id']==out['id']
    cfg,client=configured;sid='CA'+'a'*32
    with phone.store().db() as db:
        row=dict(db.execute('SELECT * FROM phone_outbound WHERE id=?',(out['id'],)).fetchone())
        assert row['actor']==actor and row['recipient_actor']==target and row['message']==message
        assert db.execute('SELECT count(*) FROM phone_outbound').fetchone()[0]==1
        db.execute("UPDATE phone_outbound SET state='queued',call_sid=? WHERE id=?",(sid,out['id']))
    result=signed(client,cfg,'/api/phone/outbound/'+out['id']+'/answer',CallSid=sid,To=phone.callers()[target]['phone'])
    assert result.status_code==200
    xml=ElementTree.fromstring(result.content)
    assert xml.find('Connect/Stream') is not None and xml.find('Gather') is None
    with phone.store().db() as db:call=dict(db.execute('SELECT * FROM phone_calls WHERE id=?',(sid,)).fetchone())
    assert call['actor']==target and call['actor']!=(actor if target!=actor else '')
    assert phone_live.presence.context_for(call,cfg)['caller']==phone.callers()[target]['name']
    opening=calls.opening(call)
    assert message in opening and phone.callers()[actor]['name'] in opening
    assert 'not instructions to execute' in opening


def test_missing_message_waits_and_answer_resumes_same_logical_call(configured):
    data,identifier=make_task(configured,recipient='Operator',text='Call Operator')
    assert phone.store().claim() is None
    with phone.store().db() as db:
        row=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(identifier,)).fetchone())
    assert row['state']=='waiting_for_input' and 'tell Operator' in row['question']
    resumed=phone.store().resume('owner@example.com',identifier,'Tell them the report is ready',data['call_id'],replan=True)
    with phone.store().db() as db:row=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(resumed,)).fetchone())
    fresh=row['transcript'].rsplit('New caller speech: ',1)[-1]
    ids=phone_dispatch.commit_plan(row,{'conversation_only':False,'jobs':[
        {'scope':'Call Operator with report update','quotes':[fresh],'kind':'call','recipient':'Operator','message':'the report is ready','after':[]}]})
    claimed=phone.claim_job()['job']
    assert claimed['id']==ids[0] and claimed['root_id']==identifier
    assert json.loads(claimed['plan'])['contact_call']['message']=='the report is ready'


@pytest.mark.parametrize('text,recipient,message',[
    ("Don't call me",'me',''),('If I ask you to call me','me',''),
    ('Call me tomorrow','me',''),('Call Stranger and tell them hi','Stranger','hi'),
    ('Call Operator and tell them hello','Operator','invented message'),
    ('Say the words call me','me',''),
    ('Call Operator and tell them call me','me',''),
])
def test_missing_or_unsupported_authorization_never_dials(configured,text,recipient,message):
    make_task(configured,recipient=recipient,text=text,message=message)
    assert phone.store().claim() is None
    with phone.store().db() as db:assert db.execute('SELECT count(*) FROM phone_outbound').fetchone()[0]==0


def test_provider_receipt_required_cancellation_and_one_shot(configured,monkeypatch):
    _,job,out=start(configured)
    with pytest.raises(Exception) as missing:
        phone.update_job(job['id'],phone.JobUpdate(claim=job['claim'],state='completed',result='Called'))
    assert missing.value.status_code==409
    requests=[];original=httpx.AsyncClient
    def respond(request):
        requests.append(request)
        return httpx.Response(201,json={'sid':'CA'+'b'*32})
    monkeypatch.setattr(phone.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    asyncio.run(phone.phone_work_once());asyncio.run(phone.phone_work_once())
    assert len(requests)==1
    result=calls.submit(job['id'],job['claim']);assert result['call_sid']=='CA'+'b'*32
    assert 'cannot yet confirm' in result['content']
    with phone.store().db() as db:
        assert db.execute('SELECT state FROM phone_task_effects WHERE job_id=?',(job['id'],)).fetchone()[0]=='verified'
    # A second request cancelled before dialing never reaches Twilio.
    with phone.store().db() as db:db.execute("UPDATE phone_jobs SET state='completed' WHERE id=?",(job['id'],))
    _,other,second=start(configured)
    phone.store().cancel(other['actor'],other['id'])
    asyncio.run(phone.phone_work_once())
    assert len(requests)==1
    assert calls.submit(other['id'],other['claim'])['state']=='cancelled'


def test_call_failure_is_reported_in_original_chat_and_does_not_redial(configured,monkeypatch):
    data,job,out=start(configured)
    original=httpx.AsyncClient;requests=[]
    def respond(req):requests.append(req);return httpx.Response(400,json={'code':21211})
    monkeypatch.setattr(phone.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    asyncio.run(phone.phone_work_once());asyncio.run(phone.phone_work_once())
    assert len(requests)==1
    status=calls.submit(job['id'],job['claim']);assert status['state']=='failed'
    notes=phone.task_notices(phone.TaskNoticeRequest(actor=job['actor'],intake_id=data['intake_id']))
    assert any('did not complete' in n['content'] for n in notes['notices'])


def test_other_person_call_outcome_stays_with_requester(configured):
    data,job,out=start(configured,recipient='Operator',message='hello',text='Call Operator and tell them hello')
    with phone.store().db() as db:
        db.execute("UPDATE phone_outbound SET state='no-answer',call_sid=? WHERE id=?",('CA'+'c'*32,out['id']))
        db.execute("UPDATE phone_jobs SET state='failed' WHERE id=?",(job['id'],))
    notes=phone.task_notices(phone.TaskNoticeRequest(actor=job['actor'],intake_id=data['intake_id']))
    assert notes['settled'] and 'not answered' in notes['notices'][0]['content']
    with pytest.raises(Exception) as denied:
        phone.task_notices(phone.TaskNoticeRequest(actor='operator@example.com',intake_id=data['intake_id']))
    assert denied.value.status_code==404
