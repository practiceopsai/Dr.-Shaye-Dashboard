import asyncio,json,time
import pytest
from fastapi import HTTPException
from app import phone,phone_live as live,phone_dispatch as dispatch,phone_presence as presence
from test_phone import setup
from test_phone_live import configured,authenticated_stream,FakeModel,fragment,STREAM
from test_phone_two_layer import intake


def task(kind,quote,**kw):
    return {'kind':kind,'scope':kind+' for Owner','quotes':[quote],'after':[],'recipient':'Owner','message':'',
            'question':'','resume_request_id':'','details':{},**kw}


def plan(*jobs):return {'conversation_only':False,'jobs':list(jobs)}


def row(identifier):
    with phone.store().db() as db:return dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(identifier,)).fetchone())


def answer(call,question,text):
    identifier=live.enqueue(call,'answer:'+str(time.time_ns()),'New caller speech: '+text,text,intake=True)
    ids=dispatch.commit_plan(row(identifier),plan(task('clarification',text,resume_request_id=question)))
    assert len(ids)==1
    return row(ids[0])


def test_two_open_tasks_keep_answers_roots_and_payloads_separate(configured):
    quote='Send Owner an invitation at 2 PM and send him an AI article.'
    call,initial=intake(configured,quote)
    calendar,article=dispatch.commit_plan(initial,plan(
        task('calendar',quote,question='What date, duration, timezone and hosting account?'),
        task('article',quote,question='Which channel?')))
    continuation=answer(call,calendar,"Tomorrow, one hour, Pacific, title AI Test Meeting, from Eli's email.")
    state=presence.task_states(call)[calendar]
    assert state['state']=='planning' and state['question_id'] is None and not state['completion_allowed']
    speech=continuation['transcript'].rsplit('New caller speech: ',1)[-1]
    details={'title':'AI Test Meeting','date':'2027-09-22','time':'14:00','timezone':'America/Los_Angeles','duration_minutes':'60','organizer':'eli'}
    invitation=dispatch.commit_plan(continuation,plan(task('calendar',speech,details=details)))[0]
    continuation=answer(call,article,'Use WhatsApp, any source.')
    speech=continuation['transcript'].rsplit('New caller speech: ',1)[-1]
    delivery=dispatch.commit_plan(continuation,plan(task('article',speech,details={'channel':'WhatsApp','query':'AI','selection':'any'})))[0]
    assert row(invitation)['root_id']==calendar and row(delivery)['root_id']==article
    assert phone.store().questions(call['actor'],call['id'])==[]
    a,b=phone.store().claim(),phone.store().claim()
    assert {a['id'],b['id']}=={invitation,delivery}  # Real work can execute in parallel.
    assert json.loads(row(invitation)['plan'])['calendar']['organizer']=='eli'
    assert json.loads(row(delivery)['plan'])['article']['channel']=='whatsapp'
    assert 'Pacific' not in row(delivery)['transcript']
    assert all(not s['completion_allowed'] for s in presence.task_states(call).values())
    with phone.store().db() as db:
        assert not db.execute("SELECT 1 FROM phone_jobs WHERE json_extract(plan,'$.atomic_kind')='clarification'").fetchone()


def test_replan_precedes_later_answer_and_does_not_reset_known_fields(configured):
    call,initial=intake(configured,'Send Owner an invitation titled AI Test Meeting.')
    root=dispatch.commit_plan(initial,plan(task('calendar','Send Owner an invitation titled AI Test Meeting.',question='Which account and when?')))[0]
    first=live.enqueue(call,'first','New caller speech: From Eli, tomorrow at 2 PM Pacific.','From Eli, tomorrow at 2 PM Pacific.',intake=True)
    later=live.enqueue(call,'later','New caller speech: One hour.','One hour.',intake=True)
    resumed=dispatch.commit_plan(row(first),plan(task('clarification','From Eli, tomorrow at 2 PM Pacific.',resume_request_id=root)))[0]
    assert dispatch.take_intake()['id']==resumed
    assert dispatch.take_intake() is None  # Later answer waits for this pure planning step, never for Hermes.
    quote=row(resumed)['transcript'].rsplit('New caller speech: ',1)[-1]
    revision=dispatch.commit_plan(row(resumed),plan(task('calendar',quote,details={'organizer':'eli'},question='How long?')))[0]
    assert dispatch.take_intake()['id']==later
    resumed2=dispatch.commit_plan(row(later),plan(task('clarification','One hour.',resume_request_id=revision)))[0]
    history=json.loads(row(resumed2)['plan'])['clarification_history']
    assert [h['question_id'] for h in history]==[root,revision]
    assert len(phone.store().jobs(call['actor']))>=1


def test_calendar_always_asks_host_even_with_other_details(configured):
    quote='Send Owner a calendar invitation titled Meeting tomorrow at 2 PM Pacific for one hour.'
    call,initial=intake(configured,quote)
    identifier=dispatch.commit_plan(initial,plan(task('calendar',quote,details={'title':'Meeting','date':'2027-09-22','time':'14:00','timezone':'America/Los_Angeles','duration_minutes':'60'})))[0]
    assert row(identifier)['state']=='waiting_for_input'
    assert "Eli's email" in row(identifier)['question']
    assert phone.store().claim() is None


def test_completion_requires_this_jobs_verified_receipt_and_promotes_acceptance(configured):
    call,initial=intake(configured,'Email Owner hello')
    identifier=dispatch.commit_plan(initial,plan(task('email','Email Owner hello',message='hello')))[0]
    claimed=phone.claim_job()['job'];claim=claimed['claim']
    update=phone.JobUpdate(claim=claim,state='completed',result='Sent.')
    with pytest.raises(HTTPException,match='409'):phone.update_job(identifier,update)
    def event(status):return phone.JobProgress(claim=claim,events=[phone.ProgressEvent(event_id='receipt-one',kind='action',tool='email_send',status=status)])
    phone.job_progress(identifier,event('accepted'))
    with pytest.raises(HTTPException):phone.update_job(identifier,update)
    phone.job_progress(identifier,event('verified'))
    phone.update_job(identifier,update)
    assert presence.task_states(call)[identifier]['completion_allowed']


def test_current_task_status_uses_local_ledger_without_another_job(configured):
    call,initial=intake(configured,'Email Owner hello')
    identifier=dispatch.commit_plan(initial,plan(task('email','Email Owner hello',message='hello')))[0]
    model=FakeModel();voice=live.LiveCall(None,model,configured[0],call,STREAM)
    voice.conversation.append(fragment('status','Did both tasks complete? What did you actually send?'));voice.conversation.last_input=0
    asyncio.run(voice.delegate('status-question',1000))
    assert 'completion_allowed' in ''.join(e.get('content','') for e in model.sent)
    with phone.store().db() as db:assert db.execute('SELECT count(*) FROM phone_jobs').fetchone()[0]==2
    assert not presence.task_status_question('Did you send it? Please send it again.')
    assert not presence.task_status_question('Did you send it and email Owner hello?')
