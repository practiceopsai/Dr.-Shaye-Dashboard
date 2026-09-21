import asyncio
import json
import time
import pytest

from app import phone, phone_live as live, phone_presence as presence
from app.phone_followups import prepare_callback
from test_phone_live import configured, authenticated_stream, CALL, STREAM, FakeModel, fragment
from test_phone import setup
from test_phone_continuity import queued, finish, make_followup_ready


def test_native_context_is_scoped_fresh_and_actually_in_session(configured):
    cfg,client=configured
    call=live.activate_stream(authenticated_stream(configured),cfg)
    payload={'contexts':[{'actor':call['actor'],'user_id':call['phone'],'packet':{'native_model':'native-test','personality':'Be candid, warm and decisive.','known_team':['Alex']}}]}
    assert client.post('/internal/phone/presence',json=payload).status_code==403
    headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    assert client.post('/internal/phone/presence',headers=headers,json=payload).status_code==200
    prompt=live.session_config(cfg,call)['instructions']
    assert 'native-test' in prompt and 'Alex' in prompt and 'candid, warm' in prompt
    assert cfg.phone_live_model in prompt
    assert 'native-test' not in live.session_config(cfg,{**call,'actor':'operator@example.com'})['instructions']
    payload['contexts'][0]['user_id']='someone-else'
    assert client.post('/internal/phone/presence',headers=headers,json=payload).status_code==403
    with phone.store().db() as db: db.execute('UPDATE phone_voice_context SET updated=?',(time.time()-301,))
    assert 'native-test' not in live.session_config(cfg,call)['instructions']


@pytest.mark.parametrize('text',['What model are you using?','Who is their team?','Who are you?'])
def test_known_questions_do_not_create_work_even_if_voice_delegates(configured,text):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    voice=live.LiveCall(None,FakeModel(),cfg,call,STREAM)
    voice.conversation.append(fragment('u',text));voice.conversation.last_input=0
    asyncio.run(voice.delegate('unexpected',1000))
    voice.save_final_request()
    assert phone.store().jobs(call['actor'])==[]


def test_directly_answered_conversation_is_not_added_to_later_work(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    v=live.LiveCall(None,FakeModel(),cfg,call,STREAM)
    v.conversation.append(fragment('u','What model are you using?'))
    v.conversation.append(fragment('a','GPT-Live.',2000,'assistant'))
    v.settle_conversation()
    v.conversation.append(fragment('task','Email Fabio.',3000))
    assert v.conversation.request(4000)[2]=='Email Fabio.'


def test_old_topic_result_is_silent_then_reintroduced_with_origin(configured):
    call,job=queued(configured);finish(configured,job)
    v=live.LiveCall(None,FakeModel(),configured[0],call,STREAM)
    v.conversation.append(fragment('u','What do you think about a vacation in Japan?'));v.conversation.last_input=0
    asyncio.run(v.deliver_ready_notice())
    assert not any(e['type']=='session.commentary.append' for e in v.upstream.sent)
    assert phone.store().notices(call['actor'])[0]['heard_at'] is None
    v.conversation.append(fragment('a','Let us discuss the trip.',2000,'assistant'))
    v.conversation.append(fragment('u2','Any updates on the email to Fabio?',3000));v.conversation.last_input=0
    asyncio.run(v.deliver_ready_notice())
    assert any(e['type']=='session.commentary.append' for e in v.upstream.sent)
    assert any('original request: Email Fabio.' in e['content'] for e in v.upstream.sent)


def test_old_call_notice_is_not_blurted_at_next_greeting(configured):
    call,job=queued(configured);finish(configured,job)
    v=live.LiveCall(None,FakeModel(),configured[0],{**call,'id':'next-call'},STREAM)
    v.conversation.append(fragment('u','Hello Eli'));v.conversation.last_input=0
    asyncio.run(v.deliver_ready_notice())
    assert not any(e['type']=='session.commentary.append' for e in v.upstream.sent)


def test_no_automatic_callback_even_with_old_opt_in_or_callback_config(configured):
    call,job=make_followup_ready(configured)
    configured[0].phone_followup_mode='callback'
    with phone.store().db() as db: db.execute('UPDATE phone_jobs SET callback_requested=0,followup_allowed=1')
    prepare_callback();prepare_callback()
    assert phone.store().outbound(call['actor'])==[]


def test_voicemail_never_creates_work_at_hangup(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    v=live.LiveCall(None,FakeModel(),cfg,{**call,'outbound_id':'approved-callback'},STREAM)
    v.conversation.append(fragment('u',"Your call has been forwarded to voicemail. At the tone, please record your message."))
    v.save_final_request()
    assert phone.store().jobs(call['actor'])==[]


def test_callback_request_needs_current_exact_quote_and_closes_once(configured):
    call,job=queued(configured);cfg,client=configured;cfg.phone_outbound_enabled=True
    headers={'Authorization':'Bearer '+cfg.phone_bridge_token}
    claimed=client.post('/internal/phone/claim',headers=headers).json()['job']
    client.post('/internal/phone/jobs/'+job,headers=headers,json={'claim':claimed['claim'],'state':'running'})
    path='/internal/phone/jobs/'+job+'/callback';data={'claim':claimed['claim'],'quote':'Please call me back.'}
    assert client.post(path,headers=headers,json=data).status_code==400
    with phone.store().db() as db: db.execute('UPDATE phone_jobs SET transcript=? WHERE id=?',('New caller speech: Please call me back.',job))
    assert client.post(path,headers=headers,json=data).status_code==200
    client.post('/internal/phone/jobs/'+job,headers=headers,json={'claim':claimed['claim'],'state':'completed','result':'Done.'})
    with phone.store().db() as db:
        db.execute('UPDATE phone_calls SET ended=?',(time.time()-40,));db.execute("UPDATE phone_live_streams SET state='closed'")
        db.execute('UPDATE phone_jobs SET updated=?',(time.time()-40,))
    prepare_callback()
    with phone.store().db() as db: db.execute("UPDATE phone_outbound SET state='completed'")
    prepare_callback();prepare_callback()
    assert len(phone.store().outbound(call['actor']))==1
    assert client.post('/internal/phone/jobs/'+job,headers=headers,json={'claim':claimed['claim'],'state':'running'}).status_code==409


def test_stop_calling_revokes_undialed_callback_without_erasing_receipt(configured):
    call,job=make_followup_ready(configured);prepare_callback()
    presence.revoke_callbacks(call['actor']);prepare_callback()
    outgoing=phone.store().outbound(call['actor'])
    assert len(outgoing)==1 and outgoing[0]['state']=='cancelled'
    with phone.store().db() as db: assert db.execute('SELECT callback_job FROM phone_outbound').fetchone()[0]==job


def test_archive_and_summary_are_evidence_not_executable_requests(configured):
    call,job=queued(configured);finish(configured,job)
    fragments=[{'role':'user','text':'What is your name?'},{'role':'assistant','text':'Eli.'}]
    presence.archive(call,fragments,'gpt-live-1');presence.archive(call,fragments,'gpt-live-1')
    with phone.store().db() as db:
        assert db.execute('SELECT count(*) FROM phone_conversations').fetchone()[0]==1
        db.execute('UPDATE phone_calls SET ended=?',(time.time(),))
    cfg,client=configured
    assert len(phone.store().jobs(call['actor']))==1
    summary=client.get('/api/phone/access').json()['summaries'][0]
    assert summary['items'][0]['request']=='Email Fabio.' and summary['items'][0]['result']
    assert presence.summaries('operator@example.com')==[]


def test_explicit_callback_survives_clarification_before_first_attempt(configured):
    call,root=make_followup_ready(configured,question=True)
    child=phone.store().resume(call['actor'],root,'Say hello.',CALL)
    finish(configured,child)
    with phone.store().db() as db: db.execute('UPDATE phone_jobs SET updated=?',(time.time()-40,))
    prepare_callback();prepare_callback()
    outgoing=phone.store().outbound(call['actor'])
    assert len(outgoing)==1 and outgoing[0]['state']=='approved'
    with phone.store().db() as db: assert db.execute('SELECT callback_job FROM phone_outbound').fetchone()[0]==root


def test_archive_marks_existing_native_evidence_without_creating_another_task(configured):
    call,job=queued(configured)
    presence.archive(call,[{'id':'u1','role':'user','text':'Email Fabio.'}], 'gpt-live-1',{'u1'})
    with phone.store().db() as db:
        payload=json.loads(db.execute('SELECT payload FROM phone_conversations').fetchone()[0])
        assert payload['turns'][0]['delegated'] is True
        assert db.execute('SELECT count(*) FROM phone_jobs').fetchone()[0]==1
