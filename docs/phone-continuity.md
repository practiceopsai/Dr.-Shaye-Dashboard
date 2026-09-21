# Background phone tasks and conversation continuity

## Diagnosis before changes

The previous release deliberately spoke progress at six seconds and then every
12–30 seconds. It checked a short quiet period for those updates, but action
receipts and final responses bypassed that check. Audio was forwarded directly
to Twilio without clearing its playback buffer when the caller began speaking.
A backend result could therefore interrupt another request.

Clarification was prompt guidance, not a task state: a question was returned as
a completed native turn. Live calls did not arrange post-call callbacks. The
three-pending-request limit prevented longer task stacks. Accepted queue entries
survived hangup, but cancellation of the settling/delegation coroutine could
discard the final unconsumed transcript. Incoming calls and private callbacks
both prompted for an eight-digit PIN.

## Current flow

1. A signed Twilio webhook maps the registered calling number to its existing
   identity. With `PHONE_PIN_REQUIRED=false` (the default), it connects directly
   to GPT-Live. No spoken/keypad verification is requested. Unknown callers are
   refused. This identifies the caller by the registered phone number; it is not
   a claim that caller ID proves the human's identity.
2. Speech remains duplex. A complete request is persisted as its transcript settles.
   The voice model gives one short acknowledgment and listens; the backend never
   adds a second spoken acknowledgment. There are no timer-driven
   spoken progress updates. Up to 32 pending requests can be stacked.
3. The native gateway executes saved jobs in caller order, independently of audio.
   Waiting clarifications and uncertain past outcomes do not occupy the active
   execution slot. An uncertain action itself is never replayed automatically.
4. Missing required details call `eli_phone_clarify`. The question is durably
   saved before returning; further task tools are blocked for that turn. Its state
   becomes `waiting_for_input`, not completed. Other requests can proceed.
5. One call-wide delivery scheduler holds verified answers and questions until
   caller audio/transcript has been quiet for 1.4 seconds and assistant audio for
   0.8 seconds. Instructions also direct semantic turn-taking and one question at
   a time. When caller speech resumes, the server clears Twilio's playback buffer
   and suppresses overlapping output. Interrupted notices remain pending.
6. Playback marks acknowledge an update only after associated output text/audio.
   Marks returned after a clear do not acknowledge it. A playback acknowledgment
   is not proof that a human understood or acted on the update.
7. A caller answer is matched to an exact open question by the existing native
   agent using `eli_phone_answer_clarification`. Ambiguous matches require a
   question. The answer must appear in current caller speech. The authenticated
   app can also answer the exact task. One transaction consumes the question and
   queues one continuation; retries return that same continuation.
8. Continuations retain the root task ID and prior receipts. The same message
   payload cannot be sent again merely because a clarification created a new
   execution turn. Missing approval or changed details still require clarification.
9. At hangup, the final available caller transcript is persisted once, including
   late fragments received while the voice session closes. Incomplete requests
   must be clarified. The call ending never grants approval or cancels work.
10. Post-release tasks opt into follow-up. After hangup, unplayed results and
    unanswered questions are grouped into a callback to the registered caller
    when `PHONE_FOLLOWUP_MODE=callback` and outbound calls are enabled. The worker
    waits at least 30 seconds after hangup and 15 seconds after a result, avoids
    active conversations, and spaces callbacks by at least two minutes. There is
    one automatic attempt per notice; an uncertain call submission is not redialed.
    Missed calls, errors and unanswered questions stay visible in the app. Old
    historical jobs are not automatically enrolled in callbacks.

## Shared Eli identity, memory and learning

Requests still enter `PhoneAdapter.agent_turn` and the full native message
pipeline using the stable `phone:<user_id>` conversation. The phone voice model
handles speech; the existing native model handles substantive work. Native SOUL,
account routing, approval hooks, scoped RAG, persona/rank and session persistence
remain authoritative. Dr. Shaye's phone platform is already in the principal
persona allowlist. Operator tests do not become inferred principal preferences.

The existing native memory/persona observers receive delegated caller turns and
results, including final captured turns. Open questions and prior action receipts
are supplied to later phone work. Tool/model timings remain in the native durable
feedback journal. Deferred and interrupted voice-delivery observations are saved
and included in later requests. This is persistent operational feedback and
memory, not online retraining of model weights or permission changes.

Both the web Phone page and iPhone “Phone requests and answers” view show saved
questions, results and callback status, and allow an authenticated caller to
answer a pending task. The iPhone view is a compatible JavaScript update.

## Verification and limits

Regression coverage includes code-free registered access, unauthorized rejection,
silent long-running work, stacked requests, interruption/cleared playback,
unanswered questions, atomic answer resumption, cross-caller denial, root receipt
deduplication, final-turn capture, callback grouping, missed/uncertain calls and
stale-connection recovery. Provider calls are mocked in automated tests.

Keep subjective telephone turn-taking acceptance separate from isolated audio
testing. Voice recognition, a dropped audio connection before transcription, or a
provider outage can still prevent completion; these must remain visible rather
than produce fabricated confirmation. iMessage reconnection remains deferred.
Unqualified “text” means iMessage; WhatsApp requires explicit naming.

Protocol references:
- https://developers.openai.com/api/docs/guides/live-delegation
- https://www.twilio.com/docs/voice/media-streams/websocket-messages
