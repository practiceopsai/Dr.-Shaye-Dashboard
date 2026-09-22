import json
import time
from app import phone, phone_dispatch as dispatch, task_ledger as ledger, task_workflow as workflow
from test_phone import setup
from test_phone_live import configured
from test_phone_two_layer import intake


def create(configured, text='Research a company, create a presentation, then email it to me', recipient='me'):
    call,row=intake(configured,text)
    ids=dispatch.commit_plan(row,{'conversation_only':False,'jobs':[{'scope':text,'quotes':[text],
        'kind':'workflow','recipient':recipient,'after':[],'details':{'deliverable':'pptx','channel':'email'}}]})
    return call,ids[0]


def test_f_plan_has_all_persisted_steps_and_only_dependency_ready_step_claims(configured):
    call,root=create(configured)
    with phone.store().db() as db:
        tasks=ledger.snapshot(db,call['actor']);children=[t for t in tasks if t['parent_id']==root]
        assert len(children)==7
        assert ledger.get(db,call['actor'],root)['state']=='running'
        assert [t['state'] for t in children].count('completed')==2
    claimed=phone.store().claim()
    assert json.loads(claimed['plan'])['stage']=='research'
    assert phone.store().claim() is None
    with phone.store().db() as db:
        db.execute("UPDATE phone_jobs SET state='completed',result='Research evidence' WHERE id=?",(claimed['id'],))
    assert json.loads(phone.store().claim()['plan'])['stage']=='create'


def test_g_third_party_requires_confirmation_and_approval_reuses_delivery_id(configured):
    text='Research a company and email Owner the findings'
    call,root=create(configured,text,'Owner')
    # Force a genuinely third-party configured destination for this test.
    with phone.store().db() as db:
        child=db.execute("SELECT * FROM phone_jobs WHERE json_extract(plan,'$.workflow_root')=? AND json_extract(plan,'$.stage')='deliver'",(root,)).fetchone()
        job=dict(child);p=json.loads(job['plan']);p['workflow'].update(preauthorized=False,recipient='guest@example.org')
        db.execute("UPDATE phone_jobs SET state='waiting_for_input',plan=?,question='May I send these findings?' WHERE id=?",(json.dumps(p),job['id']))
        resumed=workflow.approve_delivery(db,call['actor'],job['id'],'Yes','answer1')
        updated=ledger.get(db,call['actor'],job['id'])
        assert updated['id']==job['id'] and updated['job_id']==resumed
        new=db.execute('SELECT plan FROM phone_jobs WHERE id=?',(resumed,)).fetchone()
        assert json.loads(new['plan'])['workflow']['preauthorized']
        assert updated['state']=='modified'


def test_root_does_not_complete_when_a_step_claims_unconfirmed_delivery(configured):
    call,root=create(configured)
    with phone.store().db() as db:
        children=db.execute("SELECT id,plan FROM phone_jobs WHERE json_extract(plan,'$.workflow_root')=?",(root,)).fetchall()
        for child in children:
            db.execute("UPDATE phone_jobs SET state='completed',result='Claimed done' WHERE id=?",(child['id'],))
        workflow.settle(db)
        assert not ledger.get(db,call['actor'],root)['completion_allowed']
        assert ledger.get(db,call['actor'],root)['state']=='failed'


def test_parent_cancel_stops_pending_steps_and_running_step_gets_signal(configured):
    call,root=create(configured);claimed=phone.store().claim()
    with phone.store().db() as db:
        ledger.cancel(db,call['actor'],root)
        assert ledger.control(db,claimed['id'])['cancel_requested']
    assert phone.store().claim() is None


def test_parent_cannot_be_modified_after_delivery_commits(configured):
    call,root=create(configured)
    with phone.store().db() as db:
        child=db.execute("SELECT id FROM phone_jobs WHERE json_extract(plan,'$.workflow_root')=? AND json_extract(plan,'$.stage')='deliver'",(root,)).fetchone()[0]
        db.execute("UPDATE phone_jobs SET state='running' WHERE id=?",(child,))
        effect=ledger.reserve_effect(db,child,1,'send')
        ledger.finish_effect(db,child,effect,'committed',{'message_id':'provider-receipt'})
        import pytest
        with pytest.raises(ValueError,match='already committed'):ledger.revise(db,call['actor'],root,'Change recipient','change')
