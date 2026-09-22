# Eli voice orchestration

## Phase 0 — discovery, 21 September 2026

Production baseline: dashboard/backend and native phone plugin revision
`7271798a072a690eb5875696e77dd63436154554`. No production behavior was changed for
discovery. Existing backend suite: **213 passed**. Last release also passed 46
frontend tests, 73 plugin tests and 8 installed gateway adapter tests.

### Actual execution path

Twilio Media Streams carries 8 kHz mono PCMU audio in 20 ms frames. The backend
`phone_live.LiveCall` forwards it to **GPT-Live-1**, voice **Marin**. This is one
continuous audio model, not separate STT, turn-classifier and TTS services.
GPT-Live owns listening, speech generation and conversational overlap. Transcript
deltas are observations, not final utterances or confidence scores. RMS thresholds
in the relay measure activity; they must not become a noise-triggered speech mute.

Audio forwarding runs in independent asynchronous tasks. A Live delegation contains
an ID and audio offset, not a complete tool payload. The relay collects caller
fragments, waits for a settled transcript in a separate coroutine, then durably
enqueues intake. `phone_dispatch` uses a structured small model to split requests;
`phone_intake` validates required fields and prepares supported operations. Neither
planner nor executor belongs on the audio forwarding path. SQLite/context work
currently performed synchronously by the relay is a remaining scheduling hazard.

`PhoneStore` in the existing dashboard SQLite database owns persistent requests,
claims, dependencies, notices, questions, call archives and action receipts.
`root_id` already gives clarification continuations a stable logical identity;
individual rows are execution/intake revisions. Native `integrations/hermes_phone`
polls this queue, records accepted work in `state/eli-phone.sqlite3`, then runs either
a bounded prepared operation or the full authorized Hermes agent. The local journal
is a transport/reconciliation record, not a second source of task intent.

Native Hermes retains sessions/messages and delivery obligations in `state.db`;
cron schedules and execution records live under `cron/`. SOUL, persona/rank,
memory/RAG and feedback hooks remain in that gateway. Voice receives a refreshed,
actor-scoped context packet and archived calls feed the existing memory pipeline.
Hermes `TodoStore` is an in-memory agent scratchpad. Its installed persistent Kanban
board is empty (zero tasks/events/comments); introducing its independent dispatcher
for existing phone work would create competing executors. Extend PhoneStore and
expose its logical tasks across authenticated channels instead. Preserve cron and
dashboard priorities; these are schedules and recommendations, not task leases.

### Tools and delivery

AgentMail provides Eli's email; verified message IDs/readback establish delivery.
Prepared calendar operations support Eli-hosted ICS invitations (principal and guest
recipients) and the authorized principal Google Calendar connection. WhatsApp and
email have provider receipts. iMessage is disconnected and explicitly deferred by
the operator; never substitute another channel. Article search currently selects a
bounded RSS result and retains the selected source as an artifact before delivery.
Hermes has research, file and terminal tools, but no general durable research →
document → verified attachment → delivery workflow yet. A presentation must produce
an actual PPTX. Existing effect receipts and conservative uncertain-write recovery
must remain in force.

Hermes offers `pre_gateway_dispatch`, but it runs **before authorization**. Any
cross-channel bridge using it must explicitly require gateway authorization, a
configured actor and a direct message, and bypass internal/system events. It must
consume routed task instructions so the ordinary agent cannot execute them again.

### Measured latency

Twenty spoken questions were streamed in real time through an isolated copy of the
exact deployed relay, production voice model and actor context, with a temporary
database and no real calls or effects. Measurement starts at known synthetic speech
end and ends at the first voiced audio frame forwarded by the relay. It excludes
handset/PSTN latency. All 20 were answered; no overlap flags, provider errors,
delegated jobs or relay clears occurred.

| Measure | Baseline |
| --- | ---: |
| Median | 1287.335 ms |
| Maximum | 1702.89 ms |
| Turns over 800 ms | 20 / 20 |
| Median regression limit (+10%) | 1416.069 ms |

Private evidence: `%LOCALAPPDATA%/PracticeOps/EliPhone/orchestration-20260921/`.
It includes transcripts, per-turn timings, source hashes and cached input audio;
private persona/context is not committed to the public repository. The hard 800 ms
requirement **already fails**. This is not handset acceptance and cannot be reported
as satisfying that requirement.

### Design and phase boundaries

1. **Ledger:** extend existing root/revision semantics, dependencies, claims and
   receipts. Public task IDs stay stable across modifications; execution revisions
   retain their own IDs for native journal recovery. Add versioned intent metadata,
   parent/subtask relationships, an append-only event log and explicit effect
   reservations/commit receipts. The ledger projects the current revision; there is
   one queue and one canonical intent. Modifications invalidate older worker versions.
2. **Interpretation:** classify complete captured instructions against actor-scoped
   current tasks, including completed records. New work, modifications, cancellations,
   priorities and answers are typed operations. Ambiguous targets or incomplete
   consequential instructions wait for input. A cheap local control hint can hold
   effects while a possible correction is being resolved; it never authorizes work.
3. **Engine:** expand high-level work into persistent dependency steps using the
   existing executor. Re-read intent at step and effect boundaries. Store generated
   artifacts and verify them before delivery. Retry bounded reads; reconcile uncertain
   writes instead of repeating them. Third-party delivery needs task-specific approval
   or recorded preauthorization in the same conversation.
4. **Communication:** use versioned state/events as model context, not forced speech.
   Keep audio tasks independent; cache/read state off the audio path. Preserve
   personality, RAG and per-call learning. Text ingress and voice share the ledger;
   persisted tasks and agreed delivery survive hangup, with no unsolicited callbacks.

Each phase gets focused tests before the next begins. Run the existing suites again,
then A–N acceptance with ledger/event/receipt evidence and the same 20 audio samples.
Use isolated providers for invented test contacts; real sends are only those actually
authorized by the user. Final deployment requires compatible backend/native releases,
verified source hashes and idle gateway maintenance.

### API and distributed-system limits

The requested “classifier returns before TTS” is incompatible with GPT-Live's
continuous speech and independent client delegation. Waiting for a remote classifier
would violate the prime responsiveness directive. Interpretation therefore gates
**effects**, asynchronously; voice reads authoritative state and cannot equate an
acknowledgment with completion. No fabricated confidence score or final-transcript
event will be used. Incomplete/ambiguous captures require clarification before effects.

GPT-Live interruption is not an application cancellation. The client can clear its
playout buffer when it has reliable interruption evidence, but instruction append
acknowledgments do not prove playback stopped. Noise-only RMS gating caused earlier
regressions and is excluded. Absolute handset “immediate” interruption requires a
handset/echo test; model or socket timestamps alone cannot prove it.

External commit is not atomic with our SQLite transaction. Reserve and fence the
effect before its request; record the provider receipt as soon as received. During an
unresolved request, report “in flight / outcome unconfirmed,” never claim cancellation
or replay. A committed effect cannot be undone by changing the ledger.

References: [Live delegation](https://developers.openai.com/api/docs/guides/live-delegation),
[Live server controls](https://developers.openai.com/api/docs/guides/voice-server-controls?api=live).

## Implementation evidence

### Phase 1: shared ledger

Implemented logical task metadata, versions, parent/subtask links, audit events,
priorities and external-effect reservations over the existing PhoneStore queue.
Corrections and clarification answers keep the public task ID and advance its
execution version. Older workers are fenced out. Completion requires the recorded
operation receipt; queued/approved/answered do not mean completed. Reservations
are not receipts. `last_spoken_status` remains empty when playback cannot be proven.

### Phase 2: interpretation

Structured intake reads the actor's current tasks and exact question IDs across
channels. Operations apply transactionally. An ambiguous correction persists as
an intake question and holds execution until its exact answer is interpreted;
unrelated conversation cannot release it. Raw transcript fragments cannot authorize
effects. Replanning uses the original words plus the accumulated answers.

Live planner trials found and fixed contradictory derived conversation flags,
corrections misrouted as answers, and invented dependencies defeating explicit
priority. Eight actual-model scenarios now pass (A/B/C/D/F/G/H/N); the evidence
includes each returned plan and ledger snapshot. These are isolated databases,
not real sends. Planner time is background work and is not voice response latency.

### Phase 3: engine and artifacts

Research/create workflows expand into seven persistent steps in the same queue:
understand, plan, research, create, verify, deliver and confirm. Native Hermes owns
research and synthesis; the deterministic writer creates Markdown or a real PPTX
with PptxGenJS 4.0.1. Verification checks the file digest and document structure.
Delivery reads the verified artifact and checks the actual recipient, content and
attachment after provider acceptance. A provider timeout stays uncertain and is
never automatically resent. Third-party delivery pauses for task-specific approval
unless explicitly preauthorized. Calendar account selection remains mandatory.

The adapter, native tool guard, effect fence and canonical queue were tested together
using fixture model content and an isolated provider: a PPTX to the caller and written
findings to a third party each delivered exactly once; the latter required approval.
Queue restart produced no second send. A real generated deck was rendered in
PowerPoint, visually inspected, adjusted and reinspected. This proves generation
and orchestration, not the quality of arbitrary future research or real mailbox delivery.

### Phase 4: voice and channels

Transcript capture, database maintenance and state reads run off the audio event
loop. Large audio traces are bounded in memory and flushed by maintenance. The voice
prompt retains personality, conversation, delegation and authoritative status rules.
Worker events append context without creating speech turns. GPT-Live continues to
own interruption behavior. No new noise-triggered mute or forced announcement was added.

Authenticated direct-message task requests enter a durable native ingress outbox,
then the same canonical ledger. Configured identity and gateway authorization are
checked before the pre-dispatch hook consumes a message. Transport IDs deduplicate
intake. Pending-question state routes free-form answers; task notices persist with
conservative uncertain-delivery handling. `/api/tasks` exposes stable task state to
an authenticated app client; no new task UI was added in this change. Existing cron,
email, calendar, briefings, records, persona/rank and RAG continue through their
existing owners. The installed context and archive probe verified principal/operator
scope and idempotent call evidence ingestion.

### Validation and release status

- Backend: **245 tests passed**, including two queue-to-artifact-to-provider fixtures.
- Native plugin: **88 tests passed**, locally and against the installed Hermes imports.
- Installed gateway adapter: **9 tests passed**; persona/RAG/archive probe passed.
- Existing frontend: **46 tests passed**; no frontend code changes.
- Actual structured planner: **8/8 scenarios passed**, with no executor or external sends.
- Actual GPT-Live audio: baseline 20/20 answered, median **1287.335 ms**;
  final candidate 20/20 answered, median **1180.47 ms**, maximum **1470.05 ms**,
  no provider errors or unwanted task creation. Median is 8.3% below baseline and
  below the **1416.069 ms** regression ceiling. All 20 remain above **800 ms**.
- Actual-model run with two simulated running jobs and slow background workers: **20/20** answers, median **1122.08 ms**, maximum **1308.71 ms**, no provider errors. No real tasks or external sends ran in that load fixture; all 20 turns still exceeded 800 ms.

| Acceptance | Evidence / remaining work |
| --- | --- |
| A correction | Actual planner and ledger: one logical task, changed destination, version advances. |
| B multiple tasks | Actual planner creates three independent logical entries; parallel native gateway keys tested. |
| C cancellation | Actual planner and effect-fence tests cover before boundary, in flight and committed outcomes. |
| D recipient change | Actual planner retains one task; old execution cannot reserve a send. |
| E no resend | Completed-reference and durable-receipt replay tests pass. |
| F research / PPTX / self email | Actual planner plus queue/native artifact/provider fixture passes; real external delivery not exercised. |
| G research / third-party findings | Actual planner plus approval and delivery fixture passes; real external delivery not exercised. |
| H priority | Actual planner assigns independent email priority 900; queue priority/dependencies tested. |
| I barge-in cancellation | Backend cancellation boundary tested; immediate handset playback stop remains unverified. |
| J conversation under load | Slow-worker/DB fixture leaves audio forwarding responsive; actual-model load benchmark answered 20/20 at 1122.08 ms median; absolute 800 ms fails. |
| K 20-turn regression | Passes the baseline +10% median limit. Absolute 800 ms ceiling fails. |
| L restart | Canonical queue and native journal survive; uncertain writes are not repeated. |
| M voice to text | Authorized text endpoint cancels the voice task; native ingress authorization/dedup tests pass. Handset/channel acceptance remains open. |
| N partial speech | Actual planner asks for the missing instruction without executing; API supplies no acoustic confidence score. |

**Not production-deployed.** The definition of done is not met: the absolute latency
ceiling and handset acceptance remain open. Production stays on `7271798` while the
candidate is staged. An explicit decision is required before relaxing the user's
800 ms gate. A source-level implementation or simulated receipt is not evidence of
real handset behavior or actual external delivery.

For rollout after the gate is resolved: take verified native/backend snapshots, run
vault maintenance evaluations, drain only while idle, install the compatible native
plugin and its locked Node dependencies, deploy the backend, verify source hashes
and bridge health, then perform a handset acceptance session. Additive ledger tables
can remain on rollback; stop new intake and reconcile in-flight effects before
restoring an older executor. Never replay historical jobs as a migration.

A late result from a superseded native execution is retired only after its action
receipts have been flushed; it cannot overwrite the current version or block other
results. An installed-adapter regression test covers that outbox ordering.
The final voice benchmark precedes only a status-question hold-release correction;
20 focused voice tests passed after that branch-only fix.
