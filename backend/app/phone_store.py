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
            """)

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

    def claim(self):
        import secrets
        now = time.time()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # Claimed/started work is not replayed after a missing heartbeat.
            # The native worker retains an operation receipt and reconciles it.
            row = db.execute("""SELECT * FROM phone_jobs j WHERE state='queued'
                AND NOT EXISTS (SELECT 1 FROM phone_jobs a WHERE a.actor=j.actor
                  AND a.state IN ('claimed','running','uncertain')) ORDER BY created LIMIT 1""").fetchone()
            if not row:
                return None
            claim = secrets.token_urlsafe(24)
            db.execute("UPDATE phone_jobs SET state='claimed',claim=?,updated=? WHERE id=?", (claim, now, row['id']))
            db.execute('INSERT OR IGNORE INTO phone_job_updates VALUES (?,?,?,?,?,?,?,?)',
                       (row['id'], 'claimed', 'timing', '', 'claimed', int((now-row['created'])*1000), '', now))
            return {**dict(row), 'claim': claim, 'state': 'claimed', 'audio': None}

    def jobs(self, actor: str):
        with self.db() as db:
            jobs = [dict(r) for r in db.execute("""SELECT j.id,COALESCE(d.caller_text,j.transcript) AS transcript,
                j.state,j.created,j.updated,j.result,j.error,j.callback_requested FROM phone_jobs j
                LEFT JOIN phone_live_delegations d ON d.job_id=j.id
                WHERE j.actor=? ORDER BY j.created DESC LIMIT 30""", (actor,))]
            for job in jobs:
                job['actions'] = [dict(r) for r in db.execute("SELECT event_id,status,content FROM phone_job_updates WHERE job_id=? AND kind='action' ORDER BY created,event_id", (job['id'],))]
            return jobs

    def updates(self, job_id: str):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM phone_job_updates WHERE job_id=? ORDER BY created,event_id', (job_id,))]

    def outbound(self, actor: str):
        with self.db() as db:
            return [dict(r) for r in db.execute("""SELECT id,recipient,message,purpose,payload_hash,state,
                created,expires,call_sid,error,reply FROM phone_outbound WHERE actor=? ORDER BY created DESC LIMIT 30""", (actor,))]
