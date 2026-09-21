"""Explicit phone-request WhatsApp delivery through the existing native transport."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


def normalize(value):
    return ' '.join(str(value).casefold().split())


def send_whatsapp(args, settings, *, session=None, home=None, sender=None):
    return send_message(args, settings, channel='whatsapp', session=session, home=home, sender=sender)


def send_imessage(args, settings, *, session=None, home=None, sender=None, available=None):
    return send_message(args, settings, channel='imessage', session=session, home=home, sender=sender, available=available)


def imessage_available(home):
    try:
        state = json.loads((Path(home)/'gateway_state.json').read_text())
        return state.get('platforms',{}).get('bluebubbles',{}).get('state') == 'connected'
    except (OSError, ValueError):
        return False


def imessage_sender(args):
    # Explicit iMessage DM GUID prevents group/SMS fallback. Reuse the native
    # transport and its outbound response guard, not a second sending service.
    from gateway.config import Platform, load_gateway_config
    from model_tools import _run_async
    from tools.send_message_tool import _send_to_platform
    cfg = load_gateway_config().platforms.get(Platform('bluebubbles'))
    if not cfg or not cfg.enabled:
        return {'success': False, 'error': 'iMessage is not connected'}
    return _run_async(_send_to_platform(Platform('bluebubbles'),cfg,
        'iMessage;-;'+args['target'].split(':',1)[1],args['message']))


def send_message(args, settings, *, channel, session=None, home=None, sender=None, available=None):
    if session is None:
        from gateway.session_context import get_session_env
        session = get_session_env
    if home is None:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
    home = Path(home)
    user = session('HERMES_SESSION_USER_ID', '')
    request_id = session('HERMES_SESSION_MESSAGE_ID', '')
    if session('HERMES_SESSION_PLATFORM', '') != 'eli_phone' or session('HERMES_SESSION_CHAT_TYPE', '') != 'dm':
        return {'success': False, 'error': 'An authenticated direct phone request is required.'}
    identity = next(((actor, item) for actor, item in settings.get('identities', {}).items()
                     if item.get('user_id') == user), None)
    if not identity or not request_id:
        return {'success': False, 'error': 'Phone caller is not authorized.'}
    recipient = str(args.get('recipient', '')).strip()
    message = str(args.get('message', '')).strip()
    quote = str(args.get('approval_quote', '')).strip()
    if (not re.fullmatch(r'\+[1-9][0-9]{7,14}', recipient) or not 1 <= len(message) <= 1800
            or not 8 <= len(quote) <= 6000 or '\x00' in message
            or re.search(r'MEDIA:|\[\[as_document\]\]|\bmrn\b|medical record number|date of birth|\bdob\s*[:#]|patient\s+\w+\s+\w+|\bdiagnos(?:is|ed|es)\b|\bicd-?10\b|pathology report|lab result', message, re.I)):
        return {'success': False, 'error': 'A short non-patient text, exact number, and explicit caller instruction are required.'}
    db = sqlite3.connect(home / 'state/eli-phone.sqlite3', timeout=5)
    try:
        row = db.execute('SELECT payload,state FROM work WHERE id=?', (request_id,)).fetchone()
        if not row or row[1] != 'running':
            return {'success': False, 'error': 'There is no active native phone request for this action.'}
        job = json.loads(row[0])
        if job.get('actor') != identity[0] or job.get('identity') != identity[1]:
            return {'success': False, 'error': 'Request identity does not match the caller.'}
        transcript = job.get('transcript', '')
        fresh = transcript.rsplit('New caller speech: ', 1)[-1] if 'New caller speech: ' in transcript else transcript
        normalized = normalize(fresh)
        if (normalize(quote) not in normalized
                or not re.search(r'(?<!\w)' + re.escape(normalize(message)) + r'(?!\w)', normalize(quote))
                or (channel == 'whatsapp' and not re.search(r'\bwhats\s*app\b', quote, re.I))
                or (channel == 'imessage' and (not re.search(r'\b(?:text|imessage)\b',quote,re.I)
                    or re.search(r'\b(?:whats\s*app|sms|email)\b',quote,re.I)))
                or not re.search(r'\b(send|text|message|tell)\b', quote, re.I)
                or re.search(r"\b(?:do not|don't|dont|never)\s+(?:send|text|message)|\bcancel\b", fresh, re.I)):
            return {'success': False, 'error': 'The current caller must explicitly request this exact message. Earlier assistant speech is not approval.'}
        names = [part for item in settings.get('identities', {}).values() if item.get('phone') == recipient
                 for part in str(item.get('name', '')).split() if part.casefold() not in {'dr.', 'dr', 'doctor'}]
        named = any(re.search(r'\b' + re.escape(name) + r'\b', quote, re.I) for name in names)
        if not named and recipient.lstrip('+') not in re.sub(r'\D', '', quote):
            return {'success': False, 'error': 'Ask the caller to name the authorized contact or repeat the exact recipient number.'}
        digest = hashlib.sha256(((job.get('root_id') or request_id)+'\0'+channel+'\0'+recipient+'\0'+message).encode()).hexdigest()
        db.execute('CREATE TABLE IF NOT EXISTS message_receipts(id TEXT PRIMARY KEY,request_id TEXT,recipient TEXT,message TEXT,approval_quote TEXT,state TEXT,receipt TEXT,created REAL,updated REAL)')
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT state,receipt FROM message_receipts WHERE id=?', (digest,)).fetchone()
        if old:
            db.rollback()
            if old[0] == 'sent':
                return {**json.loads(old[1]), 'already_sent_for_this_request': True}
            return {'success': False, 'state': old[0], 'error': 'This exact attempt needs reconciliation; do not resend automatically.'}
        if channel == 'imessage' and not (available(home) if available else imessage_available(home)):
            db.rollback()
            return {'success': False, 'state': 'unavailable', 'pending': True,
                    'error': 'iMessage is disconnected. The request remains in the phone task history, but nothing was sent. Reconnect iMessage and explicitly resume this request; do not substitute WhatsApp or SMS.'}
        db.execute('INSERT INTO message_receipts VALUES (?,?,?,?,?,?,?,?,?)',
                   (digest, request_id, recipient, message, quote, 'sending', '{}', time.time(), time.time()))
        db.commit()
        try:
            if sender is None:
                if channel == 'imessage':
                    sender = imessage_sender
                else:
                    from tools.send_message_tool import send_message_tool
                    sender = send_message_tool
            result = sender({'action': 'send', 'target': channel+':'+recipient, 'message': message})
            if isinstance(result, str):
                result = json.loads(result)
            if not isinstance(result, dict):
                raise ValueError('invalid_transport_receipt')
            sent = result.get('success') is True and bool(result.get('message_id'))
            receipt = {'success': sent, 'state': 'sent' if sent else 'uncertain',
                       'request_id': request_id, 'recipient': recipient, 'message_id': result.get('message_id'),
                       'sent_at': time.time() if sent else None}
            if not sent:
                receipt['error'] = 'The transport did not provide a successful message receipt. Review before repeating.'
        except Exception as exc:
            receipt = {'success': False, 'state': 'uncertain', 'error': 'Delivery could not be confirmed; do not retry automatically.',
                       'error_type': type(exc).__name__}
        db.execute('UPDATE message_receipts SET state=?,receipt=?,updated=? WHERE id=?',
                   (receipt['state'], json.dumps(receipt), time.time(), digest))
        db.commit()
        return receipt
    finally:
        db.close()
