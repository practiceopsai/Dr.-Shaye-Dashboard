"""Logical tasks over the existing phone queue, not a second executor.

Execution revisions keep their transport IDs. A task's root ID, version and
events survive those revisions and are shared by voice, text and workers.
All writes below run inside the caller's SQLite transaction.
"""
import hashlib
import json
import time


TERMINAL = {'completed', 'failed', 'uncertain', 'cancelled'}
STATES = {'planning': 'pending', 'queued': 'pending', 'claimed': 'running',
          'waiting_for_input': 'waiting_for_user', 'uncertain': 'failed', 'workflow':'running'}

# A correction fences a finite set of logical tasks, never all future work by
# that caller. Legacy holds are confined to their original conversation.
HOLD_MATCH = """h.actor=j.actor AND (
    (h.task_ids IS NULL AND h.source=j.call_id) OR
    EXISTS (SELECT 1 FROM json_each(COALESCE(h.task_ids,'[]')) target
            WHERE target.value=COALESCE(j.root_id,j.id)))"""


def migrate(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS phone_task_meta (
            id TEXT PRIMARY KEY, actor TEXT NOT NULL, current_job TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1, parent_task TEXT,
            modified INTEGER NOT NULL DEFAULT 0, artifact TEXT NOT NULL DEFAULT '',
            last_spoken_status TEXT NOT NULL DEFAULT '', updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS phone_task_events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            version INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
            created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS phone_task_event_task ON phone_task_events(task_id,seq);
        CREATE INDEX IF NOT EXISTS phone_task_meta_actor ON phone_task_meta(actor,current_job);
        CREATE TABLE IF NOT EXISTS phone_task_effects (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, job_id TEXT NOT NULL,
            version INTEGER NOT NULL, state TEXT NOT NULL, receipt TEXT NOT NULL DEFAULT '',
            created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS phone_task_holds (
            actor TEXT NOT NULL, source TEXT NOT NULL, created REAL NOT NULL,
            PRIMARY KEY(actor,source));
    ''')
    if 'task_ids' not in {r[1] for r in db.execute('PRAGMA table_info(phone_task_holds)')}:
        db.execute('ALTER TABLE phone_task_holds ADD COLUMN task_ids TEXT')


def event(db, task_id, kind, payload=None):
    meta = db.execute('SELECT version FROM phone_task_meta WHERE id=?', (task_id,)).fetchone()
    if meta:
        db.execute('INSERT INTO phone_task_events(task_id,version,kind,payload,created) VALUES (?,?,?,?,?)',
                   (task_id, meta['version'], kind, json.dumps(payload or {}), time.time()))


def track(db, job_id, *, parent_id=None):
    row = db.execute('SELECT * FROM phone_jobs WHERE id=?', (job_id,)).fetchone()
    if not row or row['state'] in {'expanded', 'resumed'}:
        return None
    # Intake envelopes are not user tasks. A continuation does have a root.
    if row['execution_class'] == 'intake' and (not row['parent_id'] or json.loads(row['plan'] or '{}').get('routing_clarification')):
        return None
    root = row['root_id'] or row['id']
    meta = db.execute('SELECT * FROM phone_task_meta WHERE id=?', (root,)).fetchone()
    if not meta:
        db.execute('INSERT INTO phone_task_meta(id,actor,current_job,parent_task,updated) VALUES (?,?,?,?,?)',
                   (root, row['actor'], job_id, parent_id, time.time()))
        event(db, root, 'created', {'job_id': job_id})
    elif meta['current_job'] != job_id:
        current = db.execute('SELECT created FROM phone_jobs WHERE id=?', (meta['current_job'],)).fetchone()
        if not current or current['created'] < row['created']:
            db.execute('UPDATE phone_task_meta SET current_job=?,updated=? WHERE id=?', (job_id,time.time(),root))
            event(db, root, 'revision', {'job_id': job_id})
    return root


def sync(db, actor):
    # Also imports historical jobs. No changes to their execution or receipts.
    for row in db.execute('SELECT id FROM phone_jobs WHERE actor=? ORDER BY created', (actor,)).fetchall():
        track(db, row['id'])


def snapshot(db, actor, task_id=None):
    sync(db, actor)
    rows = db.execute('''SELECT j.*,m.id AS task_id,m.version,m.parent_task,m.modified,
        m.artifact,m.last_spoken_status FROM phone_task_meta m JOIN phone_jobs j ON j.id=m.current_job
        WHERE m.actor=? AND (? IS NULL OR m.id=?) ORDER BY j.priority DESC,j.created''',
        (actor,task_id,task_id)).fetchall()
    tasks = []
    for row in rows:
        root = row['task_id']; plan = json.loads(row['plan'] or '{}')
        subtree=[x[0] for x in db.execute('''WITH RECURSIVE nodes(id) AS (SELECT ? UNION ALL
            SELECT m.id FROM phone_task_meta m JOIN nodes n ON m.parent_task=n.id) SELECT id FROM nodes''',(root,))]
        placeholders=','.join('?' for _ in subtree)
        effects = [dict(x) for x in db.execute('SELECT id,state,receipt FROM phone_task_effects WHERE task_id IN ('+placeholders+')',subtree)]
        receipts = [dict(x) for x in db.execute('''SELECT u.tool,u.status,u.content FROM phone_job_updates u
            JOIN phone_jobs j ON j.id=u.job_id WHERE COALESCE(j.root_id,j.id) IN ('''+placeholders+''')
            AND u.kind='action' AND u.status IN ('sent','verified','accepted')''',subtree)]
        boundary = any(x['state'] in {'committed','verified'} for x in effects) or bool(receipts)
        inflight = any(x['state'] in {'reserved','uncertain'} for x in effects)
        state = STATES.get(row['state'],row['state'])
        if row['modified'] and state == 'pending': state = 'modified'
        mutation = plan.get('atomic_kind') in {'email','imessage','whatsapp','calendar','article','global','deliver'} or bool(plan.get('workflow',{}).get('channel') and plan.get('operation')=='workflow')
        confirmed = any(x['status'] in {'sent','verified'} for x in receipts) or any(x['state']=='verified' for x in effects)
        blockers = holds_for(db, row['id']) if state not in TERMINAL else []
        tasks.append({'id':root,'job_id':row['id'],'version':row['version'],'parent_id':row['parent_task'],
            'intent_summary':plan.get('atomic_scope',row['transcript'].rsplit('New caller speech: ',1)[-1]),
            'parameters':{**plan.get('details',{}),'recipient':plan.get('recipient',''),
                          'message':plan.get('message',{}),'kind':plan.get('atomic_kind','')},
            'state':state,'execution_state':row['state'],'priority':row['priority'],
            'depends_on':json.loads(row['depends_on'] or '[]'),'idempotency_key':'task:'+root,
            'irreversible_boundary_passed':boundary,'effect_in_flight':inflight,
            'cancel_requested':bool(row['cancel_requested']),
            'created_at':db.execute('SELECT min(created) FROM phone_jobs WHERE COALESCE(root_id,id)=?',(root,)).fetchone()[0],
            'updated_at':row['updated'],
            'execution_log':[dict(x) for x in db.execute('SELECT seq,version,kind,payload,created FROM phone_task_events WHERE task_id=? ORDER BY seq',(root,))],
            'result_or_artifact_pointer':row['artifact'] or row['result'],
            'last_spoken_status':row['last_spoken_status'],'question':row['question'],
            'question_id':row['id'] if row['state']=='waiting_for_input' else None,
            'completion_allowed':state=='completed' and (not mutation or confirmed),
            'held':bool(blockers), 'blockers':blockers,
            'receipts':receipts,'call_id':row['call_id'],
            'error':row['error'],'request':row['transcript'].rsplit('New caller speech: ',1)[-1]})
    return tasks


def get(db, actor, task_id):
    tasks = snapshot(db, actor, task_id)
    if not tasks: raise ValueError('Unknown task')
    return tasks[0]


def hold(db, actor, source, *, call_id=None):
    targets={r[0] for r in db.execute("""SELECT COALESCE(root_id,id) FROM phone_jobs
        WHERE actor=? AND state IN ('queued','claimed','running','workflow','waiting_for_input')
        AND execution_class!='intake' AND (? IS NULL OR call_id=?)""",(actor,call_id,call_id))}
    old=db.execute('SELECT task_ids FROM phone_task_holds WHERE actor=? AND source=?',(actor,source)).fetchone()
    if old and old['task_ids'] is not None:targets.update(json.loads(old['task_ids']))
    db.execute('''INSERT INTO phone_task_holds(actor,source,created,task_ids) VALUES (?,?,?,?)
        ON CONFLICT(actor,source) DO UPDATE SET task_ids=excluded.task_ids''',
        (actor,source,time.time(),json.dumps(sorted(targets))))


def holds_for(db, job_id):
    rows=db.execute('SELECT h.source FROM phone_task_holds h JOIN phone_jobs j ON '+HOLD_MATCH+' WHERE j.id=?',(job_id,)).fetchall()
    return [{'source':r['source'],'reason':'Execution is paused while a possible change or cancellation is clarified. Nothing has been sent by this task.'} for r in rows]


def release(db, actor, source):
    unresolved=db.execute("""SELECT 1 FROM phone_jobs WHERE actor=? AND call_id=?
        AND (state='planning' OR (state='waiting_for_input'
        AND json_extract(plan,'$.routing_clarification')=1)) LIMIT 1""",(actor,source)).fetchone()
    if unresolved:return
    db.execute('DELETE FROM phone_task_holds WHERE actor=? AND source=?',(actor,source))


def control(db, job_id):
    root = track(db,job_id)
    row = db.execute('SELECT * FROM phone_jobs WHERE id=?',(job_id,)).fetchone()
    if not row: raise ValueError('Unknown task')
    meta = db.execute('SELECT * FROM phone_task_meta WHERE id=?',(root,)).fetchone() if root else None
    return {'state':row['state'],'task_id':root or job_id,'version':meta['version'] if meta else 1,
        'superseded':bool(meta and meta['current_job']!=job_id),'cancel_requested':bool(row['cancel_requested']),
        'held':bool(holds_for(db,job_id))}


def require_mutable(task):
    if task['irreversible_boundary_passed']: raise ValueError('The external action already committed; it cannot be changed or unsent')
    if task['effect_in_flight']: raise ValueError('An external action is in flight; its outcome must be reconciled before changes')
    if task['execution_state'] in TERMINAL: raise ValueError('A finished task cannot be executed again')


def cancel(db, actor, task_id):
    task = get(db,actor,task_id)
    if task['state']=='cancelled':return task
    require_mutable(task)
    db.execute('UPDATE phone_jobs SET cancel_requested=?,callback_requested=0,updated=? WHERE COALESCE(root_id,id)=?',
               (time.time(),time.time(),task_id))
    db.execute("UPDATE phone_jobs SET state='cancelled' WHERE COALESCE(root_id,id)=? AND state IN ('planning','queued','claimed','waiting_for_input','workflow')",(task_id,))
    event(db,task_id,'cancel_requested',{'job_id':task['job_id']})
    for child in db.execute('SELECT id FROM phone_task_meta WHERE parent_task=?',(task_id,)).fetchall():
        try:cancel(db,actor,child['id'])
        except ValueError:event(db,task_id,'child_cancellation_pending',{'task_id':child['id']})
    return get(db,actor,task_id)


def prioritize(db, actor, task_id, priority):
    if type(priority) is not int or not 0 <= priority <= 1000:raise ValueError('Invalid priority')
    task = get(db,actor,task_id)
    if task['execution_state'] in TERMINAL:raise ValueError('A finished task cannot be reprioritized')
    db.execute('UPDATE phone_jobs SET priority=?,updated=? WHERE id=?',(priority,time.time(),task['job_id']))
    for child in db.execute('SELECT id FROM phone_task_meta WHERE parent_task=?',(task_id,)).fetchall():
        try:prioritize(db,actor,child['id'],priority)
        except ValueError:pass  # Already-finished prerequisites retain their receipts.
    event(db,task_id,'priority',{'priority':priority})
    return get(db,actor,task_id)


def revise(db, actor, task_id, instruction, source_id, *, call_id=None):
    """Invalidate old execution, retain the logical ID and rebuild from evidence."""
    task = get(db,actor,task_id)
    identifier = hashlib.sha256(('revision:'+task_id+':'+source_id).encode()).hexdigest()[:32]
    if db.execute('SELECT 1 FROM phone_jobs WHERE id=?',(identifier,)).fetchone():return task
    require_mutable(task)
    if not isinstance(instruction,str) or not instruction.strip() or len(instruction)>6000:raise ValueError('Invalid task change')
    row = dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(task['job_id'],)).fetchone())
    plan = json.loads(row['plan'] or '{}')
    plan.update(continuation_replan=True, modification=True,
        clarification_history=plan.get('clarification_history',[])+[{'question_id':row['id'],'question':'Task modification',
            'answer':instruction,'source_job':source_id}])
    transcript = ('Rebuild the SAME task. The latest explicit change overrides only the specified fields. '
        'Do not repeat any completed effect.\nNew caller speech: '+task['request']+'\n'+instruction)
    now=time.time()
    for child in db.execute('SELECT id FROM phone_task_meta WHERE parent_task=?',(task_id,)).fetchall():
        try:cancel(db,actor,child['id'])
        except ValueError:
            child_task=get(db,actor,child['id'])
            if child_task['effect_in_flight'] or child_task['irreversible_boundary_passed']:raise
    db.execute('UPDATE phone_jobs SET cancel_requested=?,callback_requested=0 WHERE COALESCE(root_id,id)=?',(now,task_id))
    db.execute("UPDATE phone_jobs SET state='resumed',resume_job=? WHERE id=? AND state IN ('planning','queued','claimed','waiting_for_input','workflow')",(identifier,row['id']))
    columns=['id','actor','call_id','transcript','state','created','updated','audio_state','root_id','parent_id',
             'logical_request_id','idempotency_key','authorization','plan','execution_class','priority','notify_policy','batch_id','resource_key','depends_on']
    values=[identifier,actor,call_id or row['call_id'],transcript,'planning',now,now,'live',task_id,row['id'],task_id,
            'revision:'+identifier,row['authorization'],json.dumps(plan),'intake',row['priority'],row['notify_policy'],row['batch_id'],row['resource_key'],row['depends_on']]
    db.execute('INSERT INTO phone_jobs('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',values)
    db.execute('INSERT INTO phone_live_delegations VALUES (?,?,?,?)',(call_id or row['call_id'],'revision:'+identifier,identifier,task['request']+'\n'+instruction))
    db.execute('UPDATE phone_task_meta SET current_job=?,version=version+1,modified=1,updated=? WHERE id=?',(identifier,now,task_id))
    event(db,task_id,'modified',{'instruction':instruction,'source':source_id,'previous_job':row['id'],'job_id':identifier})
    return get(db,actor,task_id)


def reserve_effect(db, job_id, version, key):
    """Atomic final fence; a reservation is NOT proof of provider acceptance."""
    c=control(db,job_id)
    if c['version']!=version or c['superseded'] or c['held'] or c['cancel_requested'] or c['state']!='running':
        raise ValueError('Task changed, paused or stopped before the effect')
    identifier=hashlib.sha256((c['task_id']+':'+key).encode()).hexdigest()
    if db.execute('SELECT 1 FROM phone_task_effects WHERE id=?',(identifier,)).fetchone():
        raise ValueError('Effect already has an attempt; reconcile it instead of replaying')
    now=time.time()
    db.execute('INSERT INTO phone_task_effects VALUES (?,?,?,?,?,?,?,?)',
               (identifier,c['task_id'],job_id,version,'reserved','',now,now))
    event(db,c['task_id'],'effect_reserved',{'id':identifier,'job_id':job_id})
    return identifier


def finish_effect(db, job_id, effect_id, state, receipt):
    if state not in {'committed','verified','rejected','uncertain'}:raise ValueError('Invalid effect state')
    row=db.execute('SELECT * FROM phone_task_effects WHERE id=? AND job_id=?',(effect_id,job_id)).fetchone()
    if not row:raise ValueError('Unknown effect')
    if state in {'committed','verified'} and not receipt:raise ValueError('A provider receipt is required')
    if row['state']=='verified' or row['state']==state:return
    if row['state']=='committed' and state!='verified':raise ValueError('A committed effect cannot be undone')
    db.execute('UPDATE phone_task_effects SET state=?,receipt=?,updated=? WHERE id=?',(state,json.dumps(receipt),time.time(),effect_id))
    event(db,row['task_id'],'effect_'+state,{'id':effect_id,'receipt':receipt})


def mark_spoken(db, actor, task_id, status):
    get(db,actor,task_id)
    db.execute('UPDATE phone_task_meta SET last_spoken_status=?,updated=? WHERE id=?',(status[:500],time.time(),task_id))
    event(db,task_id,'spoken',{'status':status[:500]})
