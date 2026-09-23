"""Authenticated text ingress into the same durable task ledger as voice."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from contextlib import contextmanager

CHANNELS={'whatsapp','telegram','photon','bluebubbles'}
ACTION=re.compile(r'\b(?:send|email|text|draft|write|research|find|search|check|schedule|book|reschedule|create|prepare|save|remember|remind|cancel|change|modify|prioritize|reprioritize|actually|instead|never mind|forget|wait|approve)\b',re.I)
SOCIAL=re.compile(r'^\s*(?:(?:hi|hey|hello+|thanks|thank you|goodbye|bye)\b|(?:who|what|when|where|why|how|are|is|do|does|can|could)\b)',re.I)
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
        actor TEXT PRIMARY KEY,waiting INTEGER NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS task_text_questions(
        actor TEXT NOT NULL,platform TEXT NOT NULL,chat_id TEXT NOT NULL,
        question_id TEXT NOT NULL,created REAL NOT NULL,
        PRIMARY KEY(actor,platform,chat_id,question_id));''')
    columns={r['name'] for r in db.execute('PRAGMA table_info(task_ingress)')}
    for name,definition in [('attempts','INTEGER NOT NULL DEFAULT 0'),('next_attempt','REAL NOT NULL DEFAULT 0'),('error',"TEXT NOT NULL DEFAULT ''")]:
        if name not in columns:db.execute('ALTER TABLE task_ingress ADD COLUMN '+name+' '+definition)
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
    if re.match(r'^\s*(?:how (?:do|can|would)|what (?:is|are)|can you (?:send|email|text) (?:people|messages|emails))\b',text,re.I):return None
    if not ACTION.search(text):
        # Old voice questions do not own this text conversation. Only a question
        # successfully delivered HERE can make free-form speech a task answer.
        if SOCIAL.search(text) or not re.search(r'\w',text):return None
        with connect(path()) as db:
            pending=db.execute('SELECT 1 FROM task_text_questions WHERE actor=? AND platform=? AND chat_id=? LIMIT 1',
                               (actor,platform,str(source.chat_id))).fetchone()
        if not pending:return None
    message_id=str(getattr(event,'message_id','') or getattr(source,'message_id',''))
    if not message_id:return None  # Never invent a transport idempotency key.
    payload={'actor':actor,'user_id':source.user_id,'platform':platform,'conversation_id':str(source.chat_id),
             'message_id':message_id,'text':text}
    identifier=hashlib.sha256((actor+platform+str(source.chat_id)+message_id).encode()).hexdigest()
    saved={'platform':platform,'chat_id':source.chat_id,'user_id':source.user_id,'user_name':getattr(source,'user_name',''),
        'chat_type':'dm','profile':getattr(source,'profile',None),'thread_id':getattr(source,'thread_id',None)}
    with connect(path()) as db:
        db.execute("INSERT OR IGNORE INTO task_ingress(id,payload,source,state,intake_id,call_id,created) VALUES (?,?,?,'pending',NULL,NULL,?)",
            (identifier,json.dumps(payload),json.dumps(saved),time.time()))
    return {'action':'skip','reason':'Saved to the shared task ledger ingress; the native task worker owns execution.'}


def ready(filename):
    with connect(filename) as db:
        return [dict(r) for r in db.execute("SELECT * FROM task_ingress WHERE state IN ('pending','accepted') AND next_attempt<=? ORDER BY next_attempt,created LIMIT 30",(time.time(),))]


def restore_source(saved):
    from gateway.session import SessionSource
    # Includes native defaults required by auth, and deliberately does not restore
    # upstream-relay trust from persisted data. Never weaken the gateway check.
    return SessionSource.from_dict(saved)


def defer(filename,item,exc):
    attempts=item.get('attempts',0)+1
    detail=type(exc).__name__
    if isinstance(getattr(exc,'code',None),int):detail+=':'+str(exc.code)
    with connect(filename) as db:
        db.execute('UPDATE task_ingress SET attempts=?,next_attempt=?,error=? WHERE id=?',
                   (attempts,time.time()+min(60,2**min(attempts,6)),detail,item['id']))
    import logging
    logging.getLogger('eli.phone').warning('Shared text item %s deferred (%s); attempt=%d',item['id'][:12],detail,attempts)


async def process_item(adapter,api,gateway,item):
    filename=adapter.journal.path
    payload=json.loads(item['payload']);saved=json.loads(item['source'])
    source=restore_source(saved)
    if gateway._is_user_authorized(source) is not True:
        with connect(filename) as db:db.execute("UPDATE task_ingress SET state='blocked',error='authorization_revoked' WHERE id=?",(item['id'],))
        return
    target=gateway._adapter_for_source(source)
    if not target:raise ConnectionError('Message transport unavailable')
    if item['state']=='pending':
        result=await asyncio.to_thread(api,'/internal/tasks/utterance',payload)
        with connect(filename) as db:db.execute("UPDATE task_ingress SET state='accepted',intake_id=?,call_id=?,attempts=0,next_attempt=0,error='' WHERE id=?",
            (result['intake_id'],result['call_id'],item['id']))
        item.update(state='accepted',intake_id=result['intake_id'],call_id=result['call_id'])
    notices=await asyncio.to_thread(api,'/internal/tasks/notices',{'actor':payload['actor'],'intake_id':item['intake_id']})
    for notice in notices['notices']:
        key=hashlib.sha256((item['id']+notice['id']+notice['state']+notice['content']).encode()).hexdigest()
        with connect(filename) as db:
            old=db.execute('SELECT 1 FROM task_text_notices WHERE id=?',(key,)).fetchone()
            if old:continue
            db.execute("INSERT INTO task_text_notices VALUES (?,'attempted',?,?)",(key,notice['content'],time.time()))
        # An unknown transport outcome never causes repeated messages.
        try:sent=await target.send(source.chat_id,notice['content'],metadata={'thread_id':source.thread_id})
        except Exception:
            with connect(filename) as db:db.execute("UPDATE task_text_notices SET state='uncertain' WHERE id=?",(key,))
            raise
        with connect(filename) as db:
            db.execute('UPDATE task_text_notices SET state=? WHERE id=?',('sent' if getattr(sent,'success',False) else 'uncertain',key))
            if getattr(sent,'success',False) and notice['state']=='waiting_for_input':
                db.execute('INSERT OR IGNORE INTO task_text_questions VALUES (?,?,?,?,?)',
                           (payload['actor'],payload['platform'],str(source.chat_id),notice['id'],time.time()))
    with connect(filename) as db:
        db.execute("UPDATE task_ingress SET attempts=0,next_attempt=0,error='' WHERE id=?",(item['id'],))
        if notices.get('settled'):db.execute("UPDATE task_ingress SET state='closed' WHERE id=?",(item['id'],))


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
                with connect(filename) as db:actors=[r[0] for r in db.execute('SELECT DISTINCT actor FROM task_text_questions')]
                for actor in actors:
                    try:
                        snapshot=await asyncio.to_thread(api,'/internal/tasks/state',{'actor':actor})
                        active={q['id'] for q in snapshot.get('questions',[])}
                        with connect(filename) as db:
                            for row in db.execute('SELECT question_id FROM task_text_questions WHERE actor=?',(actor,)).fetchall():
                                if row['question_id'] not in active:db.execute('DELETE FROM task_text_questions WHERE actor=? AND question_id=?',(actor,row['question_id']))
                    except asyncio.CancelledError:raise
                    except Exception as exc:
                        import logging
                        logging.getLogger('eli.phone').warning('Text question refresh deferred (%s)',type(exc).__name__)
                question_refresh=time.monotonic()
            for item in await asyncio.to_thread(ready,filename):
                try:await process_item(adapter,api,gateway,item)
                except asyncio.CancelledError:raise
                except Exception as exc:defer(filename,item,exc)
        except asyncio.CancelledError:raise
        except Exception as exc:
            import logging
            logging.getLogger('eli.phone').warning('Shared text synchronization deferred (%s); durable work retained',type(exc).__name__)
        await asyncio.sleep(1)
