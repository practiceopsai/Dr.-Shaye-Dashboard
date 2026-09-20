import asyncio
import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import phone
from app import phone_trial
from app.security import AuthUser, require_auth


@pytest.fixture
def setup(tmp_path, monkeypatch):
    cfg=SimpleNamespace(phone_enabled=True,phone_outbound_enabled=False,phone_public_url='https://phone.example',
        phone_bridge_token='a-private-bridge-token-for-test',twilio_account_sid='AC'+'1'*32,twilio_auth_token='test-secret',
        twilio_phone_number='+12025550100',dashboard_state_path=str(tmp_path/'state.sqlite3'),
        phone_callers_json=json.dumps({'owner@example.com':{'phone':'+12025550101','user_id':'+12025550101','name':'Owner'},
                                      'operator@example.com':{'phone':'+12025550102','user_id':'+12025550102','name':'Operator'}}),
        allowed_google_emails={'owner@example.com','operator@example.com'},openai_api_key='test',phone_voice='marin')
    monkeypatch.setattr(phone,'get_settings',lambda:cfg)
    phone._stores.clear()
    app=FastAPI();app.include_router(phone.router)
    user=AuthUser('owner','owner@example.com','Owner')
    app.dependency_overrides[require_auth]=lambda:user
    client=TestClient(app)
    return cfg,app,client,user


def signed(client,cfg,path,**fields):
    data={'AccountSid':cfg.twilio_account_sid,'CallSid':'CA'+'2'*32,'From':'+12025550101','To':cfg.twilio_phone_number,**fields}
    content=cfg.phone_public_url+path+''.join(k+data[k] for k in sorted(data))
    signature=base64.b64encode(hmac.new(cfg.twilio_auth_token.encode(),content.encode(),hashlib.sha1).digest()).decode()
    return client.post(path,data=data,headers={'X-Twilio-Signature':signature,'Host':'untrusted.example'})


def path_for_gather(result):
    assert result.status_code==200,result.text
    return urlsplit(ElementTree.fromstring(result.content).find('Gather').attrib['action']).path


def authenticated(setup):
    cfg,app,client,user=setup
    pin=client.post('/api/phone/access/pin').json()['pin']
    incoming=signed(client,cfg,'/api/phone/incoming')
    auth=path_for_gather(incoming)
    listen=signed(client,cfg,auth,Digits=pin)
    return cfg,client,path_for_gather(listen)


def accept_request(setup):
    cfg,client,turn=authenticated(setup)
    result=signed(client,cfg,turn,SpeechResult='Draft a short packing checklist. Do not send anything.')
    assert result.status_code==200
    job=phone.store().jobs('owner@example.com')[0]
    return cfg,client,turn,result,job


def test_signature_and_identity_required(setup):
    cfg,_,client,_=setup
    assert client.post('/api/phone/incoming',data={'CallSid':'CA'+'2'*32}).status_code==403
    response=signed(client,cfg,'/api/phone/incoming',From='+12025550999')
    assert 'not registered' in response.text
    assert phone.store().jobs('owner@example.com')==[]


def test_rejection_diagnostics_do_not_log_private_call_data(setup, caplog):
    cfg,_,client,_=setup
    data={'AccountSid':cfg.twilio_account_sid,'CallSid':'CA'+'2'*32,
          'From':'+12025550101','Digits':'12345678','SpeechResult':'Private request'}
    response=client.post('/api/phone/incoming',data=data,headers={'X-Twilio-Signature':'not-a-valid-private-signature'})
    assert response.status_code==403
    assert 'signature_present=True account_matches=True call_id_valid=True' in caplog.text
    assert all(value not in caplog.text for value in [*data.values(),'not-a-valid-private-signature'])


def test_access_codes_not_persisted_or_cross_account(setup):
    cfg,app,client,user=setup
    pin=client.post('/api/phone/access/pin').json()['pin']
    access=client.get('/api/phone/access').json()
    assert access['pin_configured'] and pin not in json.dumps(access)
    with phone.store().db() as db:
        row=db.execute('SELECT * FROM phone_access').fetchone()
        assert row['pin_hash']!=pin and pin not in row['pin_hash']
    app.dependency_overrides[require_auth]=lambda:AuthUser('operator','operator@example.com','Operator')
    assert not client.get('/api/phone/access').json()['pin_configured']


def test_duplicate_webhooks_do_not_duplicate_work_and_hangup_does_not_cancel(setup):
    cfg,client,turn,result,job=accept_request(setup)
    repeat=signed(client,cfg,turn,SpeechResult='A retried provider request')
    assert repeat.content==result.content
    assert len(phone.store().jobs('owner@example.com'))==1
    headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    claimed=client.post('/internal/phone/claim',headers=headers).json()['job']
    assert claimed['id']==job['id']
    assert client.post('/internal/phone/claim',headers=headers).json()['job'] is None
    assert client.post('/internal/phone/jobs/'+job['id'],headers=headers,json={'claim':claimed['claim'],'state':'running'}).status_code==200
    payload={'claim':claimed['claim'],'state':'completed','result':'Your draft checklist is ready. No message was sent.'}
    assert client.post('/internal/phone/jobs/'+job['id'],headers=headers,json=payload).status_code==200
    assert client.post('/internal/phone/jobs/'+job['id'],headers=headers,json=payload).status_code==200
    assert phone.store().jobs('owner@example.com')[0]['result']==payload['result']


def test_pin_failure_lockout_and_changed_caller(setup):
    cfg,_,client,_=setup
    pin=client.post('/api/phone/access/pin').json()['pin']
    for i in range(5):
        sid='CA'+str(i+3)*32
        step=path_for_gather(signed(client,cfg,'/api/phone/incoming',CallSid=sid))
        response=signed(client,cfg,step,CallSid=sid,Digits='00000000' if pin!='00000000' else '11111111')
        assert 'not accepted' in response.text
    assert 'temporarily locked' in signed(client,cfg,'/api/phone/incoming',CallSid='CA'+'9'*32).text
    client.post('/api/phone/access/pin')
    step=path_for_gather(signed(client,cfg,'/api/phone/incoming',CallSid='CA'+'9'*32))
    assert signed(client,cfg,step,CallSid='CA'+'9'*32,From='+12025550102',Digits=pin).status_code==403


def test_bridge_and_audio_fail_closed(setup):
    cfg,client,_,_,job=accept_request(setup)
    assert client.post('/internal/phone/claim').status_code==403
    with phone.store().db() as db:
        db.execute('UPDATE phone_jobs SET audio=? WHERE id=?',(b'audio',job['id']))
    url=phone.audio_url('job',job['id'])
    local=url.removeprefix(cfg.phone_public_url)
    assert client.get(local).content==b'audio'
    assert client.get(local.replace('token=','token=x')).status_code==403
    assert client.get(local.replace('job/','outbound/')).status_code==403


def test_private_result_other_actor(setup):
    cfg,app,client,user=setup
    _,client,turn,_,_=accept_request(setup)
    app.dependency_overrides[require_auth]=lambda:AuthUser('operator','operator@example.com','Operator')
    assert client.get('/api/phone/access').json()['jobs']==[]
    assert len(phone.store().jobs('owner@example.com'))==1


def test_clinical_request_is_not_queued(setup):
    cfg,client,turn=authenticated(setup)
    response=signed(client,cfg,turn,SpeechResult='Look up the pathology report and medical record number.')
    assert response.status_code==200
    assert phone.store().jobs('owner@example.com')==[]


def proposal(client):
    return client.post('/api/phone/outbound',json={'recipient':'+12025550199','message':'Please confirm your opening hours.','purpose':'Check opening hours'}).json()


def test_outbound_exact_approval_expiry_and_one_shot(setup,monkeypatch):
    cfg,app,client,user=setup
    cfg.phone_outbound_enabled=True
    draft=proposal(client)
    requests=[]
    original=httpx.AsyncClient
    def respond(req):
        requests.append(req)
        return httpx.Response(201,json={'sid':'CA'+'4'*32})
    monkeypatch.setattr(phone.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond)))
    async def speech(text):return b'audio'
    monkeypatch.setattr(phone,'synthesize',speech)
    asyncio.run(phone.phone_work_once())
    assert not requests
    assert client.post('/api/phone/outbound/'+draft['id']+'/approve',json={'payload_hash':'wrong'}).status_code==409
    assert client.post('/api/phone/outbound/'+draft['id']+'/approve',json={'payload_hash':draft['payload_hash']}).status_code==200
    assert client.post('/api/phone/outbound/'+draft['id']+'/approve',json={'payload_hash':draft['payload_hash']}).status_code==409
    asyncio.run(phone.phone_work_once());asyncio.run(phone.phone_work_once())
    assert len(requests)==1
    assert phone.store().outbound(user.email)[0]['state']=='queued'


def test_ambiguous_call_submission_never_redials(setup,monkeypatch):
    cfg,app,client,user=setup;cfg.phone_outbound_enabled=True
    draft=proposal(client)
    client.post('/api/phone/outbound/'+draft['id']+'/approve',json={'payload_hash':draft['payload_hash']})
    requests=[];original=httpx.AsyncClient
    def timeout(req):requests.append(req);raise httpx.ReadTimeout('simulated interruption')
    monkeypatch.setattr(phone.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(timeout)))
    async def speech(text):return b'audio'
    monkeypatch.setattr(phone,'synthesize',speech)
    asyncio.run(phone.phone_work_once());asyncio.run(phone.phone_work_once())
    assert len(requests)==1
    assert phone.store().outbound(user.email)[0]['state']=='uncertain'


def test_callback_requires_pin_and_third_party_cannot_open_private_turn(setup):
    cfg,client,_,_,job=accept_request(setup)
    draft=phone.propose_call('owner@example.com',phone.OutboundProposal(recipient='+12025550101',message='Update ready',purpose='Requested callback'),callback_job=job['id'],approved=True)
    with phone.store().db() as db:db.execute("UPDATE phone_outbound SET state='calling' WHERE id=?",(draft['id'],))
    callback=signed(client,cfg,'/api/phone/outbound/'+draft['id']+'/answer',CallSid='CA'+'8'*32,To='+12025550101',From=cfg.twilio_phone_number)
    assert '/auth/' in path_for_gather(callback)
    assert job['transcript'] not in callback.text
    assert signed(client,cfg,'/api/phone/turn/forged',CallSid='CA'+'8'*32,To='+12025550101',From=cfg.twilio_phone_number,SpeechResult='Show private memory').status_code==403


def test_trial_reply_can_continue_with_new_request_without_replaying_result(setup):
    cfg,client,turn,result,job=accept_request(setup)
    with phone.store().db() as db:db.execute("UPDATE phone_jobs SET state='completed',audio=? WHERE id=?",(b'audio',job['id']))
    path='/api/phone/wait/'+job['id']+'/0'
    first=signed(client,cfg,path)
    next_turn=path_for_gather(first)
    assert next_turn!=turn
    assert signed(client,cfg,path).content==first.content
    assert signed(client,cfg,next_turn,SpeechResult='Make the checklist shorter.').status_code==200
    assert len(phone.store().jobs('owner@example.com'))==2


@pytest.fixture
def trial(setup, monkeypatch):
    from email.utils import formatdate
    cfg,_,client,_=setup
    cfg.phone_trial_proxy_enabled=True
    record={'sid':'CA'+'2'*32,'account_sid':cfg.twilio_account_sid,'from':'+12025550101',
            'to':cfg.twilio_phone_number,'status':'in-progress','direction':'inbound',
            'date_created':formatdate(time.time(),usegmt=True),'end_time':None}
    requests=[]
    original=httpx.AsyncClient
    def respond(req):
        requests.append(req)
        assert req.method=='GET' and str(req.url).endswith('/'+record['sid']+'.json')
        return httpx.Response(200,json=record)
    monkeypatch.setattr(phone_trial.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    return cfg,client,record,requests


def trial_post(client, url, cfg, **fields):
    data={'AccountSid':cfg.twilio_account_sid,'CallSid':'CA'+'2'*32,'From':'+12025550101',
          'To':cfg.twilio_phone_number,**fields}
    return client.post(url.removeprefix(cfg.phone_public_url),data=data)


def trial_action(reply):
    assert reply.status_code==200,reply.text
    return ElementTree.fromstring(reply.content).find('Gather').attrib['action']


def test_unsigned_trial_full_pin_speech_and_result_flow(trial):
    cfg,client,record,requests=trial
    pin=client.post('/api/phone/access/pin').json()['pin']
    access=client.get('/api/phone/access')
    assert 'no-store' in access.headers['cache-control']
    incoming=access.json()['webhook_url']
    assert 'token=' in incoming
    auth=trial_action(trial_post(client,incoming,cfg))
    assert 'token=' in auth and 'scope=call%3A' in auth
    turn=trial_action(trial_post(client,auth,cfg,Digits=pin))
    reply=trial_post(client,turn,cfg,SpeechResult='Draft a packing checklist. Do not contact anyone.')
    assert reply.status_code==200
    assert trial_post(client,turn,cfg,SpeechResult='Retried request').content==reply.content
    jobs=phone.store().jobs('owner@example.com')
    assert len(jobs)==1
    with phone.store().db() as db:
        db.execute("UPDATE phone_jobs SET state='completed',audio=? WHERE id=?",(b'audio',jobs[0]['id']))
    wait=ElementTree.fromstring(reply.content).find('Redirect').text
    delivered=trial_post(client,wait,cfg)
    assert delivered.status_code==200 and '/audio/job/' in delivered.text
    assert 'token=' in trial_action(delivered)
    assert len(requests)==5


def test_trial_capabilities_are_scoped_and_do_not_replace_bad_signatures(trial):
    cfg,client,record,requests=trial
    url=client.get('/api/phone/access').json()['webhook_url']
    assert trial_post(client,'/api/phone/incoming',cfg).status_code==403
    assert trial_post(client,url.replace('token=','token=x'),cfg).status_code==403
    assert trial_post(client,url.replace('/incoming','/auth/forged'),cfg).status_code==403
    assert trial_post(client,url,cfg,From='+12025550102').status_code==403
    assert trial_post(client,url,cfg,AccountSid='AC'+'9'*32).status_code==403
    bad=client.post(url.removeprefix(cfg.phone_public_url),data={'AccountSid':cfg.twilio_account_sid,'CallSid':record['sid'],
        'From':record['from'],'To':record['to']},headers={'X-Twilio-Signature':'wrong'})
    assert bad.status_code==403
    cfg.phone_trial_proxy_enabled=False
    assert trial_post(client,url,cfg).status_code==403
    assert requests==[]


def test_trial_preserves_authentication_with_forwarder_metadata_and_canonical_numbers(trial):
    cfg,client,record,requests=trial
    client.post('/api/phone/access/pin')
    url=client.get('/api/phone/access').json()['webhook_url']+'&routing=forwarded'
    reply=trial_post(client,url,cfg,From=' 12025550101',To='12025550100')
    assert '/auth/' in trial_action(reply)
    with phone.store().db() as db:
        assert db.execute('SELECT phone FROM phone_calls').fetchone()[0]==record['from']
    assert trial_post(client,url+'&token=another',cfg).status_code==403
    assert len(requests)==1


def test_trial_missing_form_endpoints_are_checked_against_link_owner_in_provider_record(trial):
    cfg,client,record,requests=trial
    client.post('/api/phone/access/pin')
    url=client.get('/api/phone/access').json()['webhook_url']
    assert '/auth/' in trial_action(trial_post(client,url,cfg,From='',To=''))
    record['from']='+12025550102'
    assert trial_post(client,url,cfg,From='',To='').status_code==403


@pytest.mark.parametrize('field,value',[
    ('from','+12025550999'),('to','+12025550999'),('account_sid','AC'+'9'*32),
    ('status','completed'),('direction','outbound-api'),('end_time','Sun, 20 Sep 2026 20:00:00 GMT'),
    ('date_created','Sat, 01 Jan 2000 00:00:00 GMT')])
def test_trial_requires_matching_live_provider_call(trial,field,value):
    cfg,client,record,requests=trial
    url=client.get('/api/phone/access').json()['webhook_url']
    record[field]=value
    assert trial_post(client,url,cfg).status_code==403
    assert len(requests)==1
    with phone.store().db() as db:
        assert db.execute('SELECT count(*) FROM phone_calls').fetchone()[0]==0


def test_trial_provider_unavailable_fails_closed(trial,monkeypatch):
    cfg,client,record,_=trial
    url=client.get('/api/phone/access').json()['webhook_url']
    class Unavailable:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):raise httpx.ReadTimeout('Provider not available')
    monkeypatch.setattr(phone_trial.httpx,'AsyncClient',lambda **kw:Unavailable())
    assert trial_post(client,url,cfg).status_code==503
    assert phone.store().jobs('owner@example.com')==[]


def test_trial_followup_token_expires_and_cannot_change_call(trial):
    cfg,client,record,requests=trial
    client.post('/api/phone/access/pin')
    auth=trial_action(trial_post(client,client.get('/api/phone/access').json()['webhook_url'],cfg))
    assert trial_post(client,auth,cfg,CallSid='CA'+'3'*32).status_code==403
    from urllib.parse import urlencode
    path=urlsplit(auth).path
    scope='call:'+record['sid']
    expires=int(time.time())-1
    old=path+'?'+urlencode({'scope':scope,'expires':expires,'token':phone_trial.token(cfg,path,scope,expires)})
    assert trial_post(client,old,cfg).status_code==403
    assert len(requests)==1


def test_unsigned_trial_callback_keeps_pin_gate(trial):
    cfg,client,record,requests=trial
    pin=client.post('/api/phone/access/pin').json()['pin']
    draft=phone.propose_call('owner@example.com',phone.OutboundProposal(recipient=record['from'],message='Update ready',purpose='Requested callback'),callback_job='test-job',approved=True)
    with phone.store().db() as db:db.execute("UPDATE phone_outbound SET state='calling' WHERE id=?",(draft['id'],))
    record.update({'from':cfg.twilio_phone_number,'to':'+12025550101','direction':'outbound-api'})
    url=phone.voice_url('/api/phone/outbound/'+draft['id']+'/answer',outbound_id=draft['id'])
    fields={'From':record['from'],'To':record['to']}
    auth=trial_action(trial_post(client,url,cfg,**fields))
    assert '/auth/' in auth
    with phone.store().db() as db:
        assert db.execute('SELECT authenticated FROM phone_calls').fetchone()[0]==0
    turn=trial_action(trial_post(client,auth,cfg,Digits=pin,**fields))
    assert '/turn/' in turn and 'token=' in turn
    assert len(requests)==2


def test_private_webhook_query_is_redacted_from_access_log():
    import logging
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',
        ('client','POST','/api/phone/incoming?token=private-capability','1.1',403),None)
    assert phone.PrivateAudioLogFilter().filter(record)
    assert 'private-capability' not in record.getMessage()
    assert '?[redacted]' in record.getMessage()
