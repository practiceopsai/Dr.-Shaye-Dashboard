import json
import time
from app import phone, phone_dispatch as dispatch, task_ledger as ledger
from test_phone import setup
from test_phone_live import configured
from test_phone_two_layer import intake,pair
from test_task_interpretation import operation


def test_m_authenticated_text_cancels_voice_task_and_retries_do_not_duplicate(configured):
    cfg,client=configured;call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    payload={'actor':call['actor'],'user_id':phone.callers()[call['actor']]['user_id'],
             'platform':'whatsapp','conversation_id':'private-dm','message_id':'transport-id-1','text':'Cancel the pending email'}
    result=client.post('/internal/tasks/utterance',json=payload,headers=headers)
    assert result.status_code==200,result.text
    assert client.post('/internal/tasks/utterance',json=payload,headers=headers).json()['intake_id']==result.json()['intake_id']
    with phone.store().db() as db:captured=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(result.json()['intake_id'],)).fetchone())
    dispatch.commit_plan(captured,operation(captured,'CANCEL',ids[1]))
    tasks=client.post('/internal/tasks/state',json={'actor':call['actor']},headers=headers).json()['tasks']
    assert next(t for t in tasks if t['id']==ids[1])['state']=='cancelled'
    assert len(tasks)==2
    assert client.post('/internal/tasks/utterance',json={**payload,'user_id':'other'},headers=headers).status_code==403
    assert client.post('/internal/tasks/utterance',json=payload).status_code==403


def test_external_effect_final_fence_checks_claim_hold_and_version(configured):
    cfg,client=configured;call,row=intake(configured);ids=dispatch.commit_plan(row,pair())
    job=phone.store().claim();headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    client.post('/internal/phone/jobs/'+job['id'],json={'claim':job['claim'],'state':'running'},headers=headers)
    payload={'claim':job['claim'],'version':1,'key':'one-effect'}
    path='/internal/phone/jobs/'+job['id']+'/effect'
    with phone.store().db() as db:ledger.hold(db,call['actor'],'correction')
    assert client.post(path,json=payload,headers=headers).status_code==409
    with phone.store().db() as db:ledger.release(db,call['actor'],'correction')
    assert client.post(path,json=payload,headers=headers).status_code==200
    assert client.post(path,json=payload,headers=headers).status_code==409
    assert client.post(path,json={**payload,'state':'verified','receipt':{'provider_id':'one'}},headers=headers).status_code==200
    cancellation=phone.store().cancel(call['actor'],job['id'])
    assert cancellation['irreversible_boundary_passed'] and not cancellation['effect_cancelled']
