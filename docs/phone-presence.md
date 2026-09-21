# Conversation, context and explicit callbacks

This release supersedes the automatic callback policy in phone-continuity.md.

Diagnosis: speech instructions delegated every substantive question. Native
personality/RAG ran only in the executor. Results were released after an acoustic
pause with no topic check. Actual call records showed a callback reaching
voicemail, the greeting becoming a new task, and that task causing another
callback. Completed work was not replayed; new jobs formed a call chain. Audio
clearing alone lacked conversational recovery.

## Current path

1. Registered incoming calls open GPT-Live/Marin audio without a code.
2. The native bridge publishes actor-scoped context every minute. Current character,
   stage and runtime facts reach the speaking model. Principal sessions also get
   the existing persona compiler's learned context and shared RAG retrieval.
   Operators retain their existing access boundary. Context expires after five
   minutes. Known facts need no external lookup or job.
3. The voice model handles ordinary questions, explanation and judgment directly.
   Real work and fresh lookups enter the existing durable native queue. A narrow
   fallback catches unnecessary identity/model/team delegations. Answered
   conversation does not become another task on hangup.
4. Work continues through existing permissions, receipts, clarification and
   performance feedback. One acknowledgment; no timer-driven narration. Hangup
   preserves a final explicit request.
5. A result needs a quiet break and a relevant originating topic, or an explicit
   request for updates. Unrelated older results are not injected into speech.
   Admitted results carry their original request for natural reintroduction.
   There is at most one spoken attempt per notice per call. Interrupted/unplayed
   results stay in the app. Playback acknowledgment is not proof of understanding.
6. Caller speech clears buffered output and suppresses overlap. A silent recovery
   cue tells the model to yield, hear the full thought, briefly acknowledge the
   overlap at the next appropriate turn and follow the latest direction.
7. Call transcripts are separate evidence, never executable jobs. The bridge
   imports them idempotently into native SessionDB. Principal speech enters the
   existing source-checked persona inbox and shared RAG projection. Operator
   speech is not principal evidence. Assistant text is not an action receipt and
   may include interrupted speech. Sensitive text is filtered before ingestion.
8. Web and iPhone call summaries group original requests, verified results,
   missing answers and pending work. Summaries update as jobs finish.

## One call attempt per explicit request

No job opts into automatic callbacks. eli_phone_request_callback requires a
current explicit request and exact caller quote. Keypad requests remain explicit.
One unique root request permits one attempt. Completed, failed, cancelled and
uncertain receipts stay closed. Voicemail ends the callback without creating work.
"Stop calling me" revokes callback eligibility and cancels undialed callbacks.
Calls to others retain the exact-message approval workflow.

## Deployment and evidence

Deploy all six native modules, including presence.py. Schema changes are additive.
Never delete action or call receipts. PHONE_FOLLOWUP_MODE is app; historical
automatic enrollment was revoked. Explicit request state is required even with
an older callback setting. iMessage reconnection remains deferred.

Regression coverage includes scoped/expired context, known answers without jobs,
topic changes and result labels, voicemail, callback revocation/closure and
non-executable conversation archives. An isolated GPT-Live audio check answered
model/team questions directly and created one task for a simulated email lookup.
It introduced that result by topic, yielded on overlap and acknowledged the
interruption. Real telephone feel and actual outbound delivery remain separate
acceptance checks; these tests send no external messages or telephone calls.
