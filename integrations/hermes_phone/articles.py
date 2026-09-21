"""Bounded article selection. Retrieved text is data, never sending authority."""
import json
import re
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET


def select(query,selection='latest',fetch=None):
    url='https://news.google.com/rss/search?'+urlencode({'q':query,'hl':'en-US','gl':'US','ceid':'US:en'})
    if fetch:raw=fetch(url)
    else:
        with urlopen(Request(url,headers={'User-Agent':'Eli-Article-Lookup/1.0'}),timeout=10) as response:
            raw=response.read(512001)
    if len(raw)>512000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Invalid article feed')
    items=[]
    for node in ET.fromstring(raw).findall('./channel/item')[:100]:
        title=(node.findtext('title') or '').strip()
        link=(node.findtext('link') or '').strip()
        parsed=urlsplit(link)
        if not title or len(title)>500 or parsed.scheme!='https' or parsed.hostname!='news.google.com':continue
        try:published=parsedate_to_datetime(node.findtext('pubDate')).timestamp()
        except (TypeError,ValueError):continue
        if published>time.time()+300:continue
        # Output is a title and URL only, never executable instructions or media directives.
        if re.search(r'MEDIA:|\[\[as_document\]\]|[\x00-\x1f]',title+link):continue
        items.append({'title':title,'url':link,'published':published,'source':node.findtext('source') or ''})
    if not items:raise ValueError('No usable article was found')
    return max(items,key=lambda x:x['published']) if selection=='latest' else items[0]


def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS phone_article_artifacts(root_id TEXT PRIMARY KEY,actor TEXT,payload TEXT,created REAL)')


def channel_approved(spec,quote):
    patterns={'email':r'\be-?mail\b','imessage':r'\b(?:text|imessage)\b','whatsapp':r'\bwhats\s*app\b'}
    channel=spec['channel']
    if re.search(patterns[channel],quote,re.I):return True
    for h in spec.get('confirmed_proposals',[]):
        answer=h.get('answer','');prompt=h.get('spoken_prompt','')
        if not h.get('question_id') or not answer or answer not in quote:continue
        if not re.fullmatch(r"\s*(?:(?:yes|yeah|yep|correct|right|exactly|that['’]s correct|that['’]s right|that is correct|okay|ok)[,.!\s]*)+",answer,re.I):continue
        # "Email or WhatsApp?" followed by "yes" selects neither option.
        if {name for name,pattern in patterns.items() if re.search(pattern,prompt,re.I)}=={channel}:return True
    return False


def authorized(db,job,args,channel):
    """Only the exact immutable server-selected artifact may relax dictation."""
    plan=job.get('plan') or {}
    if isinstance(plan,str):plan=json.loads(plan)
    spec=plan.get('article',{})
    if plan.get('operation')!='find_send_article' or spec.get('channel')!=channel or not channel_approved(spec,args.get('approval_quote','')):return False
    try:row=db.execute('SELECT actor,payload FROM phone_article_artifacts WHERE root_id=?',(job.get('root_id') or job['id'],)).fetchone()
    except Exception:return False
    if not row or row[0]!=job['actor']:return False
    saved=json.loads(row[1])
    return all(saved['args'].get(k)==args.get(k) for k in ('recipient','message','approval_quote')) and saved['spec']==spec


def run(job,settings,perf,*,fetch=None,send=None):
    from . import performance,operations,messaging
    plan=job.get('plan') or {}
    if isinstance(plan,str):plan=json.loads(plan)
    spec=plan['article'];source=job['transcript'].rsplit('New caller speech: ',1)[-1]
    quote=spec['approval_quote'];channel=spec['channel'];root=job.get('root_id') or job['id']
    if (plan.get('operation')!='find_send_article' or channel not in {'email','imessage','whatsapp'}
        or not quote or quote not in source or not spec.get('query')
        or not channel_approved(spec,quote)
        or not re.search(r'\b(article|link)\b',quote,re.I)
        or not re.search(r'\b(send|email|text|share)\b',quote,re.I)):
        raise ValueError('Article selection lacks caller evidence')
    with perf.db() as db:
        init(db);old=db.execute('SELECT payload FROM phone_article_artifacts WHERE root_id=?',(root,)).fetchone()
    if old:
        saved=json.loads(old[0])
        if saved['spec']!=spec:raise ValueError('Existing article must be reconciled before changing delivery')
    else:
        began=time.monotonic()
        try:item=select(spec['query'],spec.get('selection','latest'),fetch)
        except Exception:
            perf.record(job['id'],'timing','article_lookup','failed',round((time.monotonic()-began)*1000))
            return {'success':False,'state':'failed','error':'The article lookup did not return a usable result. No message was sent.'}
        perf.record(job['id'],'timing','article_lookup','ok',round((time.monotonic()-began)*1000))
        args={'recipient':spec['recipient'],'message':item['title']+'\n'+item['url'],'approval_quote':quote}
        saved={'spec':spec,'article':item,'args':args}
        with perf.db() as db:
            db.execute('INSERT OR IGNORE INTO phone_article_artifacts VALUES (?,?,?,?)',(root,job['actor'],json.dumps(saved),time.time()))
            saved=json.loads(db.execute('SELECT payload FROM phone_article_artifacts WHERE root_id=?',(root,)).fetchone()[0])
    args=saved['args'];name='eli_phone_send_'+channel
    blocked=performance.before_tool(settings,tool_name=name,args=args)
    if blocked and blocked.get('block'):return {'success':False,'error':blocked['message']}
    started=time.monotonic()
    if send:result=send(channel,args)
    elif channel=='email':result=operations.send_email(args,settings)
    else:result=messaging.send_message(args,settings,channel=channel)
    performance.after_tool(settings,tool_name=name,args=args,result=result,duration_ms=round((time.monotonic()-started)*1000))
    return {**result,'article':saved['article']}
