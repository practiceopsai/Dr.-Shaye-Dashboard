"""Conversation ownership and metadata traces for continuous GPT-Live audio.

Live has timeline fragments, not Realtime response.done events. Application turn
IDs describe ownership, not invented provider events. Twilio marks prove buffer
playout, never that a person understood the audio.
"""
from collections import deque
import hashlib
import json
import re
import time


def classify_read(text):
    """Closed, read-only grammar. Anything ambiguous stays in the native agent.

    Never parse a prefix: trailing write instructions must not be discarded.
    The worker independently validates the same plan and the caller's identity.
    """
    t=re.sub(r'\s+',' ',text.casefold()).strip(' .?!')
    # Exact negative safety qualifiers do not change a read into an action.
    # Positive instructions or any other suffix still fail the full match.
    t=re.sub(r'[.!,;]? (?:do not|don.t) send anything$', '', t).strip(' .?!')
    t=re.sub(r'^(?:please |can you |could you )','',t)
    suffix=r'(?: and (?:tell me|read)(?: the)? (?:subject|sender|summary))?'
    if re.fullmatch(r'(?:check|read|show me|what is|what.s)(?: the)?(?: your| eli.s)? (?:latest|most recent|newest) (?:email|mail|message)'+suffix,t):
        return {'kind':'latest_email','mailbox':'eli'}
    if re.fullmatch(r'(?:check|read|show me|what is|what.s)(?: the)? my (?:latest|most recent|newest) (?:email|mail)'+suffix,t):
        return {'kind':'latest_email','mailbox':'personal'}
    m=re.fullmatch(r'(?:what(?: is|.s) on my calendar|check my calendar|what (?:do i have|meetings do i have))(?: (today|tomorrow|this afternoon))?',t)
    if m:return {'kind':'calendar','window':m.group(1) or 'today'}
    return None


def silent_completion(text):
    """Routine mutation completion stays in the ledger unless asked for."""
    t=re.sub(r'\b(?:do not|don.t|never)\s+[^.!?]+','',text,flags=re.I)
    return bool(re.search(r'(?:^|[.!?]\s*|\b(?:please|also|then|and|you)\s+)'
                          r'(?:send|email|text|schedule|book|reschedule|save|add|move|delete|update)\b',t,re.I))


class Runtime:
    def __init__(self,call_id,store):
        self.call_id,self.store=call_id,store
        self.began=time.monotonic();self.sequence=0
        self.events=[];self.turn_id='';self.topic_id='';self.topics=deque(maxlen=12)
        self.floor='none';self.connection='connected';self.response_id='';self.interrupted=set()
        self.pending={};self.last_user_end=0.;self.first_audio=False
        self.output_end=0.;self.played_end=0.;self.marks={};self.cancelled_spans=[]
        self.output_fence=False;self.output_silence_ms=0.;self.audio_spans=set()
        self.last_input_seq=0;self.last_generated='';self.last_played=''
        self.audio_events=set();self.output_fingerprints={};self.last_echo=0.
        self.transcript_clock_aligned=True

    def event(self,kind,*,turn_id=None,task_id='',duration_ms=0,status='',response_id=None):
        self.sequence+=1
        self.events.append((self.call_id,self.sequence,kind,turn_id or self.turn_id,self.topic_id,
                            self.response_id if response_id is None else response_id,task_id,
                            int((time.monotonic()-self.began)*1000),max(0,int(duration_ms)),status[:60],time.time()))
        if len(self.events)>2000:self.flush()

    def flush(self):
        if not self.events:return
        with self.store.db() as db:
            db.executemany('INSERT OR IGNORE INTO phone_trace VALUES (?,?,?,?,?,?,?,?,?,?,?)',self.events)
        self.events.clear()

    def user_turn(self,identifier,text):
        if identifier==self.turn_id:return
        if self.topic_id:self.topics.append({'id':self.topic_id,'turn_id':self.turn_id,'state':'suspended'})
        self.turn_id=identifier
        self.topic_id='topic-'+hashlib.sha256((self.call_id+identifier).encode()).hexdigest()[:16]
        self.first_audio=False
        self.event('turn.observed')

    def snapshot(self):
        return {'floor':self.floor,'active_turn_id':self.turn_id,'active_topic_id':self.topic_id,
                'recent_topics':list(self.topics),'pending_tasks':list(self.pending),
                'interrupted_responses':list(self.interrupted)[-5:],'connection':self.connection,
                'played_audio_ms':round(self.played_end),'generated_audio_ms':round(self.output_end),
                'clock_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

    def interrupt(self):
        self.cancelled_spans.append((self.played_end,self.output_end))
        if self.response_id:self.interrupted.add(self.response_id)
        self.marks.clear()  # Marks returned by Twilio clear are NOT played receipts.
        self.output_fence=True;self.output_silence_ms=0
        self.event('response.interrupted',status='caller_overlap')
        self.response_id=''

    def audio_allowed(self,event,voiced,duration_ms,user_speaking):
        identifier=event.get('event_id')
        if isinstance(identifier,str):
            if identifier in self.audio_events:
                self.event('audio.discarded',status='duplicate_event');return False
            self.audio_events.add(identifier)
            if len(self.audio_events)>65000:raise ValueError('audio_event_limit')
        start,end=event.get('start_ms'),event.get('end_ms')
        if isinstance(start,(int,float)) and isinstance(end,(int,float)):
            key=(start,end)
            if key in self.audio_spans:
                self.event('audio.discarded',status='duplicate_timeline');return False
            self.audio_spans.add(key)
            if len(self.audio_spans)>65000:raise ValueError('audio_timeline_limit')
            self.output_end=max(self.output_end,end)
        else:
            # Primary Live audio has no session timestamps. Its cumulative byte
            # duration is a playout counter, NOT the transcript's session clock.
            self.transcript_clock_aligned=False
            self.output_end+=duration_ms
        if self.output_fence:
            self.output_silence_ms=0 if voiced else self.output_silence_ms+duration_ms
            # Require the continuous provider to actually yield, not just the
            # local caller-energy timeout, before allowing subsequent speech.
            if self.output_silence_ms>=120:self.output_fence=False
            if voiced:return False
        return not user_speaking

    def observe_output(self,samples):
        # Short-lived nonreversible fingerprints diagnose exact media loopback.
        # They are not acoustic echo cancellation and never erase user speech.
        now=time.monotonic()
        self.output_fingerprints={k:v for k,v in self.output_fingerprints.items() if now-v<3}
        for start in range(0,len(samples)-159,160):
            frame=samples[start:start+160]
            if len(set(frame))>12:self.output_fingerprints[hashlib.sha256(frame).digest()]=now

    def observe_input(self,samples):
        now=time.monotonic()
        matched=any(now-self.output_fingerprints.get(hashlib.sha256(samples[i:i+160]).digest(),-100)<3
                    for i in range(0,len(samples)-159,160))
        if matched and now-self.last_echo>1:
            self.last_echo=now;self.event('audio.echo_suspected',status='exact_media_loopback')
        return matched

    def mark(self,name):
        self.marks[name]=self.output_end

    def played(self,name):
        end=self.marks.pop(name,None)
        if end is None:return False
        self.played_end=max(self.played_end,end)
        return True

    def heard_fragment(self,start,end):
        return (self.transcript_clock_aligned and end<=self.played_end
                and not any(start<b and end>a for a,b in self.cancelled_spans))
