import json
import time
import pytest
from app import phone, phone_live as live, phone_dispatch as dispatch, task_ledger as ledger
from test_phone import setup
from test_phone_live import configured, authenticated_stream
from test_phone_two_layer import intake, pair


def change(call, text):
    identifier=live.enqueue(call,'change:'+text,'New caller speech: '+text,text,intake=True)
    with phone.store().db() as db:return dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(identifier,)).fetchone())


def operation(row, kind, target, **kwargs):
    text=row['transcript'].rsplit('New caller speech: ',1)[-1]
    return {'conversation_only':True,'jobs':[],'operations':[{
        'type':kind,'task_id':target,'quote':text,'changes':text if kind=='MODIFY' else '',
        'priority':900 if kind=='PRIORITIZE' else 0,**kwargs}]}


def test_a_correction_same_logical_task_after_replan(configured):
    call,row=intake(configured,'Find flights to New York')
    ids=dispatch.commit_plan(row,{'conversation_only':False,'jobs':[{'scope':'Find flights','quotes':['Find flights to New York'],'kind':'read','after':[]}]})
    request=change(call,'Actually make that Boston')
    dispatch.commit_plan(request,operation(request,'MODIFY',ids[0]))
    with phone.store().db() as db:
        task=ledger.get(db,call['actor'],ids[0]);continuation=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(task['job_id'],)).fetchone())
    dispatch.commit_plan(continuation,{'conversation_only':False,'jobs':[{'scope':'Find Boston flights',
        'quotes':[continuation['transcript'].rsplit('New caller speech: ',1)[-1]],'kind':'read','after':[],'details':{'destination':'Boston'}}]})
    with phone.store().db() as db:
        tasks=ledger.snapshot(db,call['actor'])
        assert len(tasks)==1 and tasks[0]['id']==ids[0]
        assert tasks[0]['parameters']['destination']=='Boston'
    claimed=phone.store().claim()
    assert claimed['root_id']==ids[0] and 'Boston' in claimed['transcript']


def test_c_cancellation_before_boundary_and_h_priority(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    request=change(call,"Wait, don't send that text")
    dispatch.commit_plan(request,operation(request,'CANCEL',ids[0]))
    request=change(call,'Get the email done first')
    dispatch.commit_plan(request,operation(request,'PRIORITIZE',ids[1]))
    assert phone.store().claim()['id']==ids[1]
    with phone.store().db() as db:
        assert ledger.get(db,call['actor'],ids[0])['state']=='cancelled'
        assert ledger.get(db,call['actor'],ids[1])['priority']==900


def test_d_recipient_change_does_not_leave_original_send_runnable(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    request=change(call,'Actually send the email to Sarah instead')
    dispatch.commit_plan(request,operation(request,'MODIFY',ids[1]))
    with phone.store().db() as db:
        task=ledger.get(db,call['actor'],ids[1])
        assert task['version']==2 and task['state']=='modified'
        assert db.execute('SELECT state FROM phone_jobs WHERE id=?',(ids[1],)).fetchone()[0]=='resumed'
    assert phone.store().claim()['id']==ids[0]
    assert phone.store().claim() is None


def test_e_completed_reference_does_not_send_again(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    with phone.store().db() as db:db.execute("UPDATE phone_jobs SET state='completed' WHERE id=?",(ids[1],))
    request=change(call,'That email you sent earlier')
    dispatch.commit_plan(request,operation(request,'STATUS_CHECK',ids[1]))
    with phone.store().db() as db:
        assert len(ledger.snapshot(db,call['actor']))==2
        assert ledger.get(db,call['actor'],ids[1])['state']=='completed'


def test_m_control_from_another_conversation_same_actor(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    another={**call,'id':'text-conversation'}
    with phone.store().db() as db:
        db.execute('INSERT INTO phone_calls(id,actor,phone,nonce,created,authenticated) VALUES (?,?,?,?,?,1)',
            (another['id'],call['actor'],call['phone'],'test',time.time()))
    request=change(another,'Cancel the pending email')
    dispatch.commit_plan(request,operation(request,'CANCEL',ids[1]))
    with phone.store().db() as db:assert ledger.get(db,call['actor'],ids[1])['state']=='cancelled'


def test_n_partial_instruction_cannot_change_task_or_execute_send(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    request=change(call,'Actually send it to...')
    p=operation(request,'MODIFY',ids[1]);p['input_quality']='uncertain'
    dispatch.commit_plan(request,p)
    with phone.store().db() as db:assert ledger.get(db,call['actor'],ids[1])['version']==1
    request=change(call,'Send Owner something...')
    dispatch.commit_plan(request,{'conversation_only':False,'input_quality':'uncertain','jobs':[
        {'kind':'global','scope':'Unclear send','quotes':['Send Owner something...'],'after':[]}]})
    with phone.store().db() as db:
        task=next(t for t in ledger.snapshot(db,call['actor']) if t['intent_summary']=='Unclear send')
        assert task['state']=='waiting_for_user'


def test_ambiguous_answer_and_cross_actor_target_cannot_mutate(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    request=change(call,'Cancel that')
    dispatch.commit_plan(request,{'conversation_only':True,'jobs':[],'operations':[],
        'routing_question':'Do you mean the text or the email?'})
    with phone.store().db() as db:
        assert all(t['state']=='pending' for t in ledger.snapshot(db,call['actor']))
        assert not ledger.snapshot(db,'another-actor')
        with pytest.raises(ValueError):ledger.cancel(db,'another-actor',ids[0])


def test_ambiguous_cancel_stays_held_until_its_exact_answer_is_applied(configured):
    call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    request=change(call,'Cancel that')
    dispatch.commit_plan(request,{'conversation_only':True,'jobs':[],'operations':[],
        'routing_question':'Do you mean the text or the email?'})
    assert phone.store().claim() is None
    question=phone.store().questions(call['actor'])[0]
    # Unrelated dialogue cannot release this hold.
    with phone.store().db() as db:ledger.release(db,call['actor'],call['id'])
    assert phone.store().claim() is None
    answer=change(call,'The email')
    dispatch.commit_plan(answer,{'conversation_only':False,'jobs':[
        {'scope':'Answer cancellation question','kind':'clarification','quotes':['The email'],
         'after':[],'resume_request_id':question['id']}]})
    assert phone.store().claim() is None
    continuation=dispatch.take_intake()
    dispatch.commit_plan(continuation,operation(continuation,'CANCEL',ids[1]))
    assert phone.store().claim()['id']==ids[0]
    with phone.store().db() as db:
        assert len(ledger.snapshot(db,call['actor']))==2
        assert ledger.get(db,call['actor'],ids[1])['state']=='cancelled'


def test_third_party_gate_is_bound_to_exact_payload_and_approval():
    from app.task_approval import delivery_gate
    task={'kind':'email','recipient':'John','quotes':['Email John hello']}
    prepared={'operation':'send_message','message':{'recipient':'john@example.test','message':'hello'}}
    gate=delivery_gate(task,prepared,'owner@example.test',{}, {})
    assert gate
    prior={'delivery_gate':gate,'clarification_history':[{'question':gate['question'],'answer':'Yes'}]}
    assert delivery_gate(task,prepared,'owner@example.test',{},prior) is None
    prepared['message']['recipient']='sarah@example.test'
    assert delivery_gate(task,prepared,'owner@example.test',{},prior)
