"""Authenticated text ingress into the same durable task ledger as voice."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from types import SimpleNamespace
from contextlib import contextmanager

CHANNELS={'whatsapp','telegram','photon','bluebubbles'}
ACTION=re.compile(r'\b(?:send|email|text|draft|write|research|find|search|check|schedule|book|reschedule|create|prepare|save|remember|remind|cancel|change|modify|prioritize|reprioritize|actually|instead|never mind|forget|wait|approve)\b',re.I)
ANSWER=re.compile(r'^\s*(?:yes|no|correct|go ahead|send it|just send it|the (?:email|text|invite)|tomorrow|today|at \d)',re.I)
_ready=False


def path():
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())/'state/eli-phone.sqlite3'


@contextmanager
def connect(filename):
    db=sqlite3.connect(filename,timeout=3);db.row_factory=sqlite3.Row
    db.executescript('''CREATE TABLE IF NOT EXISTS task_ingress(
        id TEXT PRIMARY KEY,payload TEXT NOT NULL,source TEXT NOT NULL,state TEXT NOT NULL,
        intake_id TEXT,call_id TEXT,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS task_text_notices(
        id TEXT PRIMARY KEY,state TEXT NOT NULL,content TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS task_question_actors(
        actor TEXT PRIMARY KEY,waiting INTEGER NOT NULL,updated REAL NOT NULL);''')
    try:
        with db:yield db
    finally:db.close()


def hook(settings,event=None,gateway=None,**kwargs):
    if not _ready or not settings.get('task_ledger_text_enabled',True) or not event or not gateway:return None
    source=event.source
    platform=getattr(source.platform,'value',str(source.platform))
    if platform not in CHANNELS or source.chat_type!='dm' or not getattr(source,'user_id',None):return None
    # This hook runs before core auth, so explicitly repeat the same gateway check.
    if gateway._is_user_authorized(source) is not True:return None
    actor=next((a for a,c in settings.get('identities',{}).items() if c.get('user_id')==source.user_id),None)
    text=getattr(event,'text','') or ''
    if not actor or not text or len(text)>6000 or text.startswith('/'):return None
    with connect(path()) as db:
        pending=db.execute('SELECT waiting FROM task_question_actors WHERE actor=?',(actor,)).fetchone()
    if not (ACTION.search(text) or ANSWER.search(text) or (pending and pending['waiting'])):return None
    if re.fullmatch(r'\s*(?:hello|hi|thanks|thank you|goodbye)[.!\s]*',text,re.I):return None
    if re.match(r'^\s*(?:how (?:do|can|would)|what (?:is|are)|can you (?:send|email|text) (?:people|messages|emails))\b',text,re.I):return None
    message_id=str(getattr(event,'message_id','') or getattr(source,'message_id',''))
    if not message_id:return None  # Never invent a transport idempotency key.
    payload={'actor':actor,'user_id':source.user_id,'platform':platform,'conversation_id':str(source.chat_id),
             'message_id':message_id,'text':text}
    identifier=hashlib.sha256((actor+platform+str(source.chat_id)+message_id).encode()).hexdigest()
    saved={'platform':platform,'chat_id':source.chat_id,'user_id':source.user_id,'user_name':getattr(source,'user_name',''),
        'chat_type':'dm','profile':getattr(source,'profile',None),'thread_id':getattr(source,'thread_id',None)}
    with connect(path()) as db:
        db.execute("INSERT OR IGNORE INTO task_ingress VALUES (?,?,?,'pending',NULL,NULL,?)",
            (identifier,json.dumps(payload),json.dumps(saved),time.time()))
    return {'action':'skip','reason':'Saved to the shared task ledger ingress; the native task worker owns execution.'}


def ready(filename):
    with connect(filename) as db:
        return [dict(r) for r in db.execute("SELECT * FROM task_ingress WHERE state!='closed' ORDER BY created LIMIT 30")]


async def pump(adapter,api):
    global _ready
    filename=adapter.journal.path
    question_refresh=0
    while adapter._running:
        try:
            if not _ready:
                capability=await asyncio.to_thread(api,'/internal/tasks/capabilities',{})
                _ready=capability.get('ledger_version')==1 and capability.get('text_ingress') is True
                if not _ready:await asyncio.sleep(5);continue
            gateway=getattr(adapter._message_handler,'__self__',None)
            if gateway is None:await asyncio.sleep(1);continue
            if time.monotonic()-question_refresh>5:
                from . import configuration
                for actor in configuration().get('identities',{}):
                    snapshot=await asyncio.to_thread(api,'/internal/tasks/state',{'actor':actor})
                    with connect(filename) as db:db.execute('INSERT OR REPLACE INTO task_question_actors VALUES (?,?,?)',
                        (actor,int(bool(snapshot.get('questions'))),time.time()))
                question_refresh=time.monotonic()
            for item in await asyncio.to_thread(ready,filename):
                payload=json.loads(item['payload']);saved=json.loads(item['source'])
                from gateway.config import Platform
                source=SimpleNamespace(**{**saved,'platform':Platform(saved['platform'])})
                if gateway._is_user_authorized(source) is not True:continue
                target=gateway._adapter_for_source(source)
                if not target:continue
                if item['state']=='pending':
                    result=await asyncio.to_thread(api,'/internal/tasks/utterance',payload)
                    with connect(filename) as db:db.execute("UPDATE task_ingress SET state='accepted',intake_id=?,call_id=? WHERE id=?",
                        (result['intake_id'],result['call_id'],item['id']))
                    item.update(state='accepted',intake_id=result['intake_id'],call_id=result['call_id'])
                # Intake/control results are durable notices too; they are returned
                # separately because a cancellation need not create a new task.
                notices=await asyncio.to_thread(api,'/internal/tasks/notices',{'actor':payload['actor'],'intake_id':item['intake_id']})
                for notice in notices['notices']:
                    key=hashlib.sha256((item['id']+notice['id']+notice['state']+notice['content']).encode()).hexdigest()
                    with connect(filename) as db:
                        old=db.execute('SELECT 1 FROM task_text_notices WHERE id=?',(key,)).fetchone()
                        if old:continue
                        db.execute("INSERT INTO task_text_notices VALUES (?,'attempted',?,?)",(key,notice['content'],time.time()))
                    # An unknown transport outcome never causes repeated messages.
                    sent=await target.send(source.chat_id,notice['content'],metadata={'thread_id':source.thread_id})
                    with connect(filename) as db:db.execute('UPDATE task_text_notices SET state=? WHERE id=?',
                        ('sent' if getattr(sent,'success',False) else 'uncertain',key))
                if notices.get('settled'):
                    with connect(filename) as db:db.execute("UPDATE task_ingress SET state='closed' WHERE id=?",(item['id'],))
        except asyncio.CancelledError:raise
        except Exception:
            import logging
            logging.getLogger('eli.phone').warning('Shared text task synchronization deferred; durable work retained')
        await asyncio.sleep(1)
