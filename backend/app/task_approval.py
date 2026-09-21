"""Confirmation applies to one exact third-party effect, not a conversation-wide bypass."""
import hashlib
import json
import re
from .phone_intake import affirmative


def delivery_gate(task, prepared, actor, contacts, prior):
    operation=prepared.get('operation')
    field={'send_message':'message','calendar_invitation':'calendar','find_send_article':'article'}.get(operation)
    if not field:return None
    spec=prepared[field];recipient=spec.get('recipient')
    if not recipient:return None
    self_addresses={actor,contacts.get(actor,{}).get('phone')}
    if recipient in self_addresses and operation!='calendar_invitation':return None
    semantic={k:v for k,v in spec.items() if k not in {'approval_quote','confirmed_proposals'}}
    signature=hashlib.sha256(json.dumps({'operation':operation,'spec':semantic},sort_keys=True).encode()).hexdigest()
    quote='\n'.join(task['quotes'])
    if re.search(r'\b(?:just send|go ahead and send|send (?:it |them )?without asking|no need to ask)\b',quote,re.I):return None
    old=prior.get('delivery_gate') or {}
    if old.get('signature')==signature:
        for answer in prior.get('clarification_history',[]):
            if answer.get('question')==old.get('question') and (affirmative(answer.get('answer','')) or re.fullmatch(r'\s*(?:send it|go ahead|approved)[.!\s]*',answer.get('answer',''),re.I)):
                return None
    question='May I send this '+task['kind']+' to '+(task.get('recipient') or recipient)+'?'
    return {'signature':signature,'question':question}
