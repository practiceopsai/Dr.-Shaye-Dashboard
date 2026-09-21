"""Phone-only timing, durable progress, and bounded operational feedback.

Never stores tool arguments/results in telemetry. Observations cannot change
permissions, channel choice, or approval rules, and never retry an action.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


class Performance:
    def __init__(self, path):
        self.path = path
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS execution_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                kind TEXT NOT NULL, tool TEXT NOT NULL, status TEXT NOT NULL,
                duration_ms INTEGER NOT NULL, content TEXT NOT NULL,
                fingerprint TEXT NOT NULL, created REAL NOT NULL, delivered INTEGER DEFAULT 0)''')
            db.execute('CREATE INDEX IF NOT EXISTS execution_job ON execution_events(job_id,id)')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, job, kind, tool='', status='', duration_ms=0, content='', fingerprint=''):
        with self.db() as db:
            db.execute('INSERT INTO execution_events(job_id,kind,tool,status,duration_ms,content,fingerprint,created) VALUES (?,?,?,?,?,?,?,?)',
                       (job,kind,tool,status,max(0,min(int(duration_ms),86400000)),content[:500],fingerprint,time.time()))

    def pending(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM execution_events WHERE delivered=0 ORDER BY id LIMIT 30')]

    def delivered(self, identifiers):
        with self.db() as db:
            db.executemany('UPDATE execution_events SET delivered=1 WHERE id=?', [(i,) for i in identifiers])

    def failed_attempt(self, job, fingerprint):
        with self.db() as db:
            return bool(db.execute("SELECT 1 FROM execution_events WHERE job_id=? AND fingerprint=? AND status IN ('failed','uncertain') LIMIT 1", (job,fingerprint)).fetchone())

    def feedback(self):
        with self.db() as db:
            rows = db.execute("""SELECT tool, count(*) AS attempts,
                sum(status IN ('failed','uncertain')) AS failures,
                sum(duration_ms>5000) AS slow, cast(avg(duration_ms) AS INTEGER) AS mean_ms
                FROM (SELECT * FROM execution_events WHERE kind='timing' AND tool!='' ORDER BY id DESC LIMIT 100)
                GROUP BY tool HAVING failures>0 OR slow>0 ORDER BY failures DESC,slow DESC LIMIT 5""").fetchall()
        return [dict(r) for r in rows]


def current(settings, *, home=None, session=None):
    if session is None:
        from gateway.session_context import get_session_env
        session = get_session_env
    if home is None:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
    if session('HERMES_SESSION_PLATFORM','') != 'eli_phone' or session('HERMES_SESSION_CHAT_TYPE','') != 'dm':
        return None
    identifier = session('HERMES_SESSION_MESSAGE_ID','')
    user = session('HERMES_SESSION_USER_ID','')
    path = Path(home)/'state/eli-phone.sqlite3'
    if not path.exists() or not identifier:
        return None
    perf = Performance(path)
    with perf.db() as db:
        row = db.execute('SELECT payload,state FROM work WHERE id=?', (identifier,)).fetchone()
    if not row or row['state'] != 'running':
        return None
    job = json.loads(row['payload'])
    identity = settings.get('identities',{}).get(job.get('actor'))
    if not identity or identity != job.get('identity') or identity.get('user_id') != user:
        return None
    fresh = job.get('transcript','').rsplit('New caller speech: ',1)[-1]
    return perf, job, fresh


def fingerprint(tool, args):
    return hashlib.sha256((tool+'\0'+json.dumps(args,sort_keys=True,default=str)).encode()).hexdigest()


def simple_request(text):
    text = text.casefold()
    return bool((re.search(r'\b(latest|most recent|newest)\b',text) and re.search(r'\b(email|inbox|mail)\b',text))
                or (re.search(r'\b(send|text)\b',text) and re.search(r'\b(saying|say|hello|hi|message)\b',text)))


def before_tool(settings, tool_name='', args=None, **kwargs):
    active = current(settings)
    if not active:
        return None
    perf, job, fresh = active
    from . import effects
    if len(job.get('claim',''))>=20:
        # Fail closed for effects if cancellation state cannot be checked.
        from . import api_control
        try:control=api_control(job)
        except Exception:
            if effects.mutation(tool_name,args or {}) or tool_name.startswith('eli_phone_send_'):
                return {'block':True,'message':'Task control is unavailable; no new effect may start. Preserve existing receipts.'}
            control={}
        if control.get('cancel_requested') or control.get('state')=='cancelled':
            perf.record(job['id'],'timing','cancellation','cancel_requested')
            return {'block':True,'message':'The caller cancelled this task. Stop starting tools. Already accepted effects may have completed; report their existing receipts honestly.'}
    from .clarification import question_for
    if question_for(perf,job['id']) and tool_name not in {'eli_phone_clarify','eli_context'}:
        return {'block':True,'message':'This task is waiting for the caller answer. Return the saved question now; do not execute more work.'}
    fp = fingerprint(tool_name,args or {})
    if perf.failed_attempt(job['id'],fp):
        return {'block': True, 'message': 'This exact tool attempt already failed or has an uncertain outcome in this request. Report the existing result; do not retry or choose another channel.'}
    if simple_request(fresh) and tool_name in {'search_files','computer_use'}:
        perf.record(job['id'],'timing',tool_name,'blocked',fingerprint=fp)
        return {'block': True, 'message': 'Use the prepared phone messaging/email tools for this simple request. Do not search the computer for a transport. If unavailable, return the specific blocker now.'}
    if tool_name in {'eli_phone_latest_email','email_list_threads','email_get_thread','email_get_message'}:
        content = "I'm checking the selected inbox."
    elif tool_name in {'eli_phone_send_email','email_send','eli_phone_send_whatsapp','eli_phone_send_imessage'}:
        content = "I'm checking that message request and waiting for the sending service to confirm it."
    else:
        content = ''
    if content:
        perf.record(job['id'],'progress',tool_name,'running',content=content)
    return effects.begin(perf,job,tool_name,args or {})


def after_tool(settings, tool_name='', args=None, result=None, duration_ms=0, status='', **kwargs):
    active = current(settings)
    if not active:
        return
    perf, job, _ = active
    try:
        data = json.loads(result) if isinstance(result,str) else result
    except (ValueError,TypeError):
        data = {}
    data = data if isinstance(data,dict) else {}
    from . import effects
    effects.finish(perf,job,tool_name,args or {},data,status)
    if effects.mutation(tool_name,args or {}) and status!='blocked':effects.reconcile(perf,job)
    failed = status in {'error','failed','blocked'} or data.get('success') is False or bool(data.get('error'))
    outcome = 'uncertain' if data.get('state') == 'uncertain' else 'failed' if failed else 'ok'
    perf.record(job['id'],'timing',tool_name,outcome,duration_ms,fingerprint=fingerprint(tool_name,args or {}))
    channels = {'eli_phone_send_whatsapp':'WhatsApp', 'eli_phone_send_imessage':'iMessage',
                'eli_phone_send_email':'email', 'email_send':'email'}
    if tool_name in channels:
        # Receipt, not model prose, is the authority. Never include message body,
        # recipient or provider diagnostics in spoken progress/telemetry.
        if data.get('success') is True and data.get('message_id'):
            verified=tool_name not in {'email_send','eli_phone_send_email'} or data.get('source_verified') is True
            receipt = hashlib.sha256(str(data['message_id']).encode()).hexdigest()
            with perf.db() as db:
                exists = db.execute("SELECT 1 FROM execution_events WHERE job_id=? AND kind='action' AND fingerprint=?", (job['id'],receipt)).fetchone()
            if not exists:
                perf.record(job['id'],'action',tool_name,'sent' if verified else 'accepted',content=
                    'The requested '+channels[tool_name]+(' message has a verified send receipt.' if verified else ' send was accepted; source verification is still required. Do not resend.'),fingerprint=receipt)
        elif failed:
            perf.record(job['id'],'action',tool_name,'failed',content='The '+channels[tool_name]+' send is not confirmed. '+
                        ('The iMessage connection must be restored; no other channel was used.' if data.get('state')=='unavailable' else 'I will not repeat an uncertain send.'))


def context(settings, schemas, **kwargs):
    active = current(settings)
    if not active:
        return None
    perf, job, fresh = active
    names = {actor:{'name':identity.get('name'),'phone':identity.get('phone')} for actor,identity in settings.get('identities',{}).items()}
    return {'context': 'Prepared phone operations: call tool_call(name, arguments) directly using these schemas; no tool_describe or skill catalog is needed for them. '
        'For latest email, identify the inbox: eli_phone_latest_email reads only Eli AgentMail. My email refers to the authenticated caller, not Eli; use existing personal/practice account routing or clarify. '
        'For a new simple email send, prefer eli_phone_send_email. Unqualified text means iMessage; WhatsApp requires the caller to name WhatsApp explicitly. '
        'Missing essential details require eli_phone_clarify(question) before ending this turn. Do not just put a question in a completed response. '
        'Do not invent message text, recipients, dates, accounts or approvals. When all details are explicit, execute without an extra permission round. '
        'If this caller turn clearly answers an open question below, use eli_phone_answer_clarification with its request_id and verbatim answer_quote. '
        'That creates the continuation; do not execute the resumed task again in this turn. If several questions could match, ask which task. '
        'Work silently. Do not narrate progress or promise immediate delivery. '
        'Use existing native memory and policy; these tool definitions grant no new permissions. Return a short factual result. '
        'The phone delivery scheduler holds results and questions for relevant breaks; otherwise they stay in the app. No automatic callback. '
        'Cancel exact pending tasks with eli_phone_cancel_task. Speech interruption is not action cancellation. '
        'Open clarification tasks: '+json.dumps(job.get('open_questions',[]))+'\n'
        'Earlier action receipts in this SAME task: '+json.dumps(job.get('prior_actions',[]))+'\n'
        'Other requests with uncertain outcomes (review them before any repeat): '+json.dumps(job.get('uncertain_requests',[]))+'\n'
        'Preserve confirmed parts of this task. Execute only what remains; never repeat an uncertain action. '
        'Recent voice delivery observations: '+json.dumps(job.get('delivery_feedback',[]))+'\n'
        'Configured contacts (email keys): '+json.dumps(names)+ '\nTool schemas: '+json.dumps(schemas)+
        '\nRecent measured phone tool problems (metadata only): '+json.dumps(perf.feedback())+
        '\nUse this feedback to avoid failed routes and unnecessary discovery; do not change security, approvals, PHI rules or retry uncertain writes.'}


def model_timing(settings, api_duration=0, failed=False, **kwargs):
    active = current(settings)
    if active:
        perf,job,_ = active
        perf.record(job['id'],'timing','model_round','failed' if failed else 'ok',int(float(api_duration or 0)*1000))


def verified_answer(perf, job, answer):
    from .effects import review
    effects=review(perf,job)
    pending=[r for r in effects if r['state']!='verified']
    if pending:
        confirmed=sum(r['state']=='verified' for r in effects)
        return ('Provider verification is still pending for '+str(len(pending))+' operation(s). '
                +(str(confirmed)+' other operation(s) have verified receipts. ' if confirmed else '')
                +'The existing attempts are saved; I will not repeat an uncertain action.')
    fresh = job.get('transcript','').rsplit('New caller speech: ',1)[-1]
    if not re.search(r'\b(send|text|email)\b',fresh,re.I):
        return answer
    with perf.db() as db:
        sent = {r['tool'] for r in db.execute("SELECT tool FROM execution_events WHERE job_id=? AND kind='action' AND status='sent'",(job['id'],))}
    sent.update(r['tool'] for r in job.get('prior_actions',[]) if r.get('status')=='sent')
    expected = set()
    if re.search(r'\be-?mail\b',fresh,re.I): expected.add('email')
    if re.search(r'\bwhats\s*app\b',fresh,re.I): expected.add('whatsapp')
    if re.search(r'\bimessage\b',fresh,re.I) or (re.search(r'\btext\b',fresh,re.I) and not re.search(r'\bwhats\s*app\b',fresh,re.I)): expected.add('imessage')
    confirmed = {'email' if name=='email_send' else name.removeprefix('eli_phone_send_') for name in sent}
    if re.search(r'\b(?:I(?:\s+have|\x27ve)?\s+(?:already\s+)?sent|already sent|message (?:was|has been) sent|email (?:was|has been) sent|(?:emailed|texted)\s+\w+)\b',answer,re.I) and (not sent or expected-confirmed):
        perf.record(job['id'],'timing','final_response','failed')
        if confirmed:
            return 'Confirmed sent for this request: '+', '.join(sorted(confirmed))+'. I do not have a confirmed send for '+', '.join(sorted(expected-confirmed))+'. Do not repeat any uncertain send.'
        return 'I do not have a fresh send confirmation for this request. It needs review before any message is repeated.'
    return answer


def transform_answer(settings, response_text=None, **kwargs):
    active = current(settings)
    answer = response_text
    if active and isinstance(answer,str):
        perf,job,_ = active
        verified = verified_answer(perf,job,answer)
        return verified if verified != answer else None
