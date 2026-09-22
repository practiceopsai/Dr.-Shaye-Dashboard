"""Dependency steps in the existing ledger and executor; no audio operations."""
import hashlib
import json
import re
import time
from . import task_ledger as ledger
from .phone_intake import contact


STEPS=('understand','plan','research','create','verify','deliver','confirm')


def prepare(task, actor, contacts):
    details=task.get('details',{});quote='\n'.join(task['quotes'])
    if task.get('question'):return {},task['question']
    fmt=details.get('deliverable','markdown') or 'markdown'
    if fmt not in {'markdown','pptx'}:return {},'Should the deliverable be a presentation or written findings?'
    channel=details.get('channel','')
    mention=task.get('recipient','')
    if channel and channel not in {'email','imessage','whatsapp'}:return {},'Which delivery channel should I use?'
    if channel:
        self_reference=bool(re.search(r'\b(?:to me|email me|send me|text me)\b',quote,re.I))
        recipient=(actor if channel=='email' else contacts.get(actor,{}).get('phone')) if self_reference else contact(mention,contacts,'email' if channel=='email' else 'phone')
        if not recipient:return {},'Who should receive the findings, and at what address or number?'
        if not self_reference and mention.casefold() not in quote.casefold():return {},'Please confirm the intended recipient.'
        if not re.search({'email':r'\be-?mail\b','whatsapp':r'\bwhats\s*app\b','imessage':r'\b(?:text|imessage)\b'}[channel],quote,re.I):
            return {},'Please confirm the delivery channel.'
    else:recipient=''
    if fmt=='pptx' and channel in {'imessage','whatsapp'}:return {},'Should I email the presentation attachment instead?'
    self_target=recipient in {actor,contacts.get(actor,{}).get('phone')}
    preauthorized=bool(re.search(r'\b(?:just send|go ahead and send|send (?:it |them )?without asking|no need to ask)\b',quote,re.I))
    return {'operation':'workflow','workflow':{'goal':task['scope'],'format':fmt,'channel':channel,
        'recipient':recipient,'title':details.get('title') or task['scope'][:100],
        'approval_quote':quote,'preauthorized':self_target or preauthorized,
        'authorization_call':None}},''


def expand(db, job_id):
    row=dict(db.execute('SELECT * FROM phone_jobs WHERE id=?',(job_id,)).fetchone())
    p=json.loads(row['plan']);spec=p['workflow'];root=row['root_id'] or row['id']
    spec['authorization_call']=row['call_id'];p['workflow']=spec
    ids={stage:hashlib.sha256((job_id+':step:'+stage).encode()).hexdigest()[:32] for stage in STEPS}
    db.execute("UPDATE phone_jobs SET state='workflow',plan=? WHERE id=?",(json.dumps(p),job_id))
    ledger.track(db,job_id)
    previous=None
    for stage in STEPS:
        identifier=ids[stage];done=stage in {'understand','plan'}
        plan={'operation':'workflow_step','stage':stage,'workflow':spec,'workflow_root':root,'workflow_generation':job_id,
              'atomic_kind':'deliver' if stage=='deliver' else 'read' if stage=='research' else 'draft',
              'atomic_scope':stage.title()+': '+spec['goal'],'details':p.get('details',{}),'recipient':spec['recipient']}
        if stage=='deliver' and spec['channel']:plan['required_receipts']=[spec['channel']]
        db.execute('''INSERT INTO phone_jobs(id,actor,call_id,transcript,state,created,updated,root_id,
            authorization,plan,priority,notify_policy,batch_id,resource_key,depends_on,result)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (identifier,row['actor'],row['call_id'],row['transcript'],'completed' if done else 'queued',
             time.time(),time.time(),identifier,row['authorization'],json.dumps(plan),row['priority'],
             'silent_success',row['batch_id'],'workflow:'+identifier,json.dumps([previous] if previous else []),
             json.dumps({'stage':stage,'source':row['transcript'].rsplit('New caller speech: ',1)[-1]}) if done else ''))
        ledger.track(db,identifier,parent_id=root)
        ledger.event(db,identifier,'completed' if done else 'pending',{'stage':stage})
        previous=identifier
    ledger.event(db,root,'planned',{'steps':ids})
    return ids


def settle(db):
    for row in db.execute("SELECT * FROM phone_jobs WHERE state='workflow'").fetchall():
        root=row['root_id'] or row['id']
        children=db.execute('''SELECT j.* FROM phone_task_meta m JOIN phone_jobs j ON j.id=m.current_job
            WHERE m.parent_task=? AND json_extract(j.plan,'$.workflow_generation')=?''',(root,row['id'])).fetchall()
        if not children:continue
        failed=next((c for c in children if c['state'] in {'failed','uncertain','cancelled'}),None)
        waiting=next((c for c in children if c['state']=='waiting_for_input'),None)
        if failed:
            state='failed';result='';error=failed['error'] or 'A required workflow step did not complete. Review that step before retrying.'
        elif all(c['state']=='completed' for c in children):
            state='completed';error=''
            final=next(c for c in children if json.loads(c['plan']).get('stage')=='confirm')
            result=final['result']
            delivery=next(c for c in children if json.loads(c['plan']).get('stage')=='deliver')
            try:proof=json.loads(delivery['result'])
            except ValueError:proof={}
            spec=json.loads(delivery['plan'])['workflow']
            receipts=db.execute("SELECT 1 FROM phone_job_updates WHERE job_id=? AND kind='action' AND status IN ('sent','verified')",(delivery['id'],)).fetchone()
            if not proof.get('success') or (spec['channel'] and (not receipts or not proof.get('message_id') or not proof.get('source_verified',True))):
                state='failed';result='';error='The workflow has no verified delivery receipt. Review the saved artifact and provider outcome; nothing will be resent automatically.'
        else:
            if waiting:
                ledger.event(db,root,'needs_input',{'task_id':waiting['id']}) if not db.execute(
                    "SELECT 1 FROM phone_task_events WHERE task_id=? AND kind='needs_input' AND payload LIKE ?",
                    (root,'%'+waiting['id']+'%')).fetchone() else None
            continue
        db.execute('UPDATE phone_jobs SET state=?,result=?,error=?,updated=? WHERE id=?',(state,result,error,time.time(),row['id']))
        ledger.event(db,root,state,{'result':result[:1000],'error':error})
        db.execute('INSERT OR IGNORE INTO phone_notices(job_id,actor,kind,content,created) VALUES (?,?,?,?,?)',
                   (row['id'],row['actor'],'result',result or error,time.time()))


def approve_delivery(db, actor, job_id, answer, source_id):
    """Resume the exact delivery node; approved artifact/recipient never replanned."""
    row=db.execute('SELECT * FROM phone_jobs WHERE id=? AND actor=?',(job_id,actor)).fetchone()
    if not row:return False
    plan=json.loads(row['plan'] or '{}')
    if plan.get('operation')!='workflow_step' or plan.get('stage')!='deliver':return False
    if row['state']!='waiting_for_input':raise ValueError('Delivery is not waiting for confirmation')
    if not re.fullmatch(r'\s*(?:yes|yes please|correct|go ahead|go ahead and send it|send it|approved|just send it)[.!\s]*',answer,re.I):
        raise ValueError('Please confirm delivery or give the specific change; the artifact has not been sent')
    # Existing native journal is at waiting_for_input; use a new execution revision.
    task=ledger.get(db,actor,row['root_id'] or row['id'])
    changed=ledger.revise(db,actor,task['id'],answer,source_id)
    plan['workflow']['preauthorized']=True
    plan['workflow']['approval_source']=source_id
    plan['workflow']['approval_quote']+='\n'+answer
    db.execute("UPDATE phone_jobs SET plan=?,state='queued',execution_class='background_action' WHERE id=?",
               (json.dumps(plan),changed['job_id']))
    ledger.event(db,task['id'],'approved',{'source':source_id})
    return changed['job_id']
