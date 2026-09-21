# Phone execution, latency and recovery

The voice connection and the native Eli agent run independently. The voice model
transcribes speech and requests client delegation. It does not send messages itself.

1. Twilio forwards 8 kHz audio to the backend, which forwards chunks to GPT-Live.
2. `Conversation` collects role-separated transcript fragments. `delegate` waits
   at least one second, including 700 ms of settled speech/transcripts, so late
   qualifications are part of the request. It then atomically queues a phone job.
3. The native phone adapter claims work every second when idle and every half
   second while busy. Work is serialized per caller to preserve ordering and avoid
   racing changes/approvals. Other callers may run independently.
4. The authenticated event enters the existing native gateway: model, memory,
   persona, rank, routing and policy remain in that pipeline. A phone-only context
   hook supplies operation schemas and measured operational feedback before the
   first model call. The model can invoke `tool_call` directly without discovery.
5. Native tools perform the actual API calls. The prepared latest-email tool does
   one received-message lookup and one fetch, with no attachment downloads. It
   reads **Eli's AgentMail only**; personal/practice Gmail retains its own routing.
   A one-time email tool combines approval checks, a durable send receipt, provider
   verification and closing follow-up tracking. Existing broader tools remain.
6. Native observer hooks persist safe progress, tool/model durations and receipt
   notices to an outbox. Delivery retries only replay these records. The backend
   accepts each event once, authenticated by the exact job's claim token.
7. The live connection acknowledges acceptance, checks results every 300 ms, and
   supplies brief spoken progress after six seconds if needed, then backs off.
   Real send receipts can be announced before the native final answer. Result
   monitoring continues throughout the call; the former 90-second cutoff is gone.
   Hangup stops monitoring/audio, never the accepted task.

## Diagnosed baseline

In the initial real-call trace, a latest-email request spent about 38 seconds in
the native pipeline and seven model rounds. Its two email calls together took
about half a second. Repeated skill/catalog/schema discovery dominated the delay.
A missing WhatsApp action led to about 224 seconds of transport discovery, including
about 127 seconds of file searches; the next request waited behind it. The later
answer mistook an old email for fulfillment of a new request. The first receipt
repair added WhatsApp but did not address voice progress or schema discovery.
These measurements describe that trace, not a general latency guarantee.

## Delivery and channel rules

Unqualified **text means iMessage**. WhatsApp requires an explicit WhatsApp request.
The iMessage tool checks the existing BlueBubbles connection and reports a pending
blocker promptly if unavailable. It cannot substitute WhatsApp or SMS. Reconnection
is separate from this release. A caller must supply the message and recipient;
missing or unclear details require clarification, not invented content.

Each new message request has its own durable receipt. Duplicate invocation of
the same exact request returns that receipt. An uncertain attempt is never retried
automatically. A send receipt means the provider accepted/sent the message; it does
not prove the recipient read it. The Phone page labels a completed native turn
"Response ready" and shows action outcomes separately.

## Operational feedback

`execution_events` persists model/tool durations and outcomes without arguments,
message bodies or provider error text. Future authenticated phone turns receive
a bounded summary of recent failed/slow tools. The same failed attempt is blocked
within a request; simple messaging/lookups cannot wander into desktop/file searches.
This feedback changes route selection, not security, approvals, memory facts or
the model's weights. New policy changes require normal review and regression checks.

The native tool history and request receipts remain authoritative. Progress is
not success. Slow operations still need real-call measurements: unit tests establish
ordering, durability and permissions, not subjective rhythm or telephone quality.

Protocol reference: [GPT-Live client delegation](https://developers.openai.com/api/docs/guides/live-delegation?delegation-mode=client).
