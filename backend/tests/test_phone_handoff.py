import asyncio
import json
import time

from app import phone,phone_live as live,phone_dispatch as dispatch,phone_presence as presence
from test_phone import setup
from test_phone_live import configured,authenticated_stream,fragment,FakeModel,STREAM
from test_phone_two_layer import intake


def compound():
    return {'conversation_only':False,'jobs':[
        {'kind':'imessage','scope':'Text Owner running late','quotes':["text Owner that I'm running late"],
         'recipient':'Owner','message':"I'm running late",'question':'','resume_request_id':'','after':[]},
        {'kind':'email','scope':'Email Owner running late','quotes':["text Owner that I'm running late",'email him the same thing'],
         'recipient':'Owner','message':"I'm running late",'question':'','resume_request_id':'','after':[]}]}


def test_same_thing_is_materialized_before_two_jobs_are_ready(configured):
    call,row=intake(configured,"text Owner that I'm running late and email him the same thing")
    ids=dispatch.commit_plan(row,compound())
    a,b=phone.claim_job()['job'],phone.claim_job()['job']
    assert {a['id'],b['id']}==set(ids)
    for job in [a,b]:
        plan=json.loads(job['plan'])
        assert plan['operation']=='send_message' and plan['message']['message']=="I'm running late"
        assert "I'm running late" in job['transcript'].rsplit('New caller speech: ',1)[-1]
        assert job['open_questions']==[]


def test_missing_meeting_stops_at_intake_not_after_hermes(configured):
    call,row=intake(configured,'Email Owner about the meeting')
    ids=dispatch.commit_plan(row,{'conversation_only':False,'jobs':[
        {'kind':'email','scope':'Email Owner about meeting','quotes':['Email Owner about the meeting'],
         'recipient':'Owner','message':'','question':'Which meeting, and what should the email say?',
         'resume_request_id':'','after':[]}]})
    assert phone.store().claim() is None
    assert phone.store().questions(call['actor'],call['id'])[0]['id']==ids[0]


def test_shared_antecedent_is_preserved_when_planner_quote_omits_it(configured):
    call,row=intake(configured,"text Owner that I'm running late and email him the same thing")
    plan=compound();plan['jobs'][1]['quotes']=['email him the same thing']
    ids=dispatch.commit_plan(row,plan)
    assert phone.store().claim()['id']==ids[0]
    assert phone.store().claim()['id']==ids[1]
    assert phone.store().questions(call['actor'])==[]


def test_new_question_misclassified_as_clarification_is_saved_without_resuming(configured):
    call,row=intake(configured,'Email Owner about the meeting')
    ids=dispatch.commit_plan(row,{'conversation_only':False,'jobs':[
        {'kind':'clarification','scope':'Email Owner about meeting','quotes':['Email Owner about the meeting'],
         'recipient':'Owner','message':'','question':'Which meeting, and what should the email say?',
         'resume_request_id':'','after':[]}]})
    assert phone.store().claim() is None
    assert phone.store().questions(call['actor'],call['id'])[0]['id']==ids[0]


def test_new_message_cannot_answer_an_old_clarification(configured):
    call,row=intake(configured,"text Owner that I'm running late and email him the same thing")
    with phone.store().db() as db:
        db.execute("INSERT INTO phone_jobs(id,actor,call_id,transcript,created,updated,state,question) VALUES ('old',?,'older-call','Old request',1,1,'waiting_for_input','What text?')",(call['actor'],))
    ids=dispatch.commit_plan(row,compound())
    claimed=phone.claim_job()['job'];assert claimed['open_questions']==[]
    phone.update_job(claimed['id'],phone.JobUpdate(claim=claimed['claim'],state='running'))
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        phone.bridge_answer(claimed['id'],phone.BridgeAnswer(claim=claimed['claim'],request_id='old',answer="I'm running late"))
    assert exc.value.status_code==409


def test_last_call_excludes_current_and_other_callers(configured):
    call,_=intake(configured)
    with phone.store().db() as db:
        for sid,actor,created,text in [('earlier',call['actor'],call['created']-60,'Save two drafts'),
                                     ('other','another@example.com',call['created']-30,'Private other call')]:
            db.execute("INSERT INTO phone_calls(id,actor,phone,nonce,authenticated,created,ended) VALUES (?,?,?,'test',1,?,?)",(sid,actor,'+12025550101',created,created+10))
            db.execute('INSERT INTO phone_conversations(call_id,actor,payload,created) VALUES (?,?,?,?)',
                       (sid,actor,json.dumps({'turns':[{'role':'user','text':text}]}),created+10))
        db.execute('INSERT INTO phone_conversations(call_id,actor,payload,created) VALUES (?,?,?,?)',
                   (call['id'],call['actor'],json.dumps({'turns':[{'role':'user','text':'Current time/model questions'}]}),time.time()))
    result=presence.prior_call(call)
    assert result['call_id']=='earlier' and result['caller_words']=='Save two drafts'
    assert 'Current' not in json.dumps(result) and 'Private other' not in json.dumps(result)


def test_un_delegated_action_is_captured_without_audio_silence(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    voice=live.LiveCall(None,FakeModel(),cfg,call,STREAM)
    voice.conversation.append(fragment('one','Email Owner about the meeting'))
    voice.conversation.last_input=0
    voice.last_speech=time.monotonic()+100  # Background input energy must not block intake.
    async def run():
        await voice.capture_pending()
        await asyncio.wait_for(asyncio.gather(*voice.tasks),2)
    asyncio.run(run())
    jobs=phone.store().jobs(call['actor'])
    assert len(jobs)==1 and jobs[0]['state']=='planning'
    assert all(e.get('delegation_id') is None for e in voice.upstream.sent)
    assert 'TASK_READY' not in ''.join(e.get('content','') for e in voice.upstream.sent)


def test_result_context_keeps_original_delegation_and_tracks_ack(configured):
    cfg,_=configured;call,row=intake(configured,"text Owner that I'm running late and email him the same thing")
    ids=dispatch.commit_plan(row,compound())
    with phone.store().db() as db:
        db.execute("UPDATE phone_jobs SET state='failed',error='iMessage disconnected' WHERE id=?",(ids[0],))
        db.execute('INSERT INTO phone_notices(job_id,actor,kind,content,created) VALUES (?,?,?,?,?)',(ids[0],call['actor'],'result','iMessage disconnected',time.time()))
    model=FakeModel();voice=live.LiveCall(None,model,cfg,call,STREAM);voice.delegations.add('compound')
    asyncio.run(voice.deliver_ready_notice())
    sent=model.sent[0]
    assert sent['delegation_id']=='compound' and sent['type']=='session.thinking.append'
    assert sent['event_id'] in voice.context_receipts
    async def acknowledge():
        await model.queue.put({'type':'session.thinking.appended','client_event_id':sent['event_id']})
        await model.queue.put({'type':'session.closed'})
        await voice.receive_model()
    asyncio.run(acknowledge())
    assert sent['event_id'] not in voice.context_receipts
    assert any(e[2]=='context.accepted' for e in voice.runtime.events)
