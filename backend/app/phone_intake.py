"""Resolve message references into a complete, source-backed task at intake."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError


CHANNELS={'email':r'\be-?mail\b','imessage':r'\b(?:text|imessage)\b','whatsapp':r'\bwhats\s*app\b'}


def normalized(value):
    return ' '.join(value.casefold().split())


def contact(mention,contacts,channel):
    matches=[]
    for email,entry in contacts.items():
        aliases={normalized(email),normalized(entry.get('phone','')),normalized(entry.get('name',''))}
        aliases.update(normalized(part) for part in entry.get('name','').split() if part.lower() not in {'dr','dr.','doctor'})
        if normalized(mention) in aliases:matches.append(email if channel=='email' else entry['phone'])
    if len(set(matches))==1:return matches[0]
    if channel=='email' and re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+',mention):return mention
    if channel!='email' and re.fullmatch(r'\+[1-9][0-9]{7,14}',mention):return mention
    return None


def prepare_task(task,contacts):
    kind=task['kind']
    if kind not in {'calendar','article'}:return message_plan(task,contacts)
    details=task.get('details',{})
    details={**details,**{k:details[k].strip().casefold() for k in ('channel','organizer','selection') if k in details}}
    source='\n'.join(task['quotes'])
    mention=task.get('recipient','')
    if task.get('question'):return {},task['question']
    if not mention or normalized(mention) not in normalized(source):return {},'Who should receive the '+kind+'?'
    if kind=='article':
        channel=details.get('channel')
        if channel not in CHANNELS:return {},'Should I send the article by email, WhatsApp, or iMessage?'
        if not details.get('query'):return {},'What topic should the article cover?'
        recipient=contact(mention,contacts,'email' if channel=='email' else 'phone')
        if not recipient:return {},'What exact address or number should I use for '+mention+'?'
        if not re.search(r'\b(?:article|link)\b',source,re.I) or not re.search(r'\b(?:send|email|text|share)\b',source,re.I):
            return {},'Should I find the article only, or also send its link?'
        return {'operation':'find_send_article','article':{**details,'recipient':recipient,'approval_quote':source},
                'required_receipts':[channel]},''
    organizer=details.get('organizer')
    if organizer not in {'eli','principal'}:return {},"Should I send the invitation from Eli's email or put it on Dr. Shaye's calendar? Eli's invitation includes Dr. Shaye and the guest."
    missing=[name for name in ['title','date','time','timezone','duration_minutes'] if not details.get(name)]
    if missing:return {},'For the calendar invitation, what '+', '.join(missing).replace('duration_minutes','duration')+' should I use?'
    try:
        start=datetime.fromisoformat(details['date']+'T'+details['time'])
        if start.tzinfo is not None:raise ValueError()
        ZoneInfo(details['timezone'])
        if not 1<=int(details['duration_minutes'])<=1440:raise ValueError()
    except (ValueError,ZoneInfoNotFoundError):return {},'Please confirm the event date, time, time zone, and duration.'
    if normalized(details['title']) not in normalized(source):return {},'What title should I use for the invitation?'
    recipient=contact(mention,contacts,'email')
    if not recipient:return {},'What email address should receive the calendar invitation?'
    return {'operation':'calendar_invitation','calendar':{**details,'recipient':recipient,'approval_quote':source},
            'required_receipts':['calendar']},''


def message_plan(task, contacts):
    kind=task['kind']
    if kind not in CHANNELS:return {},task.get('question','')
    question=task.get('question','').strip()
    source='\n'.join(task['quotes'])
    body=task.get('message','').strip()
    mention=task.get('recipient','').strip()
    if question:return {},question
    if not body or normalized(body) not in normalized(source):
        return {},'What message should I '+('email' if kind=='email' else 'text')+' to the recipient?'
    if not mention or normalized(mention) not in normalized(source):
        return {},'Who should receive this '+kind+' message?'
    if not re.search(CHANNELS[kind],source,re.I):
        return {},'Which messaging channel should I use?'
    recipient=contact(mention,contacts,'email' if kind=='email' else 'phone')
    if not recipient:return {},'What exact '+('email address' if kind=='email' else 'phone number')+' should I use for '+mention+'?'
    return {'operation':'send_message','message':{'recipient':recipient,'message':body,'approval_quote':source}},''
