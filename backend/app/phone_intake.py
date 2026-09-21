"""Resolve message references into a complete, source-backed task at intake."""
import re


CHANNELS={'email':r'\be-?mail\b','imessage':r'\b(?:text|imessage)\b','whatsapp':r'\bwhats\s*app\b'}


def normalized(value):
    return ' '.join(value.casefold().split())


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
    matches=[]
    for email,entry in contacts.items():
        aliases={normalized(email),normalized(entry.get('phone','')),normalized(entry.get('name',''))}
        aliases.update(normalized(part) for part in entry.get('name','').split() if part.lower() not in {'dr','dr.','doctor'})
        if normalized(mention) in aliases:matches.append(email if kind=='email' else entry['phone'])
    if len(set(matches))==1:recipient=matches[0]
    elif kind=='email' and re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+',mention):recipient=mention
    elif kind!='email' and re.fullmatch(r'\+[1-9][0-9]{7,14}',mention):recipient=mention
    else:return {},'What exact '+('email address' if kind=='email' else 'phone number')+' should I use for '+mention+'?'
    return {'operation':'send_message','message':{'recipient':recipient,'message':body,'approval_quote':source}},''
