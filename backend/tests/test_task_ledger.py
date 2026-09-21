import json
import time
import pytest
from app.phone_store import PhoneStore
from app import task_ledger as ledger


@pytest.fixture
def store(tmp_path):
    return PhoneStore(str(tmp_path/'ledger.db'))


def add(store, identifier='task1', state='queued', actor='owner', parent=None):
    with store.db() as db:
        db.execute('''INSERT INTO phone_jobs(id,actor,call_id,transcript,state,created,updated,root_id,plan,authorization)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',(identifier,actor,'call1','New caller speech: research a company',state,
                time.time(),time.time(),identifier,json.dumps({'atomic_kind':'read','atomic_scope':'Research company'}),'{}'))
        ledger.track(db,identifier,parent_id=parent)
    return identifier


def test_task_survives_restart_and_projects_required_fields(store):
    add(store)
    restored=PhoneStore(store.path)
    with restored.db() as db:
        task=ledger.get(db,'owner','task1')
        assert task['id']=='task1' and task['state']=='pending'
        assert {'parent_id','intent_summary','parameters','priority','depends_on','idempotency_key',
            'irreversible_boundary_passed','created_at','updated_at','execution_log',
            'result_or_artifact_pointer','last_spoken_status'}<=task.keys()
        assert len(task['execution_log'])==1
        assert not ledger.snapshot(db,'another-owner')


def test_modify_retains_logical_id_invalidates_worker_and_is_idempotent(store):
    add(store,state='running')
    with store.db() as db:
        changed=ledger.revise(db,'owner','task1','Actually use Boston','utterance-2')
        assert changed['id']=='task1' and changed['version']==2 and changed['state']=='modified'
        assert changed['job_id']!='task1'
        assert ledger.control(db,'task1')['superseded']
        assert ledger.control(db,'task1')['cancel_requested']
        again=ledger.revise(db,'owner','task1','Actually use Boston','utterance-2')
        assert again['job_id']==changed['job_id'] and again['version']==2
        assert len(ledger.snapshot(db,'owner'))==1


@pytest.mark.parametrize('state',['completed','failed','uncertain','cancelled'])
def test_terminal_reference_never_reexecutes(store,state):
    add(store,state=state)
    with store.db() as db:
        with pytest.raises(ValueError,match='finished'):
            ledger.revise(db,'owner','task1','Send again','utterance')
        assert db.execute('SELECT count(*) FROM phone_jobs').fetchone()[0]==1


def test_effect_fence_catches_hold_cancellation_and_stale_version(store):
    add(store,state='running')
    with store.db() as db:
        ledger.hold(db,'owner','possible correction')
        with pytest.raises(ValueError):ledger.reserve_effect(db,'task1',1,'send')
        ledger.release(db,'owner','possible correction')
        with pytest.raises(ValueError):ledger.reserve_effect(db,'task1',0,'send')
        ledger.cancel(db,'owner','task1')
        with pytest.raises(ValueError):ledger.reserve_effect(db,'task1',1,'send')


def test_inflight_and_committed_are_not_falsely_cancelled_or_replayed(store):
    add(store,state='running')
    with store.db() as db:
        effect=ledger.reserve_effect(db,'task1',1,'send')
        with pytest.raises(ValueError,match='in flight'):ledger.cancel(db,'owner','task1')
        with pytest.raises(ValueError,match='in flight'):ledger.revise(db,'owner','task1','Send to Sarah','change')
        with pytest.raises(ValueError,match='already'):ledger.reserve_effect(db,'task1',1,'send')
        ledger.finish_effect(db,'task1',effect,'verified',{'provider_id':'msg-1'})
        with pytest.raises(ValueError,match='already committed'):ledger.cancel(db,'owner','task1')
        assert ledger.get(db,'owner','task1')['irreversible_boundary_passed']
    restored=PhoneStore(store.path)
    with restored.db() as db:
        with pytest.raises(ValueError,match='already'):ledger.reserve_effect(db,'task1',1,'send')


def test_provider_receipt_required_and_rejected_write_allows_change(store):
    add(store,state='running')
    with store.db() as db:
        effect=ledger.reserve_effect(db,'task1',1,'send')
        with pytest.raises(ValueError,match='receipt'):ledger.finish_effect(db,'task1',effect,'verified',{})
        ledger.finish_effect(db,'task1',effect,'rejected',{'reason':'provider rejected before acceptance'})
        assert not ledger.get(db,'owner','task1')['irreversible_boundary_passed']
        assert ledger.revise(db,'owner','task1','Use another recipient','change')['version']==2


def test_cancel_parent_cancels_children_and_priority_changes_claim_order(store):
    add(store);add(store,'child',parent='task1');add(store,'independent')
    with store.db() as db:
        ledger.prioritize(db,'owner','independent',900)
        ledger.cancel(db,'owner','task1')
        assert ledger.get(db,'owner','child')['state']=='cancelled'
    assert store.claim()['id']=='independent'


def test_legacy_receipts_and_clarification_revision_are_preserved(store):
    add(store,state='resumed')
    with store.db() as db:
        db.execute('INSERT INTO phone_job_updates VALUES (?,?,?,?,?,?,?,?)',('task1','receipt','action','email_send','sent',1,'provider-1',time.time()))
        row=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',('task1',)).fetchone())
        row.update(id='continuation',state='completed',root_id='task1',created=time.time()+1)
        db.execute('INSERT INTO phone_jobs('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
        tasks=ledger.snapshot(db,'owner')
        assert len(tasks)==1 and tasks[0]['id']=='task1' and tasks[0]['job_id']=='continuation'
        assert tasks[0]['irreversible_boundary_passed'] and tasks[0]['receipts'][0]['content']=='provider-1'
