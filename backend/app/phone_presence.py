"""Actor-scoped voice context and call records, separate from executable work."""
import json
import re
import time

from . import phone
from .security import contains_phi

PRIVATE = re.compile(r'(?i)\b(?:sk[_-][a-z0-9_-]{16,}|Bearer\s+\S{8,}|password\s*[:=]|totp[_ ]?secret)')


def automated_audio(text):
    return bool(re.search(r'(?:call has been forwarded|forwarded to voicemail|at the tone.{0,30}record|person you.re trying to reach is not available)', text, re.I))


def stop_calls(text):
    return bool(re.search(r'\b(?:stop calling(?: me)?|do not call me|don.t call me|no more calls)\b', text, re.I))


def known_question(text):
    """Narrow repair for an unnecessary model delegation; not a general classifier."""
    return bool(re.search(r'\b(?:what (?:ai )?model|what.s your name|what is your name|who are you|who (?:do you|you) work for|what (?:is your job|can you do)|who(?:.s| is| are).*\bteam|who am i|what.s my name)\b', text, re.I)) and not work_requested(text)


def work_requested(text):
    # Only a hangup safety net. The live model decides actual delegation intent.
    text = re.sub(r'\b(?:can|could|are) you (?:able to )?(?:send|call|text|email|check|schedule) (?:people|messages|emails|other people)\??', '', text, flags=re.I)
    if re.match(r'^\s*(?:okay[, .]+)?(?:how (?:do|can|would|should) (?:i|you)|what (?:is|are) (?:an? |the )?(?:email|text|calendar))\b',text,re.I):
        return False
    verbs=bool(re.search(r'\b(?:send|draft|write|add|move|remove|put|set|note|save|remember|remind|schedule|book|cancel|reschedule|delete|update|change|revise|shorten|prepare|create|make|check|look up|find|search|call me back|call (?!yourself)|approve)\b', text, re.I))
    message=bool(re.search(r'(?:^|[.!?]\s*|\b(?:please|you|also|then|and|okay)\s+)(?:email|text)\s+\w',text,re.I))
    return verbs or message


def revoke_callbacks(actor):
    with phone.store().db() as db:
        db.execute('UPDATE phone_jobs SET callback_requested=0,followup_allowed=0 WHERE actor=?', (actor,))
        db.execute("UPDATE phone_outbound SET state='cancelled' WHERE actor=? AND callback_job IS NOT NULL AND state IN ('approved','preparing','pending_approval')", (actor,))


def context_for(call, cfg):
    entry = phone.callers().get(call.get('actor',''), {})
    facts = {'caller': entry.get('name', ''), 'voice_model': cfg.phone_live_model,
             'voice': cfg.phone_voice, 'identity': "Eli, Dr. Omid Shaye's AI chief of staff",
             'phone_policy': 'No access code. Work survives hangup. No callback unless explicitly requested. Text means iMessage; WhatsApp only when named.'}
    with phone.store().db() as db:
        row = db.execute('SELECT * FROM phone_voice_context WHERE actor=?', (call.get('actor',''),)).fetchone()
        facts['phone_work']=[dict(r) for r in db.execute('''SELECT COALESCE(d.caller_text,j.transcript) request,j.state,
            substr(j.result,1,600) verified_result,j.question FROM phone_jobs j LEFT JOIN phone_live_delegations d ON d.job_id=j.id
            WHERE j.actor=? AND j.created>? ORDER BY j.created DESC LIMIT 8''',(call.get('actor',''),time.time()-86400))]
    if row and row['user_id'] == entry.get('user_id') and time.time()-row['updated'] < 300:
        packet = json.loads(row['packet'])
        facts.update(packet)
    else:
        facts['context_status'] = 'Native context is unavailable or stale. Answer runtime facts above; do not invent team members, rank or memories.'
    return facts


def archive(call, fragments, model, delegated=()):
    """A conversation record never enters the action queue or authorizes a call."""
    turns = []
    for f in fragments:
        if f['role']=='assistant' and f.get('playback') in {'discarded','unconfirmed'}:
            continue
        if not f['text'].strip() or automated_audio(f['text']):
            continue
        if contains_phi(f['text']) or PRIVATE.search(f['text']):
            continue
        if turns and turns[-1]['role'] == f['role'] and len(turns[-1]['text'])+len(f['text']) <= 12000:
            turns[-1]['text'] += f['text']
            turns[-1]['delegated'] = turns[-1]['delegated'] or f.get('id') in delegated
        else:
            turns.append({'role': f['role'], 'text': f['text'][:12000], 'delegated': f.get('id') in delegated})
    # Check joined fragments too: a clinical identifier can span deltas.
    turns = [t for t in turns if not contains_phi(t['text']) and not PRIVATE.search(t['text'])]
    if not turns:
        return
    payload = json.dumps({'model': model, 'turns': turns}, ensure_ascii=False)
    if len(payload)>100000:
        return
    with phone.store().db() as db:
        db.execute('INSERT OR IGNORE INTO phone_conversations(call_id,actor,payload,created) VALUES (?,?,?,?)',
                   (call['id'],call.get('actor',''),payload,time.time()))


def summaries(actor):
    with phone.store().db() as db:
        calls = db.execute('SELECT id,created,ended FROM phone_calls WHERE actor=? AND ended IS NOT NULL ORDER BY created DESC LIMIT 10', (actor,)).fetchall()
        output = []
        for c in calls:
            items = [dict(r) for r in db.execute('''SELECT j.id,COALESCE(d.caller_text,j.transcript) request,j.state,j.result,j.error,j.question,
                n.heard_at FROM phone_jobs j LEFT JOIN phone_live_delegations d ON d.job_id=j.id
                LEFT JOIN phone_notices n ON n.job_id=j.id WHERE j.call_id=? AND j.actor=? ORDER BY j.created''', (c['id'],actor))]
            if items:
                output.append({**dict(c),'items':items})
        return output


STOP_WORDS = set('a an the is are was were i you your my me it that this to for of on in at and or with what how can could would please eli okay thanks tell do did have about'.split())


def terms(text):
    return {w for w in re.findall(r'[a-z]+', text.casefold()) if len(w)>2 and w not in STOP_WORDS}


def relevant_notice(notice, call_id, latest):
    """Conservative admission; the voice model still chooses a natural turn."""
    if re.search(r'\b(?:any updates|task updates|pending (?:results|questions)|what.s (?:ready|done)|results (?:ready|yet)|where were we)\b', latest, re.I):
        return True
    if notice.get('source_call') != call_id:
        return False
    if notice.get('notify_policy')=='silent_success' and notice.get('state')=='completed':
        if not re.search(r'\b(?:did you|is it done|finished|result|update|about that)\b',latest,re.I):return False
    origin = notice.get('request', '')
    if latest.strip() and (latest.strip() in origin or origin.strip() in latest):
        return True
    # A common channel word does not establish a common topic. A general
    # discussion about email-writing must not release an old inbox result.
    generic={'email','mail','inbox','whatsapp','calendar','schedule','imessage','check','latest','recent','message','send','write','good','should'}
    overlap=(terms(origin)&terms(latest))-generic
    if re.search(r'\b(?:how|why|what do you think)\b',latest,re.I):return False
    return len(overlap)>=2 or (bool(overlap) and bool(re.search(r'\b(?:did|done|finish|find|found|result|update|about|that)\b',latest,re.I)))
