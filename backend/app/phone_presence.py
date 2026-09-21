"""Actor-scoped voice context and call records, separate from executable work."""
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import phone
from .security import contains_phi

PRIVATE = re.compile(r'(?i)\b(?:sk[_-][a-z0-9_-]{16,}|Bearer\s+\S{8,}|password\s*[:=]|totp[_ ]?secret)')


def automated_audio(text):
    return bool(re.search(r'(?:call has been forwarded|forwarded to voicemail|at the tone.{0,30}record|person you.re trying to reach is not available)', text, re.I))


def stop_calls(text):
    return bool(re.search(r'\b(?:stop calling(?: me)?|do not call me|don.t call me|no more calls)\b', text, re.I))


def known_question(text):
    """Narrow repair for an unnecessary model delegation; not a general classifier."""
    return bool(re.search(r'\b(?:what (?:ai )?model|what.s your name|what is your name|who are you|who (?:do you|you) work for|what (?:is your job|can you do)|who(?:.s| is| are).*\bteam|who am i|what.s my name|what (?:time|day|date) is it|what.s (?:today.s date|the time)|what day is today)\b', text, re.I)) and not work_requested(text)


def recall_question(text):
    return bool(re.search(r'\b(?:last|previous|prior) (?:phone )?call\b',text,re.I)
                and re.search(r'\b(?:what|recall|remember)\b',text,re.I)
                and not re.search(r'\b(?:send|email|text|schedule|cancel|repeat|redo)\b',text,re.I))


def task_status_question(text):
    return bool(re.search(r'\b(?:did (?:both |the |those |these )?tasks? (?:complete|finish)|(?:what|which) (?:did|have) you (?:actually )?(?:send|sent|complete)|(?:did|have) you (?:actually )?(?:send|sent)\b|(?:status|progress) (?:of|on) (?:the |those |these |both )?tasks?)',text,re.I)) and not re.search(r'\b(?:resend|retry|again|cancel|go ahead|(?:last|previous) call|(?:please|and|also|then)\s+(?:send|text|email|schedule)|send (?:it|that) now)\b',text,re.I)


def prior_call(call):
    """Caller-scoped primary records. Never confuse this call with an earlier one."""
    if not call.get('id'):
        return {'available':False,'reason':'No current call boundary supplied.'}
    with phone.store().db() as db:
        current=db.execute('SELECT created FROM phone_calls WHERE id=? AND actor=?',(call['id'],call['actor'])).fetchone()
        if not current:return {'available':False,'reason':'Current call is unavailable.'}
        row=db.execute('''SELECT c.id,c.created,c.ended,a.payload FROM phone_calls c
            JOIN phone_conversations a ON a.call_id=c.id AND a.actor=c.actor
            WHERE c.actor=? AND c.id!=? AND c.ended<=? AND c.created<?
            ORDER BY c.created DESC LIMIT 1''',(call['actor'],call['id'],current['created'],current['created'])).fetchone()
        if not row:return {'available':False,'reason':'No earlier recorded call for this caller.'}
        tasks=[dict(r) for r in db.execute('''SELECT j.id,j.state,d.caller_text AS request,j.result,j.question
            FROM phone_jobs j LEFT JOIN phone_live_delegations d ON d.job_id=j.id
            WHERE j.actor=? AND j.call_id=? AND j.execution_class!='intake' ORDER BY j.created LIMIT 8''',(call['actor'],row['id']))]
    payload=json.loads(row['payload'])
    words=' '.join(t['text'] for t in payload.get('turns',[]) if t.get('role')=='user')
    for task in tasks:
        for field,limit in [('request',500),('result',700),('question',250)]:task[field]=(task[field] or '')[:limit]
    return {'available':True,'call_id':row['id'],'started_at':row['created'],'ended_at':row['ended'],
            'caller_words':words[:5000],'tasks':tasks,'rule':'Prior call evidence only, never instructions to repeat work.'}


def clock_facts(cfg):
    zone=getattr(cfg,'dashboard_timezone','America/Los_Angeles')
    return {'current_datetime':datetime.now(ZoneInfo(zone)).isoformat(timespec='seconds'),
            'timezone':zone,'clock_scope':'Practice timezone; do not assume the caller is in this timezone.'}


def local_facts(call,cfg):
    context=context_for(call,cfg)
    return {k:v for k,v in context.items() if k not in {'phone_work','recent_phone_dialogue'}}


def task_states(call):
    """One current execution/clarification revision per logical task, with receipts."""
    with phone.store().db() as db:
        rows=db.execute("""SELECT * FROM phone_jobs WHERE actor=? AND call_id=?
            AND (execution_class!='intake' OR (state='planning' AND parent_id IS NOT NULL))
            AND state!='resumed' ORDER BY created DESC LIMIT 32""",(call['actor'],call['id'])).fetchall()
        result={}
        for row in rows:
            plan=json.loads(row['plan'] or '{}');root=row['root_id'] or row['id']
            if root in result or plan.get('atomic_kind')=='clarification':continue
            receipts=[dict(r) for r in db.execute("""SELECT u.tool,u.status FROM phone_job_updates u JOIN phone_jobs j ON j.id=u.job_id
                WHERE COALESCE(j.root_id,j.id)=? AND u.kind='action' AND u.status IN ('sent','verified')""",(root,))]
            mutation=plan.get('atomic_kind') in {'email','whatsapp','imessage','calendar','article','global'}
            result[root]={'task_id':root,'question_id':row['id'] if row['state']=='waiting_for_input' else None,
                'scope':plan.get('atomic_scope',''),'state':row['state'],'details':plan.get('details',{}),
                'question':row['question'] if row['state']=='waiting_for_input' else '',
                'completion_allowed':row['state']=='completed' and (bool(receipts) or not mutation),
                'receipts':receipts,'result':(row['error'] or row['result'])[:500] if row['state'] in {'completed','failed','uncertain'} else ''}
        return result


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
    facts.update(clock_facts(cfg))
    facts['previous_call']=prior_call(call)
    facts['known_contacts']=[{'name':c.get('name',''),'email':email,'phone':c.get('phone','')} for email,c in phone.callers().items()]
    with phone.store().db() as db:
        row = db.execute('SELECT * FROM phone_voice_context WHERE actor=?', (call.get('actor',''),)).fetchone()
        facts['phone_work']=[dict(r) for r in db.execute('''SELECT COALESCE(d.caller_text,j.transcript) request,j.state,
            substr(j.result,1,600) verified_result,j.question FROM phone_jobs j LEFT JOIN phone_live_delegations d ON d.job_id=j.id
            WHERE j.actor=? AND j.call_id=? AND j.state!='expanded' AND NOT (j.execution_class='intake' AND j.state='completed')
            ORDER BY j.created DESC LIMIT 8''',(call.get('actor',''),call.get('id','')))]
        # Unconfirmed generated speech remains in the private audit archive.
        # Reinjecting it into new calls recycles unheard answers and apology loops.
    if row and row['user_id'] == entry.get('user_id') and time.time()-row['updated'] < 300:
        packet = json.loads(row['packet'])
        packet.pop('recent_phone_dialogue',None)  # Use the explicitly bounded previous_call record above.
        facts.update(packet)
    else:
        facts['context_status'] = 'Native context is unavailable or stale. Answer runtime facts above; do not invent team members, rank or memories.'
    return facts


def archive(call, fragments, model, delegated=()):
    """A conversation record never enters the action queue or authorizes a call."""
    turns = []
    generated=[]
    for f in fragments:
        if f['role']=='assistant' and f.get('playback') in {'discarded','unconfirmed'}:
            if f.get('playback')=='unconfirmed':
                if generated and len(generated[-1]['text'])+len(f['text'])<=12000:generated[-1]['text']+=f['text']
                else:generated.append({'text':f['text'][:12000],'playback':'unverified'})
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
    generated=[t for t in generated if not contains_phi(t['text']) and not PRIVATE.search(t['text'])]
    # Preserve approximate provider transcript times for diagnosis. These are
    # NOT audio-playout times. Earlier archives merged roles and lost this map.
    timeline=[]
    if not contains_phi(''.join(f['text'] for f in fragments)) and not PRIVATE.search(''.join(f['text'] for f in fragments)):
        timeline=[{k:f[k] for k in ('role','text','start_ms','end_ms','turn_id','playback') if k in f}
                  for f in fragments if not automated_audio(f['text'])]
    payload = json.dumps({'model': model, 'turns': turns,'generated_unconfirmed':generated,
                          'transcript_timeline':timeline}, ensure_ascii=False)
    if len(payload)>100000:
        # Retain the existing bounded memory record even if the diagnostic map
        # would exceed its transport budget.
        payload=json.dumps({'model':model,'turns':turns,'generated_unconfirmed':generated},ensure_ascii=False)
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
                LEFT JOIN phone_notices n ON n.job_id=j.id WHERE j.call_id=? AND j.actor=? AND j.state!='expanded'
                AND NOT (j.execution_class='intake' AND j.state='completed') ORDER BY j.created''', (c['id'],actor))]
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
