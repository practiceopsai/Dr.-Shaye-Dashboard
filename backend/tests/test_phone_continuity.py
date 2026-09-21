import asyncio
import base64
import json
import time
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from app import phone, phone_live as live
from app.phone_followups import prepare_callback, close_stale_streams
from test_phone import setup, signed
from test_phone_live import configured, authenticated_stream, CALL, STREAM, FakeModel, fragment


def queued(configured, name='one'):
    cfg,client=configured
    with phone.store().db() as db:
        row=db.execute('SELECT * FROM phone_calls WHERE id=?',(CALL,)).fetchone()
    call=dict(row) if row else live.activate_stream(authenticated_stream(configured),cfg)
    identifier=live.enqueue(call,name,'New caller speech: Email Fabio.','Email Fabio.')
    return call,identifier


def finish(configured, identifier, state='completed', question=''):
    cfg,client=configured
    headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    job=client.post('/internal/phone/claim',headers=headers).json()['job']
    assert job and job['id']==identifier
    result=client.post('/internal/phone/jobs/'+identifier,headers=headers,
        json={'claim':job['claim'],'state':state,'result':question or 'The request is complete.','question':question})
    assert result.status_code==200,result.text
    return job


def test_registered_call_starts_without_pin_but_unregistered_stays_out(configured):
    cfg,client=configured;cfg.phone_pin_required=False
    incoming=signed(client,cfg,'/api/phone/incoming')
    tree=ElementTree.fromstring(incoming.content)
    assert tree.find('Connect/Stream') is not None and tree.find('Gather') is None
    assert signed(client,cfg,'/api/phone/incoming').content==incoming.content
    assert client.post('/api/phone/access/pin').status_code==409
    assert client.get('/api/phone/access').json()['pin_required'] is False
    assert 'not registered' in signed(client,cfg,'/api/phone/incoming',From='+12025550999',CallSid='CA'+'9'*32).text
    assert client.post('/api/phone/incoming',data={'CallSid':CALL}).status_code==403


def test_question_survives_hangup_does_not_block_other_work_and_resumes_once(configured):
    call,identifier=queued(configured)
    finish(configured,identifier,'waiting_for_input','What should the email say?')
    _,other=queued(configured,'two')
    finish(configured,other)
    with phone.store().db() as db:
        db.execute("UPDATE phone_live_streams SET state='closed' WHERE call_id=?",(CALL,))
        db.execute('UPDATE phone_calls SET ended=? WHERE id=?',(time.time(),CALL))
    cfg,client=configured
    first=client.post('/api/phone/jobs/'+identifier+'/answer',json={'answer':'Say hello.'})
    second=client.post('/api/phone/jobs/'+identifier+'/answer',json={'answer':'Say hello.'})
    assert first.status_code==200 and second.json()==first.json()
    jobs=phone.store().jobs(call['actor'])
    resumed=next(j for j in jobs if j['id']==first.json()['job_id'])
    assert resumed['parent_id']==identifier and resumed['state']=='queued'
    assert 'Email Fabio.\nSay hello.' in resumed['transcript']
    assert len(jobs)==3 and phone.store().questions(call['actor'])==[]


def test_answer_cannot_cross_actor_and_patient_data_rejected(configured):
    _,identifier=queued(configured)
    finish(configured,identifier,'waiting_for_input','What should I say?')
    cfg,client=configured
    assert client.post('/api/phone/jobs/'+identifier+'/answer',json={'answer':'Patient Jane Doe MRN: 123'}).status_code==400
    assert client.post('/api/phone/jobs/not-yours/answer',json={'answer':'hello'}).status_code==404
    with pytest.raises(ValueError,match='Unknown'):
        phone.store().resume('operator@example.com',identifier,'hello',CALL)


def test_bridge_answer_requires_current_caller_words_and_exact_claim(configured):
    _,identifier=queued(configured)
    finish(configured,identifier,'waiting_for_input','What should I say?')
    _,answer_id=queued(configured,'answer')
    with phone.store().db() as db:
        db.execute('UPDATE phone_jobs SET transcript=? WHERE id=?',('New caller speech: Say hello.',answer_id))
    cfg,client=configured;headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    answering=client.post('/internal/phone/claim',headers=headers).json()['job']
    assert answering['open_questions'][0]['id']==identifier
    assert client.post('/internal/phone/jobs/'+answer_id,headers=headers,json={'claim':answering['claim'],'state':'running'}).status_code==200
    path='/internal/phone/jobs/'+answer_id+'/answer'
    data={'claim':answering['claim'],'request_id':identifier,'answer':'Invented content'}
    assert client.post(path,headers=headers,json=data).status_code==400
    data['answer']='Say hello.';data['claim']='x'*24
    assert client.post(path,headers=headers,json=data).status_code==403
    data['claim']=answering['claim']
    response=client.post(path,headers=headers,json=data)
    assert response.status_code==200
    assert client.post(path,headers=headers,json=data).json()==response.json()


def test_more_than_three_requests_are_retained(configured):
    call,_=queued(configured)
    for i in range(8):
        live.enqueue(call,'task-'+str(i),'Draft item '+str(i),'Draft item '+str(i))
    assert len(phone.store().jobs(call['actor']))==9


def test_result_and_question_are_held_while_caller_speaks(configured):
    call,identifier=queued(configured)
    finish(configured,identifier,'waiting_for_input','What should I say?')
    model=FakeModel();voice=live.LiveCall(None,model,configured[0],call,STREAM)
    voice.conversation.append(fragment('u1','Email Fabio.'))
    voice.conversation.last_input=0
    voice.last_speech=time.monotonic()
    asyncio.run(voice.deliver_ready_notice())
    assert model.sent==[]
    voice.last_speech=0
    asyncio.run(voice.deliver_ready_notice())
    spoken=[e for e in model.sent if e['type']=='session.commentary.append']
    assert len(spoken)==1 and spoken[0]['content'].endswith('What should I say?')
    assert 'Email Fabio.' in spoken[0]['content']
    assert phone.store().notices(call['actor'])[0]['heard_at'] is None


class Socket:
    def __init__(self, events=()): self.events=list(events);self.sent=[]
    async def receive_json(self): return self.events.pop(0)
    async def send_json(self,event): self.sent.append(event)


def test_barge_in_clears_playback_without_marking_interrupted_result_heard(configured):
    call,identifier=queued(configured);finish(configured,identifier)
    ws=Socket([{'event':'media','streamSid':STREAM,'media':{'track':'inbound','payload':base64.b64encode(b'\x00'*160).decode()}},
               {'event':'mark','streamSid':STREAM,'mark':{'name':'old-mark'}},{'event':'stop','streamSid':STREAM}])
    voice=live.LiveCall(ws,FakeModel(),configured[0],call,STREAM)
    voice.active_notice=phone.store().notices(call['actor'])[0];voice.notice_mark='old-mark'
    asyncio.run(voice.receive_phone())
    assert ws.sent[0]['event']=='clear'
    assert phone.store().notices(call['actor'])[0]['heard_at'] is None
    assert any(u['status']=='interrupted' for u in phone.store().updates(identifier))


def test_only_playback_mark_acknowledges_delivery(configured):
    call,identifier=queued(configured);finish(configured,identifier)
    ws=Socket([{'event':'mark','streamSid':STREAM,'mark':{'name':'right-mark'}},{'event':'stop','streamSid':STREAM}])
    voice=live.LiveCall(ws,FakeModel(),configured[0],call,STREAM)
    voice.active_notice=phone.store().notices(call['actor'])[0];voice.notice_mark='right-mark'
    asyncio.run(voice.receive_phone())
    assert phone.store().notices(call['actor'])==[]


def test_hangup_captures_last_unsettled_turn_once(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    voice=live.LiveCall(None,FakeModel(),cfg,call,STREAM)
    voice.conversation.append(fragment('last','Email Fabio.',end=599900))
    voice.save_final_request();voice.save_final_request()
    jobs=phone.store().jobs(call['actor'])
    assert len(jobs)==1 and jobs[0]['state']=='queued'
    with phone.store().db() as db:
        assert 'if the speech is incomplete' in db.execute('SELECT transcript FROM phone_jobs').fetchone()[0]


def test_goodbye_never_creates_a_callback_loop(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    voice=live.LiveCall(None,FakeModel(),cfg,call,STREAM)
    voice.conversation.append(fragment('bye','Okay, thanks Eli. Goodbye.'))
    voice.save_final_request()
    assert phone.store().jobs(call['actor'])==[]
    assert not live.social_only('Thanks, and remember to prepare the agenda.')


def make_followup_ready(configured, question=False):
    cfg,_=configured;cfg.phone_outbound_enabled=True
    call,identifier=queued(configured)
    cfg.phone_pin_required=False
    finish(configured,identifier,'waiting_for_input' if question else 'completed','What should I say?' if question else '')
    with phone.store().db() as db:
        db.execute('UPDATE phone_calls SET ended=? WHERE id=?',(time.time()-40,CALL))
        db.execute("UPDATE phone_live_streams SET state='closed',closed=? WHERE call_id=?",(time.time()-40,CALL))
        db.execute('UPDATE phone_notices SET created=?',(time.time()-40,))
        db.execute('UPDATE phone_jobs SET updated=?,callback_requested=1 WHERE id=?',(time.time()-40,identifier))
    return call,identifier


def test_followup_is_durable_single_attempt_and_callback_has_no_pin(configured):
    call,identifier=make_followup_ready(configured)
    prepare_callback();prepare_callback()
    outgoing=phone.store().outbound(call['actor'])
    assert len(outgoing)==1 and outgoing[0]['recipient']==call['phone']
    cfg,client=configured
    sid='CA'+'7'*32
    with phone.store().db() as db:
        db.execute("UPDATE phone_outbound SET state='queued',call_sid=?",(sid,))
    response=signed(client,cfg,'/api/phone/outbound/'+outgoing[0]['id']+'/answer',CallSid=sid,To=call['phone'],From=cfg.twilio_phone_number)
    assert response.status_code==200
    tree=ElementTree.fromstring(response.content)
    assert tree.find('Gather') is None and tree.find('Connect/Stream') is not None


def test_question_heard_but_unanswered_still_gets_followup(configured):
    call,identifier=make_followup_ready(configured,question=True)
    phone.store().heard(identifier,call['actor'],CALL)
    assert phone.store().notices(call['actor'],CALL)==[]
    assert phone.store().notices(call['actor'],'next-call')
    prepare_callback()
    assert len(phone.store().outbound(call['actor']))==1


def test_answering_in_app_cancels_obsolete_callback_before_dialing(configured):
    call,identifier=make_followup_ready(configured,question=True)
    prepare_callback()
    phone.store().resume(call['actor'],identifier,'Say hello.',CALL)
    prepare_callback()
    assert phone.store().outbound(call['actor'])[0]['state']=='cancelled'


def test_active_call_prevents_followup_and_old_jobs_do_not_get_called(configured):
    call,identifier=make_followup_ready(configured)
    with phone.store().db() as db:
        db.execute("UPDATE phone_live_streams SET state='active',last_seen=?",(time.time(),))
    prepare_callback();assert phone.store().outbound(call['actor'])==[]
    with phone.store().db() as db:
        db.execute("UPDATE phone_live_streams SET state='closed'")
        db.execute('UPDATE phone_jobs SET followup_allowed=0,callback_requested=0')
    prepare_callback();assert phone.store().outbound(call['actor'])==[]


def test_callback_groups_results_and_keeps_uncertain_call_from_redialing(configured):
    call,identifier=make_followup_ready(configured)
    _,second=queued(configured,'second');finish(configured,second)
    with phone.store().db() as db: db.execute('UPDATE phone_notices SET created=?',(time.time()-40,))
    prepare_callback()
    with phone.store().db() as db:
        assert db.execute('SELECT count(DISTINCT followup_id) FROM phone_notices').fetchone()[0]==1
        db.execute("UPDATE phone_outbound SET state='uncertain'")
    prepare_callback();assert len(phone.store().outbound(call['actor']))==1


def test_missing_stream_heartbeat_releases_pending_followup(configured):
    call,identifier=make_followup_ready(configured)
    with phone.store().db() as db:
        db.execute('UPDATE phone_calls SET ended=NULL')
        db.execute("UPDATE phone_live_streams SET state='active',last_seen=?",(time.time()-60,))
    close_stale_streams()
    with phone.store().db() as db:
        assert db.execute('SELECT ended FROM phone_calls').fetchone()[0]
        assert db.execute('SELECT state FROM phone_live_streams').fetchone()[0]=='closed'
