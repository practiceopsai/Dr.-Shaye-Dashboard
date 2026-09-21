"""Behavioral regressions identified in the deployed September 21 baseline."""
import asyncio
import json
import time
from app import phone, phone_live as live, phone_presence as presence
from test_phone_live import configured, authenticated_stream, fragment, STREAM, FakeModel
from test_phone import setup


def test_different_email_question_does_not_release_older_email_answer():
    notice={'source_call':'call','request':'Did Peter email me about the contract?'}
    assert not presence.relevant_notice(notice,'call','How should I write a good email introduction?')


def test_duplicate_transcript_with_new_event_id_same_audio_span_is_once():
    c=live.Conversation()
    c.append(fragment('one','Send the email.',1000))
    c.append(fragment('replay','Send the email.',1000))
    assert c.request(2000)[2]=='Send the email.'


def test_repeated_delegation_for_same_caller_turn_is_one_task(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    first=live.enqueue(call,'first','New caller speech: Send the email.','Send the email.',origin_turn_id='turn-1')
    again=live.enqueue(call,'duplicate','New caller speech: Send the email.','Send the email.',origin_turn_id='turn-1')
    assert again==first
    assert len(phone.store().jobs(call['actor']))==1
    other=live.enqueue(call,'next','New caller speech: Send the email.','Send the email.',origin_turn_id='turn-2')
    assert other!=first  # A new explicit instruction is not erased by content dedup.


def test_unheard_assistant_speech_is_not_archived_as_heard(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    presence.archive(call,[{'id':'u','role':'user','text':'Hello'},
                          {'id':'a','role':'assistant','text':'I sent it.','playback':'discarded'}],cfg.phone_live_model)
    with phone.store().db() as db:
        turns=json.loads(db.execute('SELECT payload FROM phone_conversations').fetchone()[0])['turns']
    assert all(t['text']!='I sent it.' for t in turns)


def test_cancellation_closes_queued_work_without_claim_or_replay(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    job=live.enqueue(call,'one','New caller speech: Draft an email.','Draft an email.')
    result=phone.store().cancel(call['actor'],job)
    assert result['state']=='cancelled'
    assert phone.store().claim() is None
    assert phone.store().cancel(call['actor'],job)['state']=='cancelled'


def test_running_action_cancellation_never_claims_effect_was_undone(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    job=live.enqueue(call,'one','Send email.','Send email.')
    phone.store().claim()
    with phone.store().db() as db: db.execute("UPDATE phone_jobs SET state='running' WHERE id=?",(job,))
    result=phone.store().cancel(call['actor'],job)
    assert result['state']=='cancel_requested'
    assert result['effect_cancelled'] is False


def test_read_lane_does_not_wait_behind_running_mutation(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    first=live.enqueue(call,'one','New caller speech: Research a proposal.','Research a proposal.')
    assert phone.store().claim()['id']==first
    second=live.enqueue(call,'two','New caller speech: Check your latest email.','Check your latest email.',read_plan={'kind':'latest_email','mailbox':'eli'})
    assert phone.store().claim(lane='read')['id']==second


def test_trace_metadata_does_not_store_transcripts(configured):
    from app.phone_runtime import Runtime
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    rt=Runtime(call['id'],phone.store())
    rt.event('speech.user.started',turn_id='u1')
    rt.flush()
    with phone.store().db() as db:
        row=dict(db.execute('SELECT * FROM phone_trace').fetchone())
    assert row['kind']=='speech.user.started' and row['turn_id']=='u1'
    assert 'transcript' not in row


def test_cleared_playback_marks_do_not_claim_audio_was_heard(configured):
    from app.phone_runtime import Runtime
    rt=Runtime('call',phone.store());rt.output_end=1000
    rt.mark('played');rt.played('played')
    rt.output_end=2000;rt.mark('cleared');rt.interrupt()
    assert not rt.played('cleared') and rt.played_end==1000
    assert not rt.heard_fragment(1000,1500)
    assert not rt.audio_allowed({'start_ms':2000,'end_ms':2200},True,200,False)
    assert rt.audio_allowed({'start_ms':2200,'end_ms':2400},False,200,False)
    assert rt.audio_allowed({'start_ms':2400,'end_ms':2600},True,200,False)
    assert not rt.audio_allowed({'start_ms':2400,'end_ms':2600},True,200,False)


def test_conversation_pause_and_actual_repeated_speech_not_deduplicated():
    c=live.Conversation();c.append(fragment('one','Can you check',1000))
    c.append(fragment('two',' my calendar?',1900))
    assert len({x['turn_id'] for x in c.fragments})==1
    c.append(fragment('three','Can you check',5000))
    assert c.request(6000)[2].count('Can you check')==2


def test_fast_read_grammar_never_discards_appended_write():
    from app.phone_runtime import classify_read
    assert classify_read('Check your latest email.')=={'kind':'latest_email','mailbox':'eli'}
    assert classify_read('Check my latest email.')['mailbox']=='personal'
    assert classify_read('What is on my calendar tomorrow?')['window']=='tomorrow'
    assert classify_read('Check your latest email and send it to Fabio.') is None
    assert classify_read('Delete the latest email.') is None
    assert classify_read('Please check your latest email and tell me the subject. Do not send anything.')['mailbox']=='eli'


def test_routine_success_stays_silent_even_before_topic_pivot():
    n={'source_call':'call','request':'Send Fabio the email.','notify_policy':'silent_success','state':'completed'}
    assert not presence.relevant_notice(n,'call','Send Fabio the email.')
    assert presence.relevant_notice(n,'call','Any updates?')
    n['state']='uncertain'
    assert presence.relevant_notice(n,'call','Send Fabio the email.')


def test_rapid_stacked_requests_get_distinct_durable_origins(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    c=live.Conversation();c.append(fragment('first','Send Fabio hello.',1000))
    text,ids,caller=c.request(2000)
    one=live.enqueue(call,'a',text,caller,origin_turn_id=c.turn_id)
    c.consume(ids)
    c.append(fragment('second','Also check my calendar.',2100))
    text,ids,caller=c.request(3000)
    two=live.enqueue(call,'b',text,caller,origin_turn_id=c.turn_id)
    assert one!=two and len(phone.store().jobs(call['actor']))==2
    assert phone.store().jobs(call['actor'])[0]['transcript']=='Also check my calendar.'


def test_exact_media_echo_is_diagnosed_without_dropping_legitimate_repeated_words(configured):
    from app.phone_runtime import Runtime
    rt=Runtime('echo-call',phone.store())
    audio=bytes(range(160));rt.observe_output(audio)
    assert rt.observe_input(audio)
    assert not rt.observe_input(bytes(reversed(range(160))))
    assert not rt.observe_input(b'\xff'*160)
    assert any(e[2]=='audio.echo_suspected' for e in rt.events)
    assert rt.audio_allowed({'event_id':'once'},True,20,False)
    assert not rt.audio_allowed({'event_id':'once'},True,20,False)


def test_primary_audio_byte_clock_never_proves_transcript_playback(configured):
    from app.phone_runtime import Runtime
    rt=Runtime('call',phone.store())
    assert rt.audio_allowed({},True,2000,False)
    rt.mark('played');rt.played('played')
    assert rt.played_end==2000
    assert not rt.heard_fragment(0,1000)


def test_unconfirmed_generated_words_preserved_separately_from_heard_history(configured):
    cfg,_=configured;call=live.activate_stream(authenticated_stream(configured),cfg)
    presence.archive(call,[{'id':'u','role':'user','text':'What do you think?'},
        {'id':'a','role':'assistant','text':'We could shorten the meetings.','playback':'unconfirmed'}],cfg.phone_live_model)
    with phone.store().db() as db:p=json.loads(db.execute('SELECT payload FROM phone_conversations').fetchone()[0])
    assert len(p['turns'])==1 and p['turns'][0]['role']=='user'
    assert p['generated_unconfirmed'][0]['playback']=='unverified'
    context=presence.context_for(call,cfg)
    assert 'shorten the meetings' in context['prior_generated_speech'][0]
