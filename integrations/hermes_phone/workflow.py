"""General research/artifact/delivery steps executed by the existing Hermes worker."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile
from xml.etree import ElementTree
from . import ledger


def plan_for(job):
    value=job.get('plan') or {}
    return json.loads(value) if isinstance(value,str) else value


def context(job):
    plan=plan_for(job)
    if plan.get('operation')!='workflow_step':return ''
    step=plan['stage'];goal=plan['workflow']['goal']
    common=('This is one persistent workflow step: '+step+'. Overall requested outcome: '+goal+
        '. Only this step is authorized; other steps own delivery. Do not send, schedule, delegate background agents or create new tasks. ')
    if step=='research':return common+(
        'Use available read/search tools to gather current primary sources. Return substantive findings with source URLs and clear uncertainty, '
        'not a promise or plan. No shell, writes, messages or file creation in this step.\n')
    if step=='create':return common+(
        'Synthesize the verified prerequisite research into the requested deliverable. Return ONLY a JSON object: '
        '{"title":string,"summary":string,"sections":[{"heading":string,"text":string}],"sources":[{"title":string,"url":string}]}. '
        'Use 3-16 concise sections, each heading under 90 characters and text under 900 characters; title under 100. '
        'Preserve important comparisons, implications and uncertainty. Source URLs must appear in the prerequisite research. '
        'Do not call any tools; a deterministic artifact writer will create the file from your content.\n')
    return common+'This step is handled by the verified artifact runner.\n'


def guard(job, tool, args, perf):
    plan=plan_for(job);step=plan['stage']
    safe_context={'eli_context','eli_phone_clarify','tool_search','tool_describe'}
    read=bool(re.search(r'(?:^|_)(?:search|fetch|get|read|list|extract)(?:_|$)',tool,re.I))
    if step=='research':
        # Composite tools require every atom to be a read. Arbitrary code/terminal
        # tools cannot prove their external effects, so are excluded in this step.
        if tool.upper().endswith('COMPOSIO_MULTI_EXECUTE_TOOL'):
            read=bool(args.get('tools')) and all(re.search(r'(?:^|_)(?:SEARCH|FETCH|GET|READ|LIST|FIND)(?:_|$)',x.get('tool_slug',''))
                and not re.search(r'(?:SEND|CREATE|UPDATE|DELETE|INSERT|POST|PATCH)',x.get('tool_slug','')) for x in args['tools'])
        if (read or tool in safe_context) and not re.search(r'write|edit|send|delete|terminal|execute_code',tool,re.I):return None
    elif step=='deliver':
        if tool in {'email_send','eli_phone_send_whatsapp','eli_phone_send_imessage'}:
            try:
                manifest=load_delivery(job,perf)
                spec=plan['workflow']
                if not spec.get('preauthorized'):raise ValueError('Delivery needs confirmation')
                if tool=='email_send':
                    if args.get('to')!=[spec['recipient']] or args.get('text')!=manifest['body'] or args.get('subject')!=manifest['title']:
                        raise ValueError('Delivery payload differs from the verified artifact')
                    if args.get('attachments',[])!=([manifest['path']] if manifest['format']=='pptx' else []):
                        raise ValueError('Attachment differs from the verified artifact')
                else:
                    if args.get('recipient')!=spec['recipient'] or args.get('message')!=manifest['body']:raise ValueError('Delivery payload differs')
                return None
            except Exception:return {'block':True,'message':'Only the approved verified artifact may be delivered to its recorded recipient.'}
        if tool=='email_registry' and args.get('action') in {'thread_close','task_update'}:return None
    return {'block':True,'message':'This tool is outside the current workflow step. Return the required step output; do not bypass it through another tool.'}


def parse_document(raw, research):
    text=raw.strip()
    if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    data=json.loads(text)
    if not isinstance(data,dict) or not 1<=len(data.get('title',''))<=100 or not 1<=len(data.get('summary',''))<=1800:raise ValueError('Incomplete document')
    sections=data.get('sections',[]);sources=data.get('sources',[])
    if not 1<=len(sections)<=24 or not 1<=len(sources)<=40:raise ValueError('Document requires sections and sources')
    for item in sections:
        if not 1<=len(item.get('heading',''))<=90 or not 1<=len(item.get('text',''))<=900:raise ValueError('Invalid document section')
    for item in sources:
        url=item.get('url','')
        if not re.match(r'^https?://[^\s]+$',url) or url not in research:raise ValueError('Source is absent from research evidence')
    from .operations import PATIENT
    if re.search(PATIENT+'|lorem ipsum|TODO:|PLACEHOLDER',json.dumps(data),re.I):raise ValueError('Document requires review')
    return data


def build_artifact(perf, job, document, *, node=None):
    plan=plan_for(job);fmt=plan['workflow']['format']
    folder=perf.path.parent/'task-artifacts'/hashlib.sha256(job['id'].encode()).hexdigest()
    folder.mkdir(parents=True,exist_ok=True)
    body=document['summary']+'\n\n'+'\n\n'.join(s['heading']+'\n'+s['text'] for s in document['sections'])
    body+='\n\nSources\n'+'\n'.join(s['title']+': '+s['url'] for s in document['sources'])
    if len(body)>15000:raise ValueError('Document exceeds delivery limit')
    path=folder/('presentation.pptx' if fmt=='pptx' else 'findings.md')
    if fmt=='pptx':
        source=folder/'content.json';source.write_text(json.dumps(document),encoding='utf-8')
        run=subprocess.run([node or shutil.which('node') or 'node',str(Path(__file__).with_name('render_deck.cjs')),str(source),str(path)],
            capture_output=True,timeout=60,creationflags=0x08000000 if __import__('os').name=='nt' else 0)
        if run.returncode:raise RuntimeError('Presentation creation failed: '+run.stderr.decode(errors='replace')[-300:])
    else:path.write_text('# '+document['title']+'\n\n'+body,encoding='utf-8')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest={'artifact_id':hashlib.sha256((plan['workflow_root']+':'+digest).encode()).hexdigest(),
        'path':str(path.resolve()),'sha256':digest,'format':fmt,
        'title':document['title'],'body':body,'workflow_root':plan['workflow_root'],'verified':False}
    save_manifest(perf,job,manifest)
    return manifest


def save_manifest(perf,job,manifest):
    with perf.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS workflow_artifacts(id TEXT PRIMARY KEY,task_id TEXT,job_id TEXT,manifest TEXT,created REAL)')
        db.execute('INSERT OR REPLACE INTO workflow_artifacts VALUES (?,?,?,?,?)',
            (manifest['artifact_id'],manifest['workflow_root'],job['id'],json.dumps(manifest),time.time()))


def verify_artifact(manifest):
    path=Path(manifest['path']);data=path.read_bytes()
    if not data or hashlib.sha256(data).hexdigest()!=manifest['sha256']:raise ValueError('Artifact changed after creation')
    if manifest['format']=='pptx':
        with zipfile.ZipFile(path) as archive:
            slides=[n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
            if len(slides)<3:raise ValueError('Presentation is incomplete')
            for name in slides:ElementTree.fromstring(archive.read(name))
    elif not data.decode('utf-8').startswith('# '):raise ValueError('Findings document is invalid')
    return {**manifest,'verified':True,'bytes':len(data)}


def dependency(job):
    values=job.get('dependency_results',[])
    if len(values)!=1:raise ValueError('Exactly one verified prerequisite is required')
    return values[0]['result']


def load_delivery(job,perf):
    manifest=json.loads(dependency(job))
    if not manifest.get('verified'):raise ValueError('Artifact has not been verified')
    with perf.db() as db:
        row=db.execute('SELECT manifest FROM workflow_artifacts WHERE id=? AND task_id=?',
            (manifest['artifact_id'],plan_for(job)['workflow_root'])).fetchone()
    if not row:raise ValueError('Artifact belongs to a different task')
    saved=json.loads(row[0]);verified=verify_artifact(saved)
    if manifest['sha256']!=verified['sha256']:raise ValueError('Artifact digest mismatch')
    return verified


def authorized(db,job,args,channel):
    plan=plan_for(job)
    if plan.get('operation')!='workflow_step' or plan.get('stage')!='deliver':return False
    spec=plan['workflow']
    if not spec.get('preauthorized') or channel!=spec['channel'] or args.get('recipient')!=spec['recipient']:return False
    try:
        manifest=json.loads(dependency(job))
        row=db.execute('SELECT manifest FROM workflow_artifacts WHERE id=? AND task_id=?',(manifest['artifact_id'],plan['workflow_root'])).fetchone()
        saved=verify_artifact(json.loads(row[0]))
        return bool(manifest.get('verified') and args.get('message')==saved['body'])
    except Exception:return False


def deliver(job,settings,perf,*,invoke=None,services=None):
    from . import operations,effects,messaging,performance
    spec=plan_for(job)['workflow'];manifest=load_delivery(job,perf)
    if not spec['channel']:return {'success':True,'artifact':manifest,'delivered':False,'reason':'Saved in the task record; no external delivery requested.'}
    if not spec.get('preauthorized'):
        from .clarification import save_question
        q='The '+manifest['title']+' is ready. May I send it to '+spec['recipient']+' by '+spec['channel']+'?'
        save_question(perf,job['id'],q)
        return {'success':False,'waiting_for_input':True,'question':q}
    ledger.wait_ready(job)
    if spec['channel']!='email':
        if len(manifest['body'])>1800:raise ValueError('Findings are too long for this messaging route; choose email or request a shorter summary')
        args={'recipient':spec['recipient'],'message':manifest['body'],'approval_quote':spec['approval_quote']}
        result=messaging.send_message(args,settings,channel=spec['channel'])
        performance.after_tool(settings,tool_name='eli_phone_send_'+spec['channel'],args=args,result=result)
        return result
    call=invoke or operations.native_call;svc=services or operations.mail_services()
    args={'to':[spec['recipient']],'subject':manifest['title'],'text':manifest['body'],
          'attachments':[manifest['path']] if manifest['format']=='pptx' else [],
          'mandate':'Deliver this requested artifact once. No reminders or further follow-ups.',
          'success_condition':'Provider readback verifies recipient, content and attachment; close tracking.',
          'summary':'One-time verified task artifact delivery.'}
    # This local outbox is receipt storage only. The canonical fence is in the
    # native email_send hook immediately before its external write.
    key=hashlib.sha256(((job.get('root_id') or job['id'])+manifest['sha256']+spec['recipient']).encode()).hexdigest()
    with perf.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS workflow_deliveries(id TEXT PRIMARY KEY,receipt TEXT)')
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT receipt FROM workflow_deliveries WHERE id=?',(key,)).fetchone()
        if old:return json.loads(old[0])
        receipt={'success':False,'state':'uncertain','error':'Delivery outcome requires reconciliation; do not repeat it.'}
        db.execute('INSERT INTO workflow_deliveries VALUES (?,?)',(key,json.dumps(receipt)))
    def save():
        with perf.db() as db:db.execute('UPDATE workflow_deliveries SET receipt=? WHERE id=?',(json.dumps(receipt),key))
    try:
        sent=call('email_send',args)
        if not sent.get('message_id'):raise RuntimeError('No provider receipt')
        receipt.update(message_id=sent['message_id'],recipient=spec['recipient']);save()
        fetched=svc.mail.get_message(sent['message_id'])
        from email.utils import parseaddr
        verified=(fetched.get('message_id')==sent['message_id'] and fetched.get('subject')==manifest['title']
            and {parseaddr(x)[1].casefold() for x in fetched.get('to',[])}=={spec['recipient'].casefold()}
            and fetched.get('text','').strip()==manifest['body'].strip())
        if verified and manifest['format']=='pptx':
            attachments=[a for a in fetched.get('attachments',[]) if a.get('filename')==Path(manifest['path']).name]
            verified=len(attachments)==1
            if verified:
                downloaded=svc.mail.download_attachment(sent['message_id'],attachments[0]['attachment_id'],Path(manifest['path']).parent/'verified',Path(manifest['path']).name)
                verified=hashlib.sha256(Path(downloaded).read_bytes()).hexdigest()==manifest['sha256']
        if verified:
            receipt.update(success=True,state='sent',source_verified=True,artifact_id=manifest['artifact_id']);receipt.pop('error',None)
            effects.verified_provider(perf,job,sent['message_id'])
            perf.record(job['id'],'action','email_send','verified',content='Provider readback verified the requested artifact delivery.')
        try:
            call('email_registry',{'action':'thread_close','thread_id':sent['thread_id'],'summary':'One-time artifact delivered; no follow-ups.'})
            call('email_registry',{'action':'task_update','task_id':sent['task']['task_id'],'changes':{'status':'done','plan':'One delivery only.'}})
        except Exception:pass
    except Exception as exc:receipt['error_type']=type(exc).__name__
    save();return receipt


async def execute(job,settings,perf,agent_call):
    plan=plan_for(job);stage=plan['stage'];await ledger.ready(job)
    if stage in {'research','create'}:
        answer=None
        for attempt in range(3):
            await ledger.ready(job)
            try:
                answer=await agent_call()
                if not isinstance(answer,str) or not answer.strip():raise ValueError('Step returned no content')
                break
            except (TimeoutError,ConnectionError):
                if attempt==2:raise
                await asyncio.sleep(2**attempt)
        await ledger.ready(job)
        if stage=='research':
            if not re.search(r'https?://[^\s]+',answer):raise ValueError('Research returned no source evidence')
            return {'success':True,'result':answer}
        document=parse_document(answer,dependency(job))
        manifest=await asyncio.to_thread(build_artifact,perf,job,document)
        return {'success':True,'result':json.dumps(manifest)}
    if stage=='verify':
        manifest=verify_artifact(json.loads(dependency(job)));save_manifest(perf,job,manifest)
        return {'success':True,'result':json.dumps(manifest)}
    if stage=='deliver':
        result=await asyncio.to_thread(deliver,job,settings,perf)
        return {**result,'result':json.dumps(result)}
    if stage=='confirm':
        result=json.loads(dependency(job))
        if not result.get('success'):raise ValueError('Delivery has no verified result')
        if result.get('delivered') is False:return {'success':True,'result':'The requested artifact was created and verified. No external delivery was requested. '+json.dumps(result['artifact'])}
        if not result.get('message_id') or not result.get('source_verified',True):raise ValueError('Delivery receipt is incomplete')
        return {'success':True,'result':'The requested artifact was delivered with a verified provider receipt. '+json.dumps(result)}
    raise ValueError('Unknown workflow step')
