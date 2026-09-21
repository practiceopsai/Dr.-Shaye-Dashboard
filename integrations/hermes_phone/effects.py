"""Effect attempts survive model loops/restarts. Unknown outcomes never replay.

This is an additional ledger, not permission to act. Existing native policy and
prepared tools remain authoritative. Only recognized provider operations are
classified here; arbitrary shell effects are not claimed to be exactly-once.
"""
import hashlib
import json
import re
import time


def mutation(tool,args):
    if tool.startswith('eli_phone_'):return False  # Prepared tools own receipts.
    if tool.upper().endswith('COMPOSIO_MULTI_EXECUTE_TOOL'):
        return any(mutation(x.get('tool_slug',''),x.get('arguments',{})) for x in args.get('tools',[]))
    return bool(re.search(r'(?:^|_)(?:send|reply|create|update|patch|delete|remove|insert|cancel|move|publish|post|book)(?:_|$)',tool,re.I))


def identity(job,tool,args):
    clean={k:v for k,v in args.items() if k not in {'approval_quote','thought','current_step','current_step_metric','session_id'}}
    if tool=='email_send':
        clean={k:v for k,v in clean.items() if k not in {'mandate','success_condition','summary'}}
    if tool.upper().endswith('COMPOSIO_MULTI_EXECUTE_TOOL'):
        clean={'tools':[{k:v for k,v in x.items() if k in {'tool_slug','arguments','account'}} for x in args.get('tools',[])]}
    return hashlib.sha256((str(job.get('root_id') or job['id'])+'\0'+tool+'\0'+json.dumps(clean,sort_keys=True,default=str)).encode()).hexdigest()


def init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS phone_effect_attempts(
        id TEXT PRIMARY KEY,root_id TEXT,job_id TEXT,tool TEXT,state TEXT,provider_id TEXT,
        receipt TEXT,created REAL,updated REAL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS phone_effect_events(
        effect_id TEXT,state TEXT,receipt TEXT,created REAL,PRIMARY KEY(effect_id,state))''')


def atoms(tool,args):
    if tool.upper().endswith('COMPOSIO_MULTI_EXECUTE_TOOL'):
        return [(x.get('tool_slug',''),{**x.get('arguments',{}),'_account':x.get('account')},i)
                for i,x in enumerate(args.get('tools',[])) if mutation(x.get('tool_slug',''),x.get('arguments',{}))]
    return [(tool,args,None)] if mutation(tool,args) else []


def begin(perf,job,tool,args):
    operations=atoms(tool,args)
    if not operations:return None
    with perf.db() as db:
        init(db);db.execute('BEGIN IMMEDIATE')
        keyed=[(identity(job,name,params),name) for name,params,_ in operations]
        # Detect duplicate children even inside the first submitted batch.
        if len({key for key,_ in keyed})!=len(keyed):
            return {'block':True,'message':'This batch contains the same external effect twice. Submit each remaining operation once.'}
        for key,name in keyed:
            row=db.execute('SELECT * FROM phone_effect_attempts WHERE id=?',(key,)).fetchone()
            if row:
                return {'block':True,'message':'This batch contains an effect with an existing durable attempt: '+row['state']+'. '+row['receipt']+
                        ' Do not execute it again. Read the source if uncertain; submit only remaining unattempted operations.'}
        for key,name in keyed:
            db.execute('INSERT INTO phone_effect_attempts VALUES (?,?,?,?,?,?,?,?,?)',
                       (key,job.get('root_id') or job['id'],job['id'],name,'started','','',time.time(),time.time()))
            db.execute('INSERT INTO phone_effect_events VALUES (?,?,?,?)',(key,'started','',time.time()))


def envelope(data):
    if isinstance(data,str):data=json.loads(data)
    if not isinstance(data,dict):return {}
    if data.get('error') or data.get('isError') or data.get('successful') is False:return {'error':'provider_failure'}
    if isinstance(data.get('result'),(str,dict)):return envelope(data['result'])
    if data.get('content'):return envelope(next(x['text'] for x in data['content'] if x.get('type')=='text'))
    if isinstance(data.get('data'),dict):return envelope(data['data'])
    return data


def finish(perf,job,tool,args,data,status):
    operations=atoms(tool,args)
    if not operations or status=='blocked':return
    try:outer=envelope(data)
    except (ValueError,StopIteration):outer={}
    for name,params,index in operations:
        result=outer
        if index is not None:
            rows=outer.get('results',[])
            row=next((r for i,r in enumerate(rows) if r.get('index',i)==index),{})
            try:result=envelope(row.get('response',{}))
            except (ValueError,StopIteration):result={}
        key=identity(job,name,params)
        provider=str(result.get('message_id') or result.get('id') or result.get('event_id') or '')[:200]
        success=not(result.get('error') or result.get('success') is False or status in {'failed','error'})
        state='verified' if success and provider and result.get('source_verified') is True else 'accepted' if success and provider else 'uncertain'
        proof=verification_plan(name,params,result,provider) if state=='accepted' else None
        receipt=json.dumps({'provider_operation_id':provider,'state':state,'source_verified':state=='verified','verification':proof})
        with perf.db() as db:
            init(db)
            changed=db.execute("UPDATE phone_effect_attempts SET state=?,provider_id=?,receipt=?,updated=? WHERE id=? AND state='started'",
                       (state,provider,receipt,time.time(),key)).rowcount
            if changed:db.execute('INSERT OR IGNORE INTO phone_effect_events VALUES (?,?,?,?)',(key,state,receipt,time.time()))


def verification_plan(tool,args,result,provider):
    if not provider:return None
    if tool=='email_send':
        fields={k:result[k] for k in ('message_id','thread_id') if k in result}
        return {'route':'agentmail','id':provider,'expected':fields}
    if tool.startswith('GMAIL_') and re.search(r'(?:SEND|REPLY)',tool) and args.get('_account'):
        return {'route':'gmail','id':provider,'account':args['_account']}
    if tool.startswith('GOOGLECALENDAR_') and re.search(r'(?:CREATE|INSERT|PATCH|UPDATE)',tool) and args.get('_account'):
        fields={k:result[k] for k in ('summary','start','end','status','updated') if k in result}
        if not {'summary','start','end'}<=fields.keys():return None
        return {'route':'calendar','id':provider,'account':args['_account'],
                'calendar_id':args.get('calendar_id',args.get('calendarId','primary')),
                'fields':list(fields),'hash':hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()}
    return None


def reconcile(perf,job,invoke=None):
    """Retry only provider reads. No path here can re-execute a mutation."""
    from .reads import unwrap
    from .operations import native_call,mail_services
    with perf.db() as db:
        init(db)
        rows=[dict(r) for r in db.execute("SELECT * FROM phone_effect_attempts WHERE root_id=? AND state='accepted'",
                                        (job.get('root_id') or job['id'],))]
    for row in rows:
        receipt=json.loads(row['receipt']);plan=receipt.get('verification')
        attempts=receipt.get('verification_attempts',0)
        if not plan or attempts>=3 or time.time()-receipt.get('verification_time',0)<5*attempts:continue
        receipt.update(verification_attempts=attempts+1,verification_time=time.time())
        verified=False
        try:
            if plan['route']=='agentmail':
                data=invoke(plan) if invoke else mail_services().mail.get_message(plan['id'])
                verified=all(data.get(k)==v for k,v in plan['expected'].items())
            else:
                slug='GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID' if plan['route']=='gmail' else 'GOOGLECALENDAR_EVENTS_GET'
                args={'message_id':plan['id'],'format':'minimal'} if plan['route']=='gmail' else {'event_id':plan['id'],'calendar_id':plan['calendar_id']}
                if invoke:data=unwrap(invoke(plan))
                else:
                    from tools.registry import registry
                    names=[n for n in registry.get_all_tool_names() if n.upper().endswith('COMPOSIO_MULTI_EXECUTE_TOOL')]
                    if len(names)!=1:continue
                    data=unwrap(native_call(names[0],{'tools':[{'tool_slug':slug,'arguments':args,'account':plan['account']}],
                        'sync_response_to_workbench':False,'current_step':'VERIFY_PHONE_EFFECT'}))
                if plan['route']=='gmail':verified=(data.get('id',data.get('messageId'))==plan['id'] and 'SENT' in data.get('labelIds',[]))
                else:
                    data=data.get('event_data',data)
                    fields={k:data.get(k) for k in plan['fields']}
                    verified=data.get('id')==plan['id'] and hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()==plan['hash']
        except Exception:pass
        if verified:
            receipt.update(state='verified',source_verified=True)
        with perf.db() as db:
            changed=db.execute("UPDATE phone_effect_attempts SET state=?,receipt=?,updated=? WHERE id=? AND state='accepted'",
                ('verified' if verified else 'accepted',json.dumps(receipt),time.time(),row['id'])).rowcount
            if changed:db.execute('INSERT OR IGNORE INTO phone_effect_events VALUES (?,?,?,?)',
                (row['id'],'verification-'+str(attempts+1),json.dumps(receipt),time.time()))
        if verified:perf.record(job['id'],'action',row['tool'],'verified',content='Provider read-back verified the existing operation. No action was repeated.')


def verified_provider(perf,job,provider):
    """Promote matching accepted receipts only after an exact provider read-back."""
    if not provider:return
    with perf.db() as db:
        init(db)
        rows=db.execute("SELECT id FROM phone_effect_attempts WHERE root_id=? AND provider_id=? AND state='accepted'",
                        (job.get('root_id') or job['id'],provider)).fetchall()
        for row in rows:
            receipt=json.dumps({'provider_operation_id':provider,'state':'verified','source_verified':True})
            db.execute("UPDATE phone_effect_attempts SET state='verified',receipt=?,updated=? WHERE id=?",(receipt,time.time(),row['id']))
            db.execute('INSERT OR IGNORE INTO phone_effect_events VALUES (?,?,?,?)',(row['id'],'verified',receipt,time.time()))


def review(perf,job):
    with perf.db() as db:
        init(db)
        return [dict(r) for r in db.execute('SELECT tool,state,provider_id,receipt FROM phone_effect_attempts WHERE root_id=?',
                                           (job.get('root_id') or job['id'],))]


def reconcile_saved(perf,settings):
    """Bounded recovery of accepted writes, including delivered/uncertain jobs."""
    from gateway.session_context import set_session_vars,clear_session_vars
    with perf.db() as db:
        init(db)
        rows=[dict(r) for r in db.execute('''SELECT DISTINCT w.payload FROM phone_effect_attempts e
            JOIN work w ON w.id=e.job_id WHERE e.state='accepted' AND e.created>? LIMIT 10''',(time.time()-86400,))]
    for row in rows:
        job=json.loads(row['payload']);identity=settings.get('identities',{}).get(job['actor'])
        if not identity or identity!=job.get('identity'):continue
        tokens=set_session_vars(platform='eli_phone',chat_type='dm',chat_id='phone:'+identity['user_id'],
            user_id=identity['user_id'],user_name=identity['name'],message_id=job['id'],session_id='phone-reconcile-'+job['id'])
        try:reconcile(perf,job)
        finally:clear_session_vars(tokens)


def cancel_tool(args,settings):
    from .performance import current
    from . import api_request
    active=current(settings)
    if not active:return {'success':False,'error':'An authenticated current phone request is required.'}
    _,job,fresh=active
    quote=str(args.get('approval_quote',''))
    if not quote or quote not in fresh:return {'success':False,'error':'Use the current caller cancellation, not earlier speech.'}
    return api_request('/internal/phone/jobs/'+job['id']+'/cancel',{'claim':job['claim'],'request_id':args['request_id'],'quote':quote})


CANCEL_SCHEMA={'name':'eli_phone_cancel_task','description':'Cancel an exact pending phone task. A running irreversible effect may be too late; never claim cancellation beyond the returned state.',
 'parameters':{'type':'object','properties':{'request_id':{'type':'string'},'approval_quote':{'type':'string'}},'required':['request_id','approval_quote']}}
