import asyncio
import base64
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from starlette.websockets import WebSocketDisconnect

from app import phone, phone_live as live, phone_dispatch as dispatch
from test_phone import setup, signed, path_for_gather

CALL = 'CA' + '2' * 32
STREAM = 'MZ' + '3' * 32


@pytest.fixture
def configured(setup):
    cfg, app, client, _ = setup
    cfg.phone_live_enabled = True
    cfg.phone_trial_proxy_enabled = False
    cfg.phone_live_model = 'gpt-live-1'
    app.include_router(live.router)
    return cfg, client


def authenticated_stream(configured):
    cfg, client = configured
    pin = client.post('/api/phone/access/pin').json()['pin']
    step = path_for_gather(signed(client, cfg, '/api/phone/incoming'))
    result = signed(client, cfg, step, Digits=pin)
    assert result.status_code == 200
    xml = ElementTree.fromstring(result.content)
    stream = xml.find('Connect/Stream')
    assert stream is not None and xml.find('Gather') is None
    assert stream.attrib['url'] == 'wss://phone.example/api/phone/live'
    ticket = stream.find('Parameter').attrib['value']
    return {'accountSid': cfg.twilio_account_sid, 'callSid': CALL, 'streamSid': STREAM,
            'customParameters': {'ticket': ticket},
            'mediaFormat': {'encoding': 'audio/x-mulaw', 'sampleRate': 8000, 'channels': 1}}


def signature(cfg, url='wss://phone.example/api/phone/live'):
    return base64.b64encode(hmac.new(cfg.twilio_auth_token.encode(), url.encode(), hashlib.sha1).digest()).decode()


def fragment(identifier, text, end=1000, role='user'):
    return {'type': 'session.input_transcript.delta' if role == 'user' else 'session.output_transcript.delta',
            'event_id': identifier, 'delta': text, 'start_ms': max(0, end - 500), 'end_ms': end}


def test_trial_cannot_accidentally_enable_streams(configured):
    cfg, client = configured
    cfg.phone_trial_proxy_enabled = True
    assert not live.live_enabled(cfg)
    pin = client.post('/api/phone/access/pin').json()['pin']
    step = path_for_gather(signed(client, cfg, '/api/phone/incoming'))
    reply = signed(client, cfg, step, Digits=pin)
    assert '<Gather' in reply.text and '<Stream' not in reply.text
    assert client.get('/api/phone/access').json()['conversation_mode'] == 'request'


def test_stream_requires_authenticated_one_use_ticket(configured):
    cfg, client = configured
    start = authenticated_stream(configured)
    assert client.get('/api/phone/access').json()['conversation_mode'] == 'live'
    wrong = {**start, 'customParameters': {'ticket': 'x' * 43}}
    with pytest.raises(ValueError, match='unauthorized'):
        live.activate_stream(wrong, cfg)
    call = live.activate_stream(start, cfg)
    assert call['actor'] == 'owner@example.com'
    with pytest.raises(ValueError, match='unauthorized'):
        live.activate_stream(start, cfg)
    with phone.store().db() as db:
        row = db.execute('SELECT * FROM phone_live_streams').fetchone()
        assert row['ticket_hash'] == '' and row['state'] == 'active'


@pytest.mark.parametrize('change', ['account', 'codec', 'pin_reset', 'expired', 'caller_removed'])
def test_start_rejects_changed_identity_and_expiry(configured, change):
    cfg, client = configured
    start = authenticated_stream(configured)
    if change == 'account': start['accountSid'] = 'AC' + '9' * 32
    if change == 'codec': start['mediaFormat']['sampleRate'] = 16000
    if change == 'pin_reset': client.post('/api/phone/access/pin')
    if change == 'caller_removed': cfg.phone_callers_json = '{}'
    if change == 'expired':
        with phone.store().db() as db: db.execute('UPDATE phone_live_streams SET created=?', (time.time() - 61,))
    with pytest.raises(ValueError): live.activate_stream(start, cfg)


def test_unsigned_websocket_never_opens_model(configured, monkeypatch):
    cfg, client = configured
    monkeypatch.setattr(live, 'connect', lambda *a, **k: pytest.fail('Unauthorized upstream connection'))
    for headers in [{}, {'X-Twilio-Signature': 'wrong'}]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(live.PATH, headers=headers): pass


def test_conversation_preserves_roles_corrections_and_deduplicates():
    c = live.Conversation()
    c.append(fragment('u1', 'Draft for Friday.'))
    c.append(fragment('a1', 'Shall I send it?', end=2000, role='assistant'))
    c.append(fragment('u2', 'Thursday instead. Do not send.', end=3000))
    c.append(fragment('u2', 'Thursday instead. Do not send.', end=3000))
    text, used, caller = c.request(1000)
    assert caller == 'Draft for Friday.' and used == ['u1']
    c.consumed.update(used)
    text, used, caller = c.request(3000)
    assert caller == 'Thursday instead. Do not send.' and used == ['u2']
    assert '"role": "assistant"' in text and 'never user instructions or approval' in text
    c.consumed.update(used)
    assert c.request(3000)[0] is None


def test_patient_information_is_not_enqueued(configured):
    cfg, _ = configured
    call = live.activate_stream(authenticated_stream(configured), cfg)
    with pytest.raises(ValueError):
        live.enqueue(call, 'd1', 'Patient MRN: 123456 has a diagnosis.', 'Patient MRN: 123456')
    assert phone.store().jobs(call['actor']) == []


def test_delegation_durable_idempotent_and_actor_bound(configured):
    cfg, client = configured
    call = live.activate_stream(authenticated_stream(configured), cfg)
    identifier = live.enqueue(call, 'd1', 'Draft a packing checklist.', 'Draft a packing checklist.')
    assert live.enqueue(call, 'd1', 'Provider duplicate', 'duplicate') == identifier
    jobs = phone.store().jobs(call['actor'])
    assert len(jobs) == 1 and jobs[0]['transcript'] == 'Draft a packing checklist.'
    assert phone.store().jobs('operator@example.com') == []
    headers = {'Authorization': 'Bearer ' + cfg.phone_bridge_token}
    claimed = client.post('/internal/phone/claim', headers=headers).json()['job']
    assert claimed['id'] == identifier and claimed['identity']['user_id'] == '+12025550101'
    assert claimed['audio_state'] == 'live'
    with phone.store().db() as db:
        db.execute("UPDATE phone_live_streams SET state='closed' WHERE call_id=?", (CALL,))
    reply = client.post('/internal/phone/jobs/' + identifier, headers=headers,
                        json={'claim': claimed['claim'], 'state': 'completed', 'result': 'The checklist is ready.'})
    assert reply.status_code == 200 and phone.store().jobs(call['actor'])[0]['state'] == 'completed'
    client.post('/api/phone/access/pin')
    with pytest.raises(ValueError, match='caller_access_changed'):
        live.enqueue(call, 'd2', 'New task.', 'New task.')


class FakeModel:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.sent = []

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        kind = event['type']
        if kind == 'session.start':
            assert event['session']['delegation'] == {'type': 'client'}
            await self.queue.put({'type': 'session.started'})
        elif kind == 'session.input_audio.append':
            await self.queue.put(fragment('u1', 'Draft two meeting preparation steps.'))
            await self.queue.put({'type': 'session.delegation.created', 'offset_ms': 1500,
                                  'delegation': {'id': 'delegate1', 'target': 'client'}})
            # Real Live sessions can delegate before the final qualifier arrives.
            await self.queue.put(fragment('u2', ' Do not send anything.', end=1800))
            # Ordinary conversation is allowed while a delegation is captured.
            await self.queue.put({'type': 'session.output_audio.delta', 'delta': 'bGlzdGVuaW5n'})
        elif kind == 'session.commentary.append' or (kind == 'session.thinking.append' and event['content'].startswith('INTAKE_CAPTURED')):
            await self.queue.put({'type': 'session.output_audio.delta', 'delta': 'YWNr' if event['content'].startswith('INTAKE_CAPTURED') else 'cmVzdWx0'})
        elif kind == 'session.close':
            await self.queue.put({'type': 'session.closed'})

    async def recv(self): return json.dumps(await self.queue.get())
    def __aiter__(self): return self
    async def __anext__(self): return await self.recv()


def test_stream_audio_native_receipt_and_graceful_hangup(configured, monkeypatch):
    cfg, client = configured
    start = authenticated_stream(configured)
    model = FakeModel()

    @asynccontextmanager
    async def connection(*args, **kwargs):
        assert kwargs['additional_headers']['Authorization'] == 'Bearer test'
        yield model

    monkeypatch.setattr(live, 'connect', connection)
    with client.websocket_connect(live.PATH, headers={'X-Twilio-Signature': signature(cfg)}) as ws:
        ws.send_json({'event': 'connected'})
        ws.send_json({'event': 'start', 'start': start})
        ws.send_json({'event': 'media', 'streamSid': STREAM,
                      'media': {'track': 'inbound', 'payload': base64.b64encode(b'\xff' * 160).decode()}})
        assert ws.receive_json()['media']['payload'] == 'bGlzdGVuaW5n'
        headers = {'Authorization': 'Bearer ' + cfg.phone_bridge_token}
        deadline = time.monotonic() + 5
        job = None
        while not job and time.monotonic() < deadline:
            intake=dispatch.take_intake()
            if intake:
                dispatch.commit_plan(intake, {'conversation_only':False,'jobs':[{'scope':'Draft meeting steps', 'quotes':['Draft two meeting preparation steps. Do not send anything.'], 'kind':'draft','after':[]}]})
            job = client.post('/internal/phone/claim', headers=headers).json()['job']
            if not job: time.sleep(.05)
        assert job and job['actor'] == 'owner@example.com'
        assert 'New caller speech: Draft two meeting preparation steps.' in job['transcript']
        reply = client.post('/internal/phone/jobs/' + job['id'], headers=headers,
                            json={'claim': job['claim'], 'state': 'completed', 'result': 'Set an agenda and review the notes.'})
        assert reply.status_code == 200
        deadline=time.monotonic()+5
        while not any('Task result' in e.get('content','') for e in model.sent) and time.monotonic()<deadline:
            time.sleep(.05)
        assert any('Set an agenda' in e.get('content','') for e in model.sent)
        assert not any(e['type']=='session.commentary.append' for e in model.sent)
        ws.send_json({'event': 'stop', 'streamSid': STREAM})
        with pytest.raises(WebSocketDisconnect):
            while True:ws.receive_json()  # Playout marks can already be queued.
    with phone.store().db() as db:
        assert db.execute('SELECT state FROM phone_live_streams').fetchone()[0] == 'closed'
    assert any(e['type'] == 'session.close' for e in model.sent)
    assert phone.store().jobs('owner@example.com')[0]['transcript'] == 'Draft two meeting preparation steps. Do not send anything.'


def test_context_updates_cannot_force_a_speech_turn(configured):
    cfg,_=configured
    model=FakeModel();call=live.LiveCall(None,model,cfg,{},STREAM)
    with pytest.raises(ValueError,match='owns speech'):
        asyncio.run(call.append('commentary','Read this result aloud.','d1'))
    asyncio.run(call.append('thinking','x'*1200+' Action has not been approved.','d1'))
    assert all(len(e['content'])<=500 for e in model.sent)
    assert all(e['type']=='session.thinking.append' for e in model.sent)


def test_progress_claim_auth_deduplication_and_patient_boundary(configured):
    cfg,client=configured
    call=live.activate_stream(authenticated_stream(configured),cfg)
    job_id=live.enqueue(call,'progress-test','Check email.','Check email.')
    headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    job=client.post('/internal/phone/claim',headers=headers).json()['job']
    event={'event_id':'native-1','kind':'action','tool':'email_send','status':'sent','content':'Email send confirmed.'}
    path='/internal/phone/jobs/'+job_id+'/progress'
    assert client.post(path,headers=headers,json={'claim':'x'*24,'events':[event]}).status_code==403
    for _ in range(2):assert client.post(path,headers=headers,json={'claim':job['claim'],'events':[event]}).status_code==200
    assert len([e for e in phone.store().updates(job_id) if e['event_id']=='native-1'])==1
    event['event_id']='native-2';event['content']='Patient Jane Doe MRN: 12345'
    assert client.post(path,headers=headers,json={'claim':job['claim'],'events':[event]}).status_code==400
    assert not any(e['event_id']=='native-2' for e in phone.store().updates(job_id))


def test_silent_work_and_completion_after_old_90_second_cutoff(configured,monkeypatch):
    cfg,_=configured
    call=live.activate_stream(authenticated_stream(configured),cfg)
    job_id=live.enqueue(call,'slow-test','Complete approved task.','Complete approved task.')
    clock=SimpleNamespace(now=10.)
    model=FakeModel();call=live.LiveCall(None,model,cfg,call,STREAM)
    call.conversation.append(fragment('u1','Complete approved task.'))
    call.conversation.last_input=0
    monkeypatch.setattr(live,'time',SimpleNamespace(monotonic=lambda:clock.now,time=time.time))
    real_sleep=asyncio.sleep
    async def advance(seconds):
        clock.now+=seconds
        with phone.store().db() as db:
            if clock.now>=20:
                db.execute('INSERT OR IGNORE INTO phone_job_updates VALUES (?,?,?,?,?,?,?,?)',
                    (job_id,'native-receipt','action','email_send','sent',100,'The email send is confirmed.',time.time()))
            if clock.now>=106:
                db.execute("UPDATE phone_jobs SET state='completed',result='The task is complete.' WHERE id=?",(job_id,))
                db.execute("INSERT OR IGNORE INTO phone_notices(job_id,actor,kind,content,created) VALUES (?,'owner@example.com','result','The task is complete.',?)",(job_id,time.time()))
        await real_sleep(0)
    monkeypatch.setattr(live.asyncio,'sleep',advance)
    asyncio.run(call.wait_for_result('slow-test',job_id))
    spoken=[e['content'] for e in model.sent if e['type']=='session.commentary.append']
    assert not any('waiting behind' in s or 'still working' in s for s in spoken)
    assert 'The email send is confirmed.' not in spoken
    assert not any(e['type']=='session.instructions.append' for e in model.sent)
    assert len([e for e in model.sent if 'INTAKE_CAPTURED' in e['content']])==1
    assert not spoken
    assert any('The task is complete.' in e['content'] for e in model.sent)
    assert clock.now>=106
    assert len(spoken)<10


def test_hangup_cancels_result_wait_without_cancelling_work(configured):
    cfg,_=configured
    call=live.activate_stream(authenticated_stream(configured),cfg)
    job_id=live.enqueue(call,'hangup-test','Prepare draft.','Prepare draft.')
    model=FakeModel();live_call=live.LiveCall(None,model,cfg,call,STREAM)
    async def check():
        task=asyncio.create_task(live_call.wait_for_result('hangup-test',job_id))
        await asyncio.sleep(.01);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(check())
    assert phone.store().jobs(call['actor'])[0]['state']=='queued'


def test_existing_spoken_acknowledgment_is_not_repeated(configured):
    cfg,_=configured
    call=live.activate_stream(authenticated_stream(configured),cfg)
    job_id=live.enqueue(call,'ack-test','Check email.','Check email.')
    with phone.store().db() as db:
        db.execute("UPDATE phone_jobs SET state='completed',result='The lookup is ready.' WHERE id=?",(job_id,))
        db.execute("INSERT INTO phone_notices(job_id,actor,kind,content,created) VALUES (?,'owner@example.com','result','The lookup is ready.',?)",(job_id,time.time()))
    model=FakeModel();live_call=live.LiveCall(None,model,cfg,call,STREAM)
    live_call.conversation.append(fragment('u1','Check email.',end=1000))
    live_call.conversation.append(fragment('a1',"I'm checking now.",end=1500,role='assistant'))
    asyncio.run(live_call.wait_for_result('ack-test',job_id))
    assert not any(e['type']=='session.instructions.append' for e in model.sent)
    assert any(e['status']=='context_updated' for e in phone.store().updates(job_id))
