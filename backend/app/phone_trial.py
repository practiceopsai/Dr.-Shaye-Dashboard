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
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

log = logging.getLogger('uvicorn.error')


def token(cfg, path, scope, expires):
    if not cfg.phone_bridge_token:
        raise HTTPException(503, 'Phone verification is not configured')
    message = json.dumps(['eli-phone-trial-v1', path, scope, expires], separators=(',', ':'))
    return hmac.new(cfg.phone_bridge_token.encode(), message.encode(), hashlib.sha256).hexdigest()


def webhook_url(base, path, cfg, scope):
    if not getattr(cfg, 'phone_trial_proxy_enabled', False):
        return base + path
    expires = 0 if scope.startswith('entry:') else int(time.time()) + 1200
    return base + path + '?' + urlencode({'scope': scope, 'expires': expires,
                                         'token': token(cfg, path, scope, expires)})


async def validate_request(request, values, cfg, identities):
    if not getattr(cfg, 'phone_trial_proxy_enabled', False):
        return False
    query = request.query_params
    if len(query.multi_items()) != 3 or set(query) != {'scope', 'expires', 'token'}:
        return False
    path = request.url.path
    if path == '/api/phone/incoming':
        actor = next((actor for actor, entry in identities.items() if entry['phone'] == values.get('From')), None)
        if not actor or values.get('To') != cfg.twilio_phone_number:
            return False
        scope = 'entry:' + actor
    elif match := re.fullmatch(r'/api/phone/outbound/([a-f0-9]{32})/(answer|status)', path):
        scope = 'outbound:' + match[1]
    else:
        scope = 'call:' + values['CallSid']
    try:
        expires = int(query['expires'])
    except ValueError:
        return False
    if query['scope'] != scope:
        return False
    if scope.startswith('entry:'):
        if expires != 0:
            return False
    elif not time.time() < expires <= time.time() + 1210:
        return False
    if not re.fullmatch(r'[a-f0-9]{64}', query['token']) or not hmac.compare_digest(token(cfg, path, scope, expires), query['token']):
        return False

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
               and call.get('from') == values.get('From') and call.get('to') == values.get('To')
               and -60 <= time.time() - created <= 1200)
    if not matches:
        log.warning('Phone webhook rejected: trial call record mismatch or age limit')
        return False
    if path.endswith('/status'):
        return call.get('status') == values.get('CallStatus')
    if call.get('status') not in {'in-progress', 'ringing', 'queued'} or call.get('end_time'):
        log.warning('Phone webhook rejected: trial call is not active')
        return False
    if path == '/api/phone/incoming':
        return call.get('direction') == 'inbound'
    return True
