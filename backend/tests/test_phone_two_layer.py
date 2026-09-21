import asyncio
import json
import time

import pytest

from app import phone, phone_dispatch as dispatch, phone_live as live
from test_phone import setup
from test_phone_live import configured, authenticated_stream, FakeModel, fragment, STREAM


def intake(configured, text='Text Owner hello and email Owner hello.'):
    cfg,_=configured
    call=live.activate_stream(authenticated_stream(configured),cfg)
    identifier=live.enqueue(call,'compound','New caller speech: '+text,text,origin_turn_id='one',intake=True)
    with phone.store().db() as db:
        row=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(identifier,)).fetchone())
    return call,row


def pair():
    return {'conversation_only':False,'jobs':[
        {'scope':'Text Owner hello','quotes':['Text Owner hello'],'kind':'imessage','after':[],'recipient':'Owner','message':'hello'},
        {'scope':'Email Owner hello','quotes':['email Owner hello.'],'kind':'email','after':[],'recipient':'Owner','message':'hello'}]}


def test_compound_is_atomic_parallel_and_cannot_replay_after_hangup(configured):
    call,row=intake(configured)
    assert phone.store().claim() is None  # Raw compound never enters Hermes.
    with phone.store().db() as db:
        db.execute('UPDATE phone_calls SET ended=?',(time.time(),))
    ids=dispatch.commit_plan(row,pair())
    assert len(ids)==2
    assert dispatch.commit_plan(row,pair())==[]
    a=phone.store().claim('agent');b=phone.store().claim('agent')
    assert {a['id'],b['id']}==set(ids)  # Same actor can run both concurrently.
    assert a['root_id']!=b['root_id'] and a['batch_id']==b['batch_id']==row['id']
    assert phone.store().claim('agent') is None
    with phone.store().db() as db:
        db.execute("UPDATE phone_jobs SET state='completed' WHERE id IN (?,?)",ids)
    assert phone.store().claim() is None
    assert 'email Owner' not in a['transcript'].split('New caller speech: ')[-1]


def test_dependencies_and_conflicts_hold_only_related_work(configured):
    _,row=intake(configured)
    plan=pair();plan['jobs'][1]['after']=[0]
    ids=dispatch.commit_plan(row,plan)
    assert phone.store().claim()['id']==ids[0]
    assert phone.store().claim() is None
    with phone.store().db() as db:db.execute("UPDATE phone_jobs SET state='completed' WHERE id=?",(ids[0],))
    assert phone.store().claim()['id']==ids[1]


def test_planning_restart_reclaims_only_expired_planning_lease(configured):
    _,row=intake(configured)
    assert dispatch.take_intake()['id']==row['id']
    assert dispatch.take_intake() is None
    with phone.store().db() as db:db.execute('UPDATE phone_jobs SET plan_lease=?',(time.time()-1,))
    assert dispatch.take_intake()['id']==row['id']
    assert phone.store().claim() is None


def test_plan_cannot_invent_approval_or_dependency(configured):
    _,row=intake(configured)
    p=pair();p['jobs'][0]['quotes']=['Send my bank details']
    with pytest.raises(ValueError,match='invented'):dispatch.commit_plan(row,p)
    p=pair();p['jobs'][0]['after']=[1]
    with pytest.raises(ValueError,match='dependency'):dispatch.commit_plan(row,p)
    assert phone.store().claim() is None


def test_cancelled_intake_cannot_expand(configured):
    call,row=intake(configured)
    phone.store().cancel(call['actor'],row['id'])
    assert dispatch.commit_plan(row,pair())==[]
    assert phone.store().claim() is None


def test_failed_planning_retains_question_and_can_resume(configured):
    call,row=intake(configured)
    async def unavailable(*args):raise TimeoutError()
    for _ in range(3):
        with phone.store().db() as db:db.execute('UPDATE phone_jobs SET plan_lease=NULL')
        asyncio.run(dispatch.dispatch_once(unavailable))
    assert phone.store().questions(call['actor'])[0]['id']==row['id']
    child=phone.store().resume(call['actor'],row['id'],'Only the email, please.',call['id'])
    assert dispatch.take_intake()['id']==child
    assert phone.store().claim() is None


@pytest.mark.parametrize('text',['What time is it?','What day is today?','What model are you?',"Who is on Dr. Shaye's team?"])
def test_local_questions_never_touch_planner_or_hermes(configured,text):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    model=FakeModel();voice=live.LiveCall(None,model,cfg,call,STREAM)
    voice.conversation.append(fragment('q',text));voice.conversation.last_input=0
    asyncio.run(voice.delegate('unneeded',1000))
    voice.save_final_request()
    assert phone.store().jobs(call['actor'])==[]
    assert 'current_datetime' in ''.join(e.get('content','') for e in model.sent)


def test_result_is_context_once_even_during_speech_and_topic_change(configured):
    call,row=intake(configured)
    ids=dispatch.commit_plan(row,pair())
    with phone.store().db() as db:
        for identifier in ids:
            db.execute("UPDATE phone_jobs SET state='completed' WHERE id=?",(identifier,))
            db.execute('INSERT INTO phone_notices(job_id,actor,kind,content,created) VALUES (?,?,?,?,?)',
                       (identifier,call['actor'],'result','Verified result.',time.time()))
    model=FakeModel();voice=live.LiveCall(None,model,configured[0],call,STREAM)
    voice.conversation.append(fragment('new-topic','Tell me about Japan.'))
    voice.last_speech=time.monotonic()
    asyncio.run(voice.deliver_ready_notice());asyncio.run(voice.deliver_ready_notice())
    assert len(model.sent)==2
    assert all(e['type']=='session.thinking.append' for e in model.sent)
    assert all('Original request:' in e['content'] for e in model.sent)
    assert all(n['heard_at'] is None for n in phone.store().notices(call['actor']))
    assert voice.active_notice is None  # No unrelated speech can acknowledge a result.


def test_failed_prerequisite_stops_child_instead_of_leaving_it_queued(configured):
    _,row=intake(configured)
    plan=pair();plan['jobs'][1]['after']=[0]
    ids=dispatch.commit_plan(row,plan)
    with phone.store().db() as db:db.execute("UPDATE phone_jobs SET state='uncertain' WHERE id=?",(ids[0],))
    dispatch.settle_dependencies()
    assert phone.store().claim() is None
    with phone.store().db() as db:
        child=db.execute('SELECT state,error FROM phone_jobs WHERE id=?',(ids[1],)).fetchone()
    assert child['state']=='failed' and 'required earlier task' in child['error']


def test_conversation_only_intake_is_audit_not_a_user_task(configured):
    call,row=intake(configured,'What do you think about longer meetings?')
    assert dispatch.commit_plan(row,{'conversation_only':True,'jobs':[]})==[]
    assert phone.store().claim() is None
    assert phone.store().jobs(call['actor'])==[]
    assert live.presence.context_for(call,configured[0])['phone_work']==[]
    with phone.store().db() as db:
        assert db.execute('SELECT state FROM phone_jobs WHERE id=?',(row['id'],)).fetchone()['state']=='completed'
