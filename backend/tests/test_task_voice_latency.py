import asyncio
import base64
import time
from app import phone,phone_live as live,phone_dispatch as dispatch,task_intent
from test_phone import setup
from test_phone_live import configured,authenticated_stream,FakeModel,STREAM


def test_j_slow_planning_database_does_not_block_audio(configured,monkeypatch):
    async def run():
        cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
        model=FakeModel();sent=[]
        class Socket:
            async def send_json(self,event):sent.append((time.monotonic(),event))
        voice=live.LiveCall(Socket(),model,cfg,call,STREAM)
        monkeypatch.setattr(dispatch,'settle_dependencies',lambda:time.sleep(.6))
        monkeypatch.setattr(dispatch,'take_intake',lambda:None)
        first=asyncio.create_task(dispatch.dispatch_once());second=asyncio.create_task(dispatch.dispatch_once())
        await asyncio.sleep(.03)
        began=time.monotonic()
        await model.queue.put({'type':'session.output_audio.delta','delta':base64.b64encode(b'\x10'*1600).decode()})
        await model.queue.put({'type':'session.closed'})
        await voice.receive_model()
        assert next(t for t,e in sent if e['event']=='media')-began<.15
        assert not first.done() and not second.done()
        await asyncio.gather(first,second)
    asyncio.run(run())


def test_transcript_hint_is_bounded_and_never_authorizes_a_send():
    began=time.perf_counter()
    for _ in range(1000):
        assert task_intent.control_hint('Wait, do not send it')
        assert not task_intent.control_hint('What is the weather?')
    assert time.perf_counter()-began<.3


def test_trace_volume_never_performs_database_io_on_audio_path(configured,monkeypatch):
    from app.phone_runtime import Runtime
    rt=Runtime('test',phone.store())
    def blocked():raise AssertionError('Audio trace attempted synchronous I/O')
    monkeypatch.setattr(rt,'flush',blocked)
    for _ in range(21000):rt.event('audio.forwarded')
    assert len(rt.events)<=20000
