"""Regression for the two September 23 calls: saved emails never reached Hermes."""
import asyncio
import json
import time
import pytest
from app import phone, phone_live as live, phone_dispatch as dispatch, task_ledger as ledger, phone_presence
from app.phone_store import PhoneStore
from test_phone import setup
from test_phone_live import configured
from test_phone_two_layer import intake, pair
from test_task_interpretation import change


def new_call(original, identifier):
    call={**original,'id':identifier}
    with phone.store().db() as db:
        db.execute('INSERT INTO phone_calls(id,actor,phone,nonce,created,authenticated) VALUES (?,?,?,?,?,1)',
            (identifier,call['actor'],call['phone'],'test',time.time()))
    return call


def email(row, message='hello'):
    text=row['transcript'].rsplit('New caller speech: ',1)[-1]
    return dispatch.commit_plan(row,{'conversation_only':False,'jobs':[
        {'scope':'Email Owner '+message,'quotes':[text],'kind':'email','after':[],'recipient':'Owner','message':message}]})[0]


def test_legacy_hold_cannot_starve_new_call_or_text_after_restart(configured):
    call,row=intake(configured);old=dispatch.commit_plan(row,pair())
    with phone.store().db() as db:
        db.execute('INSERT INTO phone_task_holds(actor,source,created) VALUES (?,?,?)',(call['actor'],call['id'],time.time()))
        db.execute('UPDATE phone_calls SET ended=? WHERE id=?',(time.time(),call['id']))
    for identifier in ['new-phone-call','text:new-thread']:
        current=new_call(call,identifier)
        job=email(change(current,'Email Owner hello'))
        phone._stores.clear()
        claimed=phone.store().claim()
        assert claimed['id']==job
        with phone.store().db() as db:
            assert not ledger.control(db,job)['held']
            db.execute("UPDATE phone_jobs SET state='completed' WHERE id=?",(job,))
            assert all(ledger.control(db,k)['held'] for k in old)
    assert phone.store().claim() is None  # Historical sends were not replayed.


def test_ambiguous_control_holds_only_existing_tasks_and_exposes_blocker(configured):
    call,row=intake(configured);old=dispatch.commit_plan(row,pair())
    request=change(call,'Cancel that')
    dispatch.commit_plan(request,{'conversation_only':True,'jobs':[],'routing_question':'The text or the email?'})
    newer=email(change(call,'Email Owner a new message'),'a new message')
    assert phone.store().claim()['id']==newer
    assert phone.store().claim() is None
    state=phone_presence.task_states(call)
    assert state[old[1]]['held'] and not state[old[1]]['completion_allowed']
    assert 'paused' in state[old[1]]['blockers'][0]['reason']
    assert not state[newer]['held']


def test_ordinary_clarification_cannot_pause_ready_email(configured):
    call,row=intake(configured,'Email Owner hello');ready=email(row)
    request=change(call,'Say hello this is a test')
    dispatch.commit_plan(request,{'conversation_only':True,'jobs':[],
        'routing_question':'Which request do you mean?'})
    assert phone.store().claim()['id']==ready


def test_planner_questions_and_tasks_belong_to_current_call(configured,monkeypatch):
    configured[0].phone_dispatch_model='planner-fixture'
    call,row=intake(configured,'Email Owner')
    old=email(row,'')
    current=new_call(call,'new-call')
    row=change(current,'Email Owner hello')
    captured={}
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,**kwargs):
            captured.update(json.loads(kwargs['json']['input']))
            class Response:
                def raise_for_status(self):pass
                def json(self):return {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(
                    {'conversation_only':True,'jobs':[],'operations':[],'input_quality':'uncertain','routing_question':''})}]}]}
            return Response()
    monkeypatch.setattr(dispatch.httpx,'AsyncClient',Client)
    result=asyncio.run(dispatch.plan_intake(row,configured[0]))
    assert not captured['open_questions'] and old not in captured['current_tasks']
    assert 'other_tasks' not in captured
    assert 'previous_call' not in captured['session_context']
    assert not result['routing_question']  # An unfinished fragment is not a cancellation.
    # Explicit cross-channel cancellation can still identify its target.
    row=change(current,'Cancel the pending email')
    asyncio.run(dispatch.plan_intake(row,configured[0]))
    assert old in captured['other_tasks']


def test_answer_cannot_attach_to_old_call_question(configured):
    call,row=intake(configured,'Email Owner');old=email(row,'')
    current=new_call(call,'new-call');row=change(current,'Say hello')
    with pytest.raises(ValueError,match='not in this call'):
        dispatch.commit_plan(row,{'conversation_only':False,'jobs':[
            {'scope':'Answer email question','quotes':['Say hello'],'kind':'clarification','after':[],'resume_request_id':old}]})
