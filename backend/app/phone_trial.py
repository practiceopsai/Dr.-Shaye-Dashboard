"""Authenticate the trial's unsigned forwarding with scoped private URLs.

The URL capability is required in addition to an independently fetched Twilio
call record. Caller allowlisting and PIN verification remain in phone.py.
Direct Voice webhooks still use Twilio's normal signature verification.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from email.utils import parsedate_to_datetime

import httpx
from fastapi import HTTPException

log = logging.getLogger('uvicorn.error')


def reject(reason):
    # Reasons are static strings; no private URL/body values enter the log.
    log.warning('Phone webhook rejected: trial %s', reason)
    return False


def canonical_number(value):
    value = value.strip()
    return '+' + value if value.isascii() and value.isdigit() else value


def token(cfg, path, scope, expires):
    if not cfg.phone_bridge_token:
        raise HTTPException(503, 'Phone verification is not configured')
    message = json.dumps(['eli-phone-trial-v1', path, scope, expires], separators=(',', ':'))
    return hmac.new(cfg.phone_bridge_token.encode(), message.encode(), hashlib.sha256).hexdigest()


def webhook_url(base, path, cfg, scope):
    if not getattr(cfg, 'phone_trial_proxy_enabled', False):
        return base + path
    expires = 0 if scope.startswith('entry:') else int(time.time()) + 1200
    # The trial forwarder did not preserve the separate query credential fields.
    # Keep the capability in one URL-safe path segment instead.
    return base + path + f'/{expires}.{token(cfg, path, scope, expires)}'


async def validate_request(request, values, cfg, identities):
    if not getattr(cfg, 'phone_trial_proxy_enabled', False):
        return False
    query = request.query_params
    path = request.url.path
    path_key = re.fullmatch(r'(/api/phone/.+)/(0|[0-9]{10})\.([a-f0-9]{64})', path)
    # Forwarders may append routing parameters. Authenticate our three fields
    # exactly once, without requiring unrelated query parameters to disappear.
    if not path_key and any(len(query.getlist(key)) != 1 for key in ('scope', 'expires', 'token')):
        return reject('missing or repeated URL credential field')
    if path_key:
        path, expiry_text, supplied_token = path_key.groups()
    else:
        expiry_text, supplied_token = query['expires'], query['token']
    actor = None
    if path == '/api/phone/incoming':
        actor = next((actor for actor in identities
                      if hmac.compare_digest(token(cfg, path, 'entry:'+actor, 0), supplied_token)), None) if path_key else query['scope'].removeprefix('entry:')
        if actor not in identities:
            return reject('entry identity is not configured')
        if values.get('From') and canonical_number(values['From']) != identities[actor]['phone']:
            return reject('entry caller does not match link owner')
        if values.get('To') and canonical_number(values['To']) != cfg.twilio_phone_number:
            return reject('entry destination does not match')
        scope = 'entry:' + actor
    elif match := re.fullmatch(r'/api/phone/outbound/([a-f0-9]{32})/(answer|status)', path):
        scope = 'outbound:' + match[1]
    else:
        scope = 'call:' + values['CallSid']
    try:
        expires = int(expiry_text)
    except ValueError:
        return reject('invalid URL expiry')
    if not path_key and query['scope'] != scope:
        return reject('URL scope does not match call')
    if scope.startswith('entry:'):
        if expires != 0:
            return reject('invalid entry expiry')
    elif not time.time() < expires <= time.time() + 1210:
        return reject('expired continuation URL')
    if not re.fullmatch(r'[a-f0-9]{64}', supplied_token) or not hmac.compare_digest(token(cfg, path, scope, expires), supplied_token):
        return reject('URL capability does not match')

    # Never trust a body claiming to be Twilio. Confirm its exact call, account,
    # endpoints and active lifetime through the account-authenticated REST API.
    # A 2.5-second bound leaves time inside the trial's five-second webhook limit.
    try:
        async with asyncio.timeout(2.5):
            async with httpx.AsyncClient(timeout=2.5) as client:
                reply = await client.get(
                    f'https://api.twilio.com/2010-04-01/Accounts/{cfg.twilio_account_sid}/Calls/{values["CallSid"]}.json',
                    auth=(cfg.twilio_account_sid, cfg.twilio_auth_token))
        if reply.status_code != 200:
            log.warning('Phone webhook rejected: trial call lookup; http_status=%s', reply.status_code)
            raise HTTPException(503, 'Phone provider could not verify this call')
        call = reply.json()
        created = parsedate_to_datetime(call['date_created']).timestamp()
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, OverflowError) as exc:
        log.warning('Phone webhook rejected: trial call lookup; error_type=%s', type(exc).__name__)
        raise HTTPException(503, 'Phone provider could not verify this call') from None
    matches = (call.get('sid') == values['CallSid'] and call.get('account_sid') == cfg.twilio_account_sid
               and (not values.get('From') or call.get('from') == canonical_number(values['From']))
               and (not values.get('To') or call.get('to') == canonical_number(values['To']))
               and -60 <= time.time() - created <= 1200)
    if actor:
        matches = matches and call.get('from') == identities[actor]['phone'] and call.get('to') == cfg.twilio_phone_number
    if not matches:
        log.warning('Phone webhook rejected: trial call record mismatch or age limit')
        return False
    if path.endswith('/status'):
        if call.get('status') != values.get('CallStatus'):
            return reject('call status does not match provider record')
    elif call.get('status') not in {'in-progress', 'ringing', 'queued'} or call.get('end_time'):
        return reject('call is not active')
    if actor and call.get('direction') != 'inbound':
        return reject('entry call is not inbound')
    # Only provider-authenticated canonical endpoints reach PIN/session handling.
    if values.get('From') != call.get('from') or values.get('To') != call.get('to'):
        log.info('Phone trial forwarded endpoint format normalized from verified provider record')
    if set(query) - {'scope', 'expires', 'token'}:
        log.info('Phone trial extra routing parameters retained outside URL credentials')
    values['From'], values['To'] = call.get('from', ''), call.get('to', '')
    return True
