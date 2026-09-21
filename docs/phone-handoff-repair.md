# Phone handoff repair — 21 September 2026

The operator's 217-second acceptance call exposed failures between voice delegation,
task intake, and native execution. The deployed baseline was `1272611`. Private call
transcripts, job payloads, native tool traces, and audio transport events were inspected
before changes. Times below are seconds from the start of that call.

## Observed breakpoints

| Request | Trace | Failure |
| --- | --- | --- |
| First prior-call recall | Delegated at 54.8; intake at 55.8; classified as conversation at about 58.6 | Earlier current-call fragments remained unconsumed. Historical open questions influenced routing. No prior-call record was queried. |
| Repeated prior-call recall | Delegated 77.8; read job 81.1; completed 133.9; context submitted 134.0 | Native history discovery took 52.9 seconds, including denied context/history routes. The final result did identify the prior call, but the bridge recorded submission without a model acknowledgment. |
| Text and email with shared content | Intake 117.5; two jobs 120.0 | The email quote contained only “email him the same thing,” losing its antecedent. Both native jobs resumed unrelated historical clarification tasks instead of sending messages. |
| Message completion | New text/email marked completed at 140.2/150.0 | Acknowledgment strings were accepted as completion without send receipts. The resumed email task later asked for the missing wording. No send tool fired for either request. |
| Ambiguous meeting email | Spoken 137.2–141.0; delegated 198.8; waiting for input 211.8 | Voice confirmed without delegating promptly; required-content validation was deferred until native execution. |

There were 2,033 audio forwarding events, no application audio clears or discards,
and a largest forwarding gap of 739 ms. Audio packets continued during the roughly
28-second conversational silence following “checking now.” This does not establish
exact handset playout or rule out acoustic echo: raw handset audio was not retained.
There was no evidence that the delegation coroutine blocked the audio socket.

## Changed behavior

1. Session state contains an explicitly bounded previous completed call for the same
   caller. It excludes the current call, other callers, and calls ending after this
   call started. Simple recall reads that record locally. Native personality, rank,
   caller-scoped RAG, and call evidence ingestion remain connected.
2. Intake resolves shared recipients and message bodies before creating executable
   jobs. Each message stores its own complete source-backed payload and approval
   evidence. Missing details produce a durable `waiting_for_input` task immediately;
   no native execution claim is made. An isolated live-model replay also caught a
   planner labeling a new question as a clarification answer; new questions now
   persist safely without trying to resume any earlier task.
3. A new atomic job receives no unrelated open questions. An answer can resume only
   the explicitly selected question in the current call. Both backend and native
   tools enforce that boundary, including idempotent repeat delivery.
4. Fully specified sends go directly through existing native authorization, channel,
   cancellation, effect-ledger, and provider-receipt checks. This avoids an unnecessary
   reasoning/tool-discovery round. Each channel has an independent job and completion
   state. Acknowledgment prose cannot complete a message job. An uncertain accepted
   effect remains uncertain and is never automatically resent.
5. Intake is persisted independently of model delegation as a safety net for spoken
   actions that the model acknowledges without delegating. It waits for stable
   transcript fragments, without depending on input RMS silence. Background work
   survives hangup. There are no new passcodes, callbacks, or channel substitutions.
6. Result updates retain their original Live delegation correlation. Submission and
   OpenAI context acknowledgment are measured separately. Missing context delivery is
   retried once using the same event ID; action execution is not retried. Results stay
   in thinking context so the voice model controls conversational timing.
7. Planner validation reasons, execution/tool timings, receipt failures, and context
   acknowledgments are durable diagnostic observations. Existing bounded native
   feedback and source-checked call learning remain active. They do not modify
   authorization policy or learn successful execution from unverified speech.

The working continuous-audio transport, voice, and model-owned turn-taking were
preserved. No additional VAD threshold, local muting, forced progress speech, or
application barge-in rule was introduced.

## Validation and limits

Backend regression tests cover complete compound payloads, missing-content intake,
cross-call isolation, prior-call boundaries, capture without model delegation,
and acknowledged result correlation. Native tests cover source-backed prepared sends,
once-only receipt reuse, invented-content rejection, and refusal to complete a send
from acknowledgment text. Installed-adapter tests exercise email completion and the
iMessage blocker without invoking the reasoning agent.

The isolated GPT-Live audio replay uses the actual voice model and task planner with
simulated external delivery. It cannot prove a real email was sent or how a handset
sounds. Production provider receipts and the operator's handset test are separate
acceptance requirements. iMessage remains disconnected by the operator's choice;
it must report failure promptly and must not fall back to SMS or WhatsApp.
