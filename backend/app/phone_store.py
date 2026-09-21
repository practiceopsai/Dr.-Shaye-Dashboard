"""Durable phone work. A disconnected call never deletes an accepted request."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time


class PhoneStore:
    def __init__(self, path: str):
        if not path:
            raise ValueError("Persistent phone storage is required")
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS phone_access (
                    actor TEXT PRIMARY KEY, salt TEXT, pin_hash TEXT,
                    failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS phone_calls (
                    id TEXT PRIMARY KEY, actor TEXT NOT NULL, phone TEXT NOT NULL,
                    authenticated INTEGER NOT NULL DEFAULT 0, nonce TEXT NOT NULL,
                    created REAL NOT NULL, outbound_id TEXT, hops INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS phone_events (
                    call_id TEXT NOT NULL, nonce TEXT NOT NULL, response TEXT NOT NULL,
                    PRIMARY KEY(call_id, nonce));
                CREATE TABLE IF NOT EXISTS phone_jobs (
                    id TEXT PRIMARY KEY, actor TEXT NOT NULL, call_id TEXT NOT NULL,
                    transcript TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
                    created REAL NOT NULL, updated REAL NOT NULL, claim TEXT,
                    result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    audio BLOB, audio_state TEXT NOT NULL DEFAULT 'pending',
                    callback_requested INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS phone_outbound (
                    id TEXT PRIMARY KEY, actor TEXT NOT NULL, recipient TEXT NOT NULL,
                    message TEXT NOT NULL, purpose TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending_approval', created REAL NOT NULL,
                    expires REAL NOT NULL, approved REAL, call_sid TEXT, error TEXT NOT NULL DEFAULT '',
                    audio BLOB, reply TEXT NOT NULL DEFAULT '', callback_job TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS phone_bridge_health (
                    id INTEGER PRIMARY KEY CHECK(id=1), seen REAL NOT NULL, version TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS phone_jobs_actor ON phone_jobs(actor, created);
                CREATE TABLE IF NOT EXISTS phone_live_streams (
                    call_id TEXT PRIMARY KEY, ticket_hash TEXT NOT NULL,
                    created REAL NOT NULL, stream_id TEXT, state TEXT NOT NULL DEFAULT 'pending',
                    closed REAL, reason TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS phone_live_delegations (
                    call_id TEXT NOT NULL, delegation_id TEXT NOT NULL, job_id TEXT NOT NULL,
                    caller_text TEXT NOT NULL,
                    PRIMARY KEY(call_id, delegation_id));
                CREATE TABLE IF NOT EXISTS phone_job_updates (
                    job_id TEXT NOT NULL, event_id TEXT NOT NULL, kind TEXT NOT NULL,
                    tool TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
                    duration_ms INTEGER NOT NULL DEFAULT 0, content TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL, PRIMARY KEY(job_id, event_id));
                CREATE TABLE IF NOT EXISTS phone_notices (
                    job_id TEXT PRIMARY KEY, actor TEXT NOT NULL, kind TEXT NOT NULL,
                    content TEXT NOT NULL, created REAL NOT NULL,
                    heard_at REAL, heard_call TEXT, followup_id TEXT);
                CREATE TABLE IF NOT EXISTS phone_voice_context (
                    actor TEXT PRIMARY KEY, user_id TEXT NOT NULL, packet TEXT NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS phone_conversations (
                    call_id TEXT PRIMARY KEY, actor TEXT NOT NULL, payload TEXT NOT NULL,
                    created REAL NOT NULL, archived REAL);
                CREATE TABLE IF NOT EXISTS phone_trace (
                    call_id TEXT NOT NULL, sequence INTEGER NOT NULL, kind TEXT NOT NULL,
                    turn_id TEXT, topic_id TEXT, response_id TEXT, task_id TEXT,
                    offset_ms INTEGER NOT NULL, duration_ms INTEGER NOT NULL, status TEXT,
                    created REAL NOT NULL, PRIMARY KEY(call_id,sequence));
            """)
            # Additive migration: existing accepted work and receipts stay intact.
            for table, columns in {
                'phone_calls': {'ended': 'REAL'},
                'phone_live_streams': {'last_seen': 'REAL'},
                'phone_jobs': {'root_id': 'TEXT', 'parent_id': 'TEXT', 'question': "TEXT NOT NULL DEFAULT ''",
                               'resume_job': 'TEXT', 'followup_allowed': 'INTEGER NOT NULL DEFAULT 0',
                               'origin_turn_id': "TEXT NOT NULL DEFAULT ''", 'origin_topic_id': "TEXT NOT NULL DEFAULT ''",
                               'logical_request_id': 'TEXT', 'idempotency_key': 'TEXT',
                               'authorization': "TEXT NOT NULL DEFAULT '{}'", 'plan': "TEXT NOT NULL DEFAULT '{}'",
                               'execution_class': "TEXT NOT NULL DEFAULT 'background_action'",
                               'notify_policy': "TEXT NOT NULL DEFAULT 'natural_when_relevant'",
                               'priority': 'INTEGER NOT NULL DEFAULT 60', 'cancel_requested': 'REAL'},
            }.items():
                present = {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
                for name, definition in columns.items():
                    if name not in present:
                        db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS phone_job_effect ON phone_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL')
            for name, definition in {
                'batch_id': 'TEXT', 'resource_key': "TEXT NOT NULL DEFAULT 'global'",
                'depends_on': "TEXT NOT NULL DEFAULT '[]'", 'plan_lease': 'REAL',
                'plan_attempts': 'INTEGER NOT NULL DEFAULT 0',
            }.items():
                if name not in {r['name'] for r in db.execute('PRAGMA table_info(phone_jobs)')}:
                    db.execute('ALTER TABLE phone_jobs ADD COLUMN '+name+' '+definition)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=2000")
            with db:
                yield db
        finally:
            db.close()

    def claim(self, lane='any'):
        import secrets
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # Claimed/started work is not replayed after a missing heartbeat.
            # The native worker retains an operation receipt and reconciles it.
            row = db.execute("""SELECT * FROM phone_jobs j WHERE state='queued' AND cancel_requested IS NULL
                AND (?='any' OR (execution_class='foreground_read')=?)
                AND NOT EXISTS (SELECT 1 FROM phone_jobs a WHERE a.actor=j.actor
                  AND a.state IN ('claimed','running') AND (?='any' OR (a.execution_class='foreground_read')=?)
                  AND (a.resource_key='global' OR j.resource_key='global' OR a.resource_key=j.resource_key))
                AND NOT EXISTS (SELECT 1 FROM json_each(j.depends_on) dep
                  WHERE NOT EXISTS (SELECT 1 FROM phone_jobs p WHERE
                    COALESCE(p.root_id,p.id)=dep.value AND p.state='completed'))
                ORDER BY priority DESC,created LIMIT 1""",(lane,lane=='read',lane,lane=='read')).fetchone()
            if not row:
                return None
            claim = secrets.token_urlsafe(24)
            db.execute("UPDATE phone_jobs SET state='claimed',claim=?,updated=? WHERE id=?", (claim, now, row['id']))
            db.execute('INSERT OR IGNORE INTO phone_job_updates VALUES (?,?,?,?,?,?,?,?)',
                       (row['id'], 'claimed', 'timing', '', 'claimed', int((now-row['created'])*1000), '', now))
            return {**dict(row), 'claim': claim, 'state': 'claimed', 'audio': None}

    def cancel(self, actor, job_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM phone_jobs WHERE id=? AND actor=?',(job_id,actor)).fetchone()
            if not row:raise ValueError('Unknown task')
            if row['state']=='resumed' and row['resume_job']:
                job_id=row['resume_job'];row=db.execute('SELECT * FROM phone_jobs WHERE id=? AND actor=?',(job_id,actor)).fetchone()
            if row['state']=='expanded':
                children=db.execute('SELECT id,state FROM phone_jobs WHERE batch_id=?',(job_id,)).fetchall()
                for child in children:
                    if child['state'] in {'queued','claimed','waiting_for_input'}:
                        db.execute("UPDATE phone_jobs SET state='cancelled',cancel_requested=?,updated=? WHERE id=?",(time.time(),time.time(),child['id']))
                    elif child['state']=='running':
                        db.execute('UPDATE phone_jobs SET cancel_requested=? WHERE id=?',(time.time(),child['id']))
                return {'task_id':job_id,'state':'cancel_requested','effect_cancelled':False}
            if row['state'] in {'queued','claimed','waiting_for_input','planning'}:
                db.execute("UPDATE phone_jobs SET state='cancelled',cancel_requested=?,callback_requested=0,updated=? WHERE id=?",(time.time(),time.time(),job_id))
                db.execute('UPDATE phone_notices SET heard_at=COALESCE(heard_at,?) WHERE job_id=?',(time.time(),job_id))
                return {'task_id':job_id,'state':'cancelled','effect_cancelled':True}
            if row['state']=='running':
                db.execute('UPDATE phone_jobs SET cancel_requested=?,callback_requested=0 WHERE id=?',(time.time(),job_id))
                return {'task_id':job_id,'state':'cancel_requested','effect_cancelled':False}
            return {'task_id':job_id,'state':row['state'],'effect_cancelled':row['state']=='cancelled'}

    def jobs(self, actor: str):
        with self.db() as db:
            jobs = [dict(r) for r in db.execute("""SELECT j.id,COALESCE(d.caller_text,j.transcript) AS transcript,
                j.state,j.created,j.updated,j.result,j.error,j.callback_requested,j.question,j.resume_job,j.parent_id,j.cancel_requested FROM phone_jobs j
                LEFT JOIN phone_live_delegations d ON d.job_id=j.id
                WHERE j.actor=? AND j.state!='expanded' AND NOT (j.execution_class='intake' AND j.state='completed')
                ORDER BY CASE WHEN j.state='waiting_for_input' THEN 0 ELSE 1 END,j.created DESC LIMIT 100""", (actor,))]
            for job in jobs:
                job['actions'] = [dict(r) for r in db.execute("SELECT event_id,status,content FROM phone_job_updates WHERE job_id=? AND kind='action' ORDER BY created,event_id", (job['id'],))]
        return jobs

    def questions(self, actor, call_id=None):
        with self.db() as db:
            return [dict(r) for r in db.execute("""SELECT id,question,root_id,call_id FROM phone_jobs
                WHERE actor=? AND state='waiting_for_input' AND (? IS NULL OR call_id=?)
                ORDER BY created LIMIT 32""", (actor,call_id,call_id))]

    def notices(self, actor, call_id='', *, current_only=False):
        with self.db() as db:
            return [dict(r) for r in db.execute("""SELECT n.*,j.call_id AS source_call,j.created AS requested_at,j.state,j.notify_policy,
                COALESCE(d.caller_text,j.transcript) AS request FROM phone_notices n JOIN phone_jobs j ON j.id=n.job_id
                LEFT JOIN phone_live_delegations d ON d.job_id=j.id
                WHERE n.actor=? AND (n.heard_at IS NULL OR (n.kind='question' AND COALESCE(n.heard_call,'')!=?))
                AND (?='' OR j.call_id=? OR n.followup_id=(SELECT outbound_id FROM phone_calls WHERE id=?))
                AND j.state IN ('completed','waiting_for_input','failed','uncertain')
                ORDER BY CASE WHEN n.kind='question' THEN 0 ELSE 1 END,n.created LIMIT 32""", (actor,call_id,call_id if current_only else '',call_id,call_id))]

    def heard(self, job_id, actor, call_id):
        with self.db() as db:
            db.execute('UPDATE phone_notices SET heard_at=?,heard_call=? WHERE job_id=? AND actor=? AND heard_at IS NULL',
                       (time.time(),call_id,job_id,actor))

    def resume(self, actor, request_id, answer, call_id, *, source_job=None):
        """Consume one answer atomically. A retry returns the same continuation.

        Operation receipts use root_id across continuations, so completing a
        missing detail never repeats an already-confirmed part of the task.
        """
        import secrets
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM phone_jobs WHERE id=? AND actor=?',(request_id,actor)).fetchone()
            if not row:
                raise ValueError('Unknown clarification')
            if row['resume_job']:
                return row['resume_job']
            if row['state'] != 'waiting_for_input':
                raise ValueError('This task is not waiting for an answer')
            original = row['transcript'].rsplit('New caller speech: ',1)[-1]
            if len(original)+len(answer)>6000:
                raise ValueError('Please restate the complete request as a new task; this clarification history is too long')
            transcript = ('Resume this existing phone task using the same Eli memory and permissions. '
                          'Do not repeat any previously confirmed action. The answer applies only to the question below. '
                          'If it is insufficient, ask again; never fill missing details by guessing.\n'
                          'Question that was asked: '+row['question']+'\n'
                          'The following combines the original caller words and their clarification verbatim.\n'
                          'New caller speech: '+original+'\n'+answer)
            identifier, now = secrets.token_hex(16), time.time()
            db.execute("""INSERT INTO phone_jobs(id,actor,call_id,transcript,created,updated,audio_state,root_id,parent_id,followup_allowed,callback_requested)
                VALUES (?,?,?,?,?,?,'live',?,?,?,?)""",
                (identifier,actor,call_id,transcript,now,now,row['root_id'] or row['id'],row['id'],0,row['callback_requested']))
            db.execute('INSERT INTO phone_live_delegations VALUES (?,?,?,?)',
                       (call_id,'continuation:'+identifier,identifier,original+'\n'+answer))
            auth=json.loads(row['authorization'] or '{}')
            auth.update(clarification_actor=actor,clarification_time=now,source_job=source_job)
            db.execute('''UPDATE phone_jobs SET origin_turn_id=?,origin_topic_id=?,logical_request_id=?,idempotency_key=?,
                authorization=?,notify_policy=? WHERE id=?''',
                (row['origin_turn_id'],row['origin_topic_id'],row['logical_request_id'] or row['id'],
                 'continuation:'+row['id'],json.dumps(auth),row['notify_policy'],identifier))
            db.execute('UPDATE phone_jobs SET batch_id=?,resource_key=?,depends_on=?,plan=? WHERE id=?',
                       (row['batch_id'],row['resource_key'],row['depends_on'],row['plan'],identifier))
            if row['execution_class']=='intake':
                db.execute("UPDATE phone_jobs SET state='planning',execution_class='intake' WHERE id=?",(identifier,))
            db.execute("UPDATE phone_jobs SET state='resumed',resume_job=?,updated=? WHERE id=?",(identifier,now,row['id']))
            db.execute('UPDATE phone_notices SET heard_at=COALESCE(heard_at,?),heard_call=COALESCE(heard_call,?) WHERE job_id=?',(now,call_id,row['id']))
            if source_job:
                db.execute('INSERT OR IGNORE INTO phone_job_updates VALUES (?,?,?,?,?,?,?,?)',
                           (source_job,'resume:'+request_id,'timing','clarification','resumed',0,'',now))
            return identifier

    def updates(self, job_id: str):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM phone_job_updates WHERE job_id=? ORDER BY created,event_id', (job_id,))]

    def outbound(self, actor: str):
        with self.db() as db:
            return [dict(r) for r in db.execute("""SELECT id,recipient,message,purpose,payload_hash,state,
                created,expires,call_sid,error,reply FROM phone_outbound WHERE actor=? ORDER BY created DESC LIMIT 30""", (actor,))]
