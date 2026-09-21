"""One explicitly hosted invitation, guarded by a durable root-task attempt."""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from email.utils import parseaddr
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo
from . import operations,performance,reads,effects


def escape(value):
    return value.replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def fold(line):
    # RFC 5545 folds at 75 octets without splitting a UTF-8 code point.
    out=[];part=''
    for char in line:
        if len((part+char).encode())>75:out.append(part);part=' '
        part+=char
    return '\r\n'.join(out+[part])


def invitation(root,title,start,end,organizer,recipients):
    stamp=lambda dt:dt.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//PracticeOps//Eli//EN','CALSCALE:GREGORIAN','METHOD:REQUEST',
           'BEGIN:VEVENT','UID:'+hashlib.sha256(root.encode()).hexdigest()+'@practiceops.ai',
           'DTSTAMP:'+stamp(datetime.now(timezone.utc)),'DTSTART:'+stamp(start),'DTEND:'+stamp(end),
           'SUMMARY:'+escape(title),'ORGANIZER:mailto:'+organizer,'SEQUENCE:0','STATUS:CONFIRMED']
    lines+=['ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:'+x for x in recipients]
    return ('\r\n'.join(fold(x) for x in lines+['END:VEVENT','END:VCALENDAR'])+'\r\n').encode()


def connector(slug,args,invoke=None):
    account='googlecalendar_move-rung'
    if invoke:return reads.unwrap(invoke(slug,args,account))
    from tools.registry import registry
    names=[n for n in registry.get_all_tool_names() if n.upper().endswith('COMPOSIO_MULTI_EXECUTE_TOOL')]
    if len(names)!=1:raise RuntimeError('Calendar connector unavailable')
    return reads.unwrap(operations.native_call(names[0],{'tools':[{'tool_slug':slug,'arguments':args,'account':account}],
        'sync_response_to_workbench':False,'current_step':'REQUESTED_PHONE_CALENDAR_INVITATION'}))


def run(job,settings,perf,*,services=None,invoke=None,calendar_call=None,config=None,now=None):
    plan=job.get('plan') or {}
    if isinstance(plan,str):plan=json.loads(plan)
    spec=plan['calendar'];root=job.get('root_id') or job['id']
    source=job['transcript'].rsplit('New caller speech: ',1)[-1];quote=spec.get('approval_quote','')
    confirmed_title=any(spec['title'].casefold() in h.get('spoken_prompt','').casefold()
        and h.get('answer') and h['answer'] in quote
        and re.fullmatch(r"\s*(?:(?:yes|yeah|yep|correct|right|exactly|that['’]s correct|that['’]s right|that is correct|okay|ok)[,.!\s]*)+",h['answer'],re.I)
        for h in spec.get('confirmed_proposals',[]))
    if job.get('identity')!=settings.get('identities',{}).get(job['actor']):raise PermissionError('Identity mismatch')
    if (plan.get('operation')!='calendar_invitation' or spec.get('organizer') not in {'eli','principal'}
        or not quote or quote not in source or (spec['title'].casefold() not in quote.casefold() and not confirmed_title)
        or re.search(operations.PATIENT,quote,re.I)
        or re.search(r"\b(?:do not|don't|never)\s+(?:send|invite|create|schedule)|\bcancel\b",quote,re.I)):
        raise ValueError('Invitation lacks caller evidence')
    address=spec['recipient']
    email=lambda x:bool(re.fullmatch(r'[^\s@,;:]+@[^\s@,;:]+\.[^\s@,;:]+',x))
    names=[i.get('name','').split() for a,i in settings.get('identities',{}).items() if a.casefold()==address.casefold()]
    if not email(address) or not (address.casefold() in quote.casefold() or any(
        re.search(r'\b'+re.escape(n)+r'\b',quote,re.I) for parts in names for n in parts if n.lower() not in {'dr','dr.','doctor'})):
        raise ValueError('Invitation recipient lacks caller evidence')
    start=datetime.fromisoformat(spec['date']+'T'+spec['time'])
    if start.tzinfo:raise ValueError('Expected local wall time')
    start=start.replace(tzinfo=ZoneInfo(spec['timezone']))
    if start.utcoffset()!=start.replace(fold=1).utcoffset():raise ValueError('Ambiguous daylight-saving time; clarify the exact time')
    if start.astimezone(timezone.utc).astimezone(start.tzinfo)!=start:raise ValueError('Invalid daylight-saving time')
    duration=int(spec['duration_minutes'])
    if not 1<=duration<=1440:raise ValueError('Invalid invitation duration')
    end=start+timedelta(minutes=duration)
    if config is None and spec['organizer']=='principal':
        from hermes_cli.config import load_config
        config=load_config()
    if spec['organizer']=='principal' and not reads.principal(job['identity']['user_id'],config):
        return {'success':False,'state':'blocked','error':"This caller is not authorized to create events on Dr. Shaye's calendar. Nothing was created. Dr. Shaye can request it directly, or explicitly choose Eli's invitation."}
    blocked=performance.before_tool(settings,tool_name='eli_phone_calendar_invitation',args=spec)
    if blocked and blocked.get('block'):return {'success':False,'state':'blocked','error':blocked['message']}
    with perf.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS phone_calendar_receipts(root_id TEXT PRIMARY KEY,payload TEXT,receipt TEXT,created REAL)')
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT receipt FROM phone_calendar_receipts WHERE root_id=?',(root,)).fetchone()
        if old:return {**json.loads(old[0]),'already_attempted_for_this_request':True}
        if start.timestamp()< (time.time() if now is None else now):
            return {'success':False,'state':'failed','error':'The requested event time has already passed. Confirm a new date before sending.'}
        receipt={'success':False,'state':'uncertain','error':'This invitation attempt requires reconciliation; do not send it again.'}
        db.execute('INSERT INTO phone_calendar_receipts VALUES (?,?,?,?)',(root,json.dumps(spec),json.dumps(receipt),time.time()))
    def save():
        with perf.db() as db:db.execute('UPDATE phone_calendar_receipts SET receipt=? WHERE root_id=?',(json.dumps(receipt),root))
    try:
        if spec['organizer']=='eli':
            svc=services or operations.mail_services();call=invoke or operations.native_call
            organizer=svc.settings.effective_from_address
            principals=list(svc.settings.principal_addresses)
            # The native mail identity uses principal_addresses[0] for cc_principal;
            # remaining addresses are aliases, not additional meeting attendees.
            if not email(organizer) or not principals or not email(principals[0]):raise ValueError('Principal invitation recipient is not configured')
            recipients=list(dict.fromkeys([principals[0],address]))
            directory=perf.path.parent/'calendar-invitations'/hashlib.sha256(root.encode()).hexdigest()
            directory.mkdir(parents=True,exist_ok=True);path=directory/'invitation.ics'
            data=invitation(root,spec['title'],start,end,organizer,recipients);path.write_bytes(data)
            sent=call('email_send',{'to':recipients,'subject':spec['title'],'text':
                'Calendar invitation: '+spec['title']+'\n'+start.isoformat()+' to '+end.isoformat()+' ('+spec['timezone']+').',
                'attachments':[str(path)],'mandate':'Send this one explicitly requested calendar invitation once. No reminders or follow-up authorized.',
                'success_condition':'Provider receipt and read-back confirm the invitation and both recipients; close tracking.',
                'summary':'One-time caller-requested calendar invitation.'})
            if not sent.get('message_id'):raise ValueError('Provider returned no invitation receipt')
            receipt.update(message_id=sent['message_id'],recipients=recipients,organizer=organizer);save()
            # Cleanup never retries the send and cannot change a verified receipt.
            receipt['tracking_closed']=False
            try:
                closed=call('email_registry',{'action':'thread_close','thread_id':sent['thread_id'],'summary':'One invitation sent. No follow-ups.'})
                task=call('email_registry',{'action':'task_update','task_id':sent['task']['task_id'],'changes':{'status':'done','plan':'One invitation; no follow-ups.'}})
                receipt['tracking_closed']=bool(closed.get('success') and task.get('success'))
            except Exception:pass
            fetched=svc.mail.get_message(sent['message_id'])
            matches=[a for a in fetched.get('attachments',[]) if a.get('filename')=='invitation.ics' and a.get('attachment_id')]
            verified=(fetched.get('message_id')==sent['message_id'] and fetched.get('subject')==spec['title']
                and {parseaddr(x)[1].casefold() for x in fetched.get('to',[])}=={x.casefold() for x in recipients} and len(matches)==1)
            if verified:
                downloaded=svc.mail.download_attachment(sent['message_id'],matches[0]['attachment_id'],directory/'verified','invitation.ics')
                verified=Path(downloaded).read_bytes()==data
            provider=sent['message_id']
        else:
            args={'calendar_id':'primary','summary':spec['title'],'start_datetime':start.replace(tzinfo=None).isoformat(),
                  'end_datetime':end.replace(tzinfo=None).isoformat(),'timezone':spec['timezone'],
                  'attendees':[address],'send_updates':'all','create_meeting_room':False}
            sent=connector('GOOGLECALENDAR_CREATE_EVENT',args,calendar_call)
            if not sent.get('id'):raise ValueError('Calendar returned no event receipt')
            provider=sent['id'];receipt.update(event_id=provider,recipients=[address]);save()
            fetched=connector('GOOGLECALENDAR_EVENTS_GET',{'calendar_id':'primary','event_id':provider},calendar_call)
            verified=(fetched.get('id')==provider and fetched.get('summary')==spec['title'] and fetched.get('status')=='confirmed'
                and {a['email'].casefold() for a in fetched.get('attendees',[])}=={address.casefold()}
                and datetime.fromisoformat(fetched['start']['dateTime'])==start
                and datetime.fromisoformat(fetched['end']['dateTime'])==end)
        if verified:
            effects.verified_provider(perf,job,provider)
            receipt.update(success=True,state='sent',source_verified=True);receipt.pop('error',None)
            perf.record(job['id'],'action','eli_phone_calendar_invitation','verified',
                content='The requested calendar invitation has a verified provider receipt.',fingerprint=hashlib.sha256(provider.encode()).hexdigest())
        else:receipt['error']='Invitation accepted, but its details could not be verified. Do not send another invitation.'
    except Exception as exc:
        receipt['error_type']=type(exc).__name__
    save()
    return receipt
