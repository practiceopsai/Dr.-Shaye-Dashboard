"""Regression cases from the two September 21 production calls."""
import asyncio
import base64
import json
import time

from app import phone, phone_live as live, phone_presence as presence
from app.phone_runtime import Runtime
from test_phone import setup
from test_phone_live import configured, authenticated_stream, STREAM, FakeModel


def test_energy_observation_cannot_latch_off_future_provider_speech(configured):
    rt = Runtime('call', phone.store())
    rt.interrupt()
    # A local noise observation must not wait for provider silence to unlock audio.
    assert rt.audio_allowed({'event_id': 'after-noise'}, True, 200, False)
    assert rt.audio_allowed({'event_id': 'during-rms-spike'}, True, 200, True)


def test_pending_delegation_cannot_clip_unrelated_conversation(configured):
    async def run():
        cfg, _ = configured
        call = live.activate_stream(authenticated_stream(configured), cfg)
        model = FakeModel()
        sent = []
        class Socket:
            async def send_json(self, event): sent.append(event)
        voice = live.LiveCall(Socket(), model, cfg, call, STREAM)
        voice.unaccepted.add('saving-another-task')
        audio = base64.b64encode(b'\x10' * 1600).decode()
        await model.queue.put({'type': 'session.output_audio.delta', 'delta': audio})
        await model.queue.put({'type': 'session.closed'})
        await voice.receive_model()
        assert [e['media']['payload'] for e in sent if e['event'] == 'media'] == [audio]
    asyncio.run(run())


def test_volume_spike_does_not_clear_speech_or_prompt_an_apology(configured):
    async def run():
        cfg, _ = configured
        call = live.activate_stream(authenticated_stream(configured), cfg)
        model = FakeModel()
        sent = []
        events = iter([
            {'event': 'media', 'streamSid': STREAM, 'sequenceNumber': '1', 'media': {
                'track': 'inbound', 'payload': base64.b64encode(b'\x10' * 160).decode()}},
            {'event': 'stop', 'streamSid': STREAM},
        ])
        class Socket:
            async def send_json(self, event): sent.append(event)
            async def receive_json(self): return next(events)
        voice = live.LiveCall(Socket(), model, cfg, call, STREAM)
        voice.last_output = time.monotonic()
        await voice.receive_phone()
        assert not any(e['event'] == 'clear' for e in sent)
        assert [e['type'] for e in model.sent] == ['session.input_audio.append']
    asyncio.run(run())


def test_runtime_metadata_does_not_enter_live_thought_stream(configured):
    cfg, _ = configured
    call = live.activate_stream(authenticated_stream(configured), cfg)
    model = FakeModel()
    voice = live.LiveCall(None, model, cfg, call, STREAM)
    voice.runtime.user_turn('turn-1', 'Hello')
    asyncio.run(voice.deliver_ready_notice())
    assert not model.sent


def test_unheard_previous_answers_are_not_reinjected_into_new_calls(configured):
    cfg, _ = configured
    call = live.activate_stream(authenticated_stream(configured), cfg)
    presence.archive(call, [{'id': 'u', 'role': 'user', 'text': 'Hello'},
        {'id': 'a', 'role': 'assistant', 'text': 'Old answer about a different topic.',
         'playback': 'unconfirmed'}], cfg.phone_live_model)
    assert 'Old answer' not in json.dumps(presence.context_for(call, cfg))


def test_diagnostic_timeline_preserves_fragments_without_claiming_playback(configured):
    cfg, _ = configured
    call = live.activate_stream(authenticated_stream(configured), cfg)
    fragments=[{'role':'user','text':'What is your name?','start_ms':1200,'end_ms':1800},
               {'role':'assistant','text':'Eli.','start_ms':2200,'end_ms':2600,'playback':'unconfirmed'},
               {'role':'user','text':'Thank you.','start_ms':3200,'end_ms':3600}]
    presence.archive(call,fragments,cfg.phone_live_model)
    with phone.store().db() as db:
        record=json.loads(db.execute('SELECT payload FROM phone_conversations').fetchone()[0])
    assert record['transcript_timeline']==fragments
    assert all(t['role']=='user' for t in record['turns'])
    assert record['generated_unconfirmed'][0]['playback']=='unverified'
