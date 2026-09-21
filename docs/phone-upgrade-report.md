# Eli production voice upgrade — living implementation report

Audit baseline: public commit f9d331d; production hashes verified 2026-09-21 UTC.
Native gateway running, phone connected, bridge heartbeat <1 second. No active work
at inspection. Current request authorizes phased implementation/deployment, not
unsolicited test messages or calls. iMessage reconnection remains deferred.

## Discovered production architecture

Registered Twilio caller -> signed Media Stream (PCMU 8 kHz) -> Railway FastAPI
WebSocket -> OpenAI GPT-Live-1/Marin. The live model owns listening/speech and
delegates via metadata; it does not emit legacy Realtime response IDs/final turns.
PhoneStore persists jobs on the Railway volume. Native Hermes on the Orgo Windows
host polls, journals accepted work, runs its existing identity/policy/persona/RAG
pipeline, and transports saved results back. Voice notices use a separate quiet
gate. Web/iPhone show durable tasks and summaries. The iPhone app currently opens
telephone calls; it does not implement an in-app microphone/WebRTC voice session.

Native personality compiler, familiarity/rank state, hybrid vault retrieval,
SessionDB episodes and evidence learning already exist. Principal private-memory
access remains scoped to Dr. Shaye. Operator access is not silently broadened.
Gmail/Calendar connections are active according to current connection metadata.
Practice records are not downloaded to test access. AgentMail is Eli's own inbox,
not either caller's personal mailbox. The BlueBubbles endpoint is still deferred.

## Verified diagnosis before implementation

* Fast AgentMail tool calls: successful recorded durations 186 and 405 ms. General
  model rounds: median 6432 ms (72 rounds, includes a failed round). Queue claim:
  median 652 ms, maximum 115442 ms (25 jobs). Native turns: median 15217 ms,
  maximum 253750 ms (25 turns, includes failures and earlier releases). These are
  mixed-release historical samples, not current production latency guarantees.
* Every delegated read goes through the same actor-serialized agent queue; the
  prepared provider read itself is much faster than the surrounding reasoning.
* Reproduced: a result about Peter's contract email is admitted during an unrelated
  question about writing an email because one channel word matches.
* Reproduced: identical transcript/audio span with a new event ID is appended twice.
* General assistant transcripts are archived even if local output suppression cut
  off the audio. Playback marks currently cover notices, not all speech.
* The prompt permits an acknowledgment before persistence; a later silent accepted
  update cannot retroactively guarantee its ordering.
* Ordinary tasks have no explicit cancellation route, priority class or original
  turn/topic/authorization snapshot. Provider receipts cover prepared sends, not
  every general native mutation.
* No evidence yet establishes echo, two audio consumers, or duplicate primary
  response generation as the cause of a particular real call. These are hypotheses
  to instrument, not confirmed production diagnoses. Baseline has one audio sender
  and one GPT-Live speaking authority. No model temperature change is warranted.

## Requirement matrix — baseline

Statuses apply to the audited baseline. Each numbered section/heading is mapped;
code examples and subrequirements are interpreted within their parent row. A
vendor example is not treated as a mandate to replace functioning infrastructure.
Phase results below record changes without rewriting the historical diagnosis.

| ID / source requirement | Status | Verified implementation, gap or applicability |
|---|---|---|
| D.1 Objective | Implemented but needs improvement | Independent live audio and native task workers exist; fast reads share the slow agent path. |
| D.2 Two Independent Execution Planes | Already implemented and working | phone_live.LiveCall and PhoneAdapter/Journal are separate; accepted tasks survive disconnect. |
| D.3 Classify Every Tool Before Execution | Missing | No explicit execution_class; all delegated work uses one queue. |
| D.4 Task Queue Manager | Implemented but needs improvement | PhoneStore is the durable manager; lacks priority, cancellation and structured per-effect reconciliation. |
| D.5 Canonical Task Object | Implemented but needs improvement | Actor/call/job/root/claim/times exist; turn/topic/logical IDs and an authorization snapshot are absent. |
| D.6 Task State Machine | Implemented but needs improvement | queued/claimed/running/waiting/resumed/completed/failed/uncertain exist; completed means agent response, not verified side effect. |
| D.7 Durable Enqueue Before Conversational Acknowledgement | Implemented but needs improvement | Enqueue is durable; speaking-model instructions permit acknowledgment before the enqueue completes. |
| D.8 Recommended Queue Infrastructure | Conflicting / obsolete | SQLite on persistent Railway/native volumes already supplies the current single-instance ledger. A Postgres/Redis migration is not needed to repair these bugs; horizontal workers would require reconsideration. |
| D.9 Worker Concurrency | Implemented but needs improvement | Two native worker slots; all work per actor serialized, including independent reads. |
| D.10 Sequential vs Parallel Tasks | Implemented but needs improvement | Native agent can execute multiple tools; no explicit task dependency graph or independent read lane. |
| D.11 Smart Conversational Queue Behavior | Implemented but needs improvement | Conversation remains live, but the result relevance gate is keyword-based. |
| D.12 Completion Notification Policy | Implemented but needs improvement | Quiet-time/topic gate and app summaries exist; per-job notification policy absent. Routine progress must remain silent. |
| D.13 Conversational Relevance Gate | Implemented but needs improvement | Reproduced false positive: contract email answer passes gate during email-writing discussion. |
| D.14 Execution Receipts | Implemented but needs improvement | Root-scoped email/messaging receipts exist; generic native mutations lack a unified immutable effect ledger. |
| D.15 Idempotency and Duplicate Prevention | Implemented but needs improvement | Same delegation and tool receipt dedup work. New delegation IDs for the same logical turn are not durably joined. |
| D.16 Context Binding | Implemented but needs improvement | Actor/call/root binding exists; explicit original turn/topic metadata absent. |
| D.17 Task Memory Integration | Already implemented and working | PhoneStore and native Journal store execution state separately from RAG; recent task facts feed live context. |
| D.18 Task Queue Priority | Missing | No priority lane; recorded claim latency reached 115442 ms. |
| D.19 Resource Serialization | Implemented but needs improvement | Per-actor serialization is safe but overbroad; generic resource-level locking is absent. |
| D.20 Writes and Interruption Semantics | Already implemented and working | Speech interruption/voice-task cancellation never deletes durable accepted native work. |
| D.21 Explicit Cancellation | Missing | Only outbound-call cancellation exists. Ordinary queued/running tasks lack an explicit cancellation protocol. |
| D.22 Background Task and Handoff Survival | Implemented but needs improvement | Journal recovers accepted work; started work becomes uncertain. Automatic provider reconciliation is incomplete. |
| D.23 Example End-to-End Interaction | Implemented but needs improvement | Parts exist, but direct calendar read and generic calendar read-back are not prepared paths. |
| D.24 Multiple Simultaneous Requests | Implemented but needs improvement | Compound utterances reach one native request; results/receipts can represent partial sends. No independently scheduled child jobs. |
| D.25 Partial Failure Handling | Implemented but needs improvement | Receipt-aware send reporting prevents some false all-done claims; generic mutations need equivalent coverage. |
| D.26 Retry Strategy | Implemented but needs improvement | Receipt transport retries safely; uncertain writes are not replayed. Read retry/deadline policy needs a separate lane. |
| D.27 Pre-Execution and Post-Execution Verification | Implemented but needs improvement | Email read-back exists but send acceptance is counted as confirmed even when source_verified is false. |
| D.28 Interaction With Fillers | Conflicting / obsolete | Use one acknowledgment after persistence. Repeated fillers/progress conflict with the current user instruction. |
| D.29 Never Fake Completion | Implemented but needs improvement | Messaging receipt guards exist; generic task completion and provider verification still need separation. |
| D.30 Observability | Implemented but needs improvement | Native model/tool/queue timings exist; end-to-end voice/turn/playback traces absent. |
| D.31 Recovery After Restart | Implemented but needs improvement | Uncertain effects are held rather than blindly replayed; reconciliation does not cover every provider. |
| D.32 Conversation Reconnect | Already implemented and working | Durable work and actor-scoped recent receipts remain after calls end; old sessions cannot authorize callbacks. |
| D.33 Smart Queue Pseudocode | Implemented but needs improvement | Existing implementation has persistence/worker separation; explicit classes, origins, cancel and receipt state need upgrades. |
| D.34 Builder-Agent Invariants | Implemented but needs improvement | Durability and interruption invariants partly enforced. New tests target identified gaps; no global exactly-once claim. |
| D.35 Required Regression Tests | Implemented but needs improvement | Existing regression suite covers hangup/clarification/callbacks; gap tests added before changes. |
| D.36 Performance Targets | Unable to verify | Targets are acceptance criteria, not measured results. Baseline lacks speech-end/playout p95. |
| D.37 Recommended Technology Mapping | Conflicting / obsolete | GPT-Live already owns full-duplex conversation. LiveKit/Temporal/pgvector are proposed choices, not requirements to replace working services. |
| D.38 Final Architecture After Adding the Task Engine | Implemented but needs improvement | Two planes already deployed. Missing direct reads, stronger state ownership and verified generic effects are the relevant upgrades. |
| R.1 Executive diagnosis and target architecture | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.2 Architectural conclusion | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.3 The four bugs and their most probable architectural causes | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.4 Recommended runtime strategy | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.5 Conversational state and situational awareness | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.6 Make the application state authoritative, not the model context | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.7 Use a deterministic state machine | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.8 Separate “generated,” “sent,” and “heard” | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.9 Build a fresh context snapshot before every response | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.10 Use a topic stack, not one global “current topic” string | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.11 Define the stale-result invariant | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.12 Real-time tools, retrieval and perceived latency | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.13 Replace request-time retrieval with synchronized read models where possible | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.14 Keep a freshness contract | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.15 Normalize tools behind one low-latency contract | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.16 Put hard latency budgets around tools | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.17 Never serialize independent lookups | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.18 Use narrow API requests | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.19 Make filler audio concurrent, cancellable and non-semantic | Conflicting / obsolete | Periodic narration conflicts with one acknowledgment then silence; use no routine progress timers. |
| R.20 A practical tool execution pattern | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.21 Do not use “I’ll get back to you” as a normal tool strategy | Implemented but needs improvement | Prepared AgentMail reads take 186-405 ms, but are wrapped in general model rounds and actor queue. No synchronized Gmail/Calendar read model; account/PHI boundaries apply. |
| R.22 Transport, turn-taking and barge-in | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.23 WebRTC should carry the interactive voice path | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.24 Phone calls need a telephony-specific path | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.25 Choose exactly one turn authority | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.26 Recommended LiveKit turn profile | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.27 Backchannels are not interruptions | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.28 Barge-in must stop local playback before doing anything else | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.29 Bound the downstream audio queue | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.30 Preempt intelligently | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.31 Native Realtime configuration | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.32 Cascaded versus native realtime | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.33 Repetition, audio cutoffs and output integrity | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.34 Diagnose repetition in the correct order | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.35 Add sequence numbers everywhere audio can be duplicated | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.36 Treat response text as segmented speech | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.37 Do not “fix” exact duplication using temperature | Already implemented and working | No temperature change proposed. Model repetition cannot be inferred from aggregate task logs. |
| R.38 Prevent response cutoffs caused by competing lifecycle events | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.39 Long-term memory, personality and user evolution | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.40 Do not build memory as “one vector database” | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.41 Storage recommendation | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.42 Core memory schema | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.43 Make raw episodes immutable | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.44 Memory write pipeline | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.45 Memory admission policy | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.46 Never overwrite evolving facts | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.47 Retrieval should be hybrid and time-aware | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.48 Memory cards should carry provenance | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.49 Personality and authority are not ordinary memories | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.50 Implementation blueprint, observability and acceptance gates | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.51 Recommended service decomposition | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.52 Canonical event envelope | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.53 Persist a turn timing record | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.54 Production SLOs | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |
| R.55 Add transport metrics | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |
| R.56 Critical regression scenarios | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.57 Audio-specific chaos testing | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |
| R.58 Use the cascaded engine as a debugging oracle | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.59 Recommended rollout sequence | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.60 Builder-agent implementation contract | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.61 Definition of “Eli vNext is ready” | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |

## Phased implementation and rollback

1. Strengthen existing conversation/task ownership, trace metadata, duplicate and
   cancellation handling. Additive schemas; preserve existing work/receipts.
2. Add bounded authorized immediate reads with independent worker capacity and
   truthful freshness. Preserve the full native agent for unsupported/complex work.
3. Strengthen side-effect receipts/reconciliation and execution authorization.
4. Verify local/native/staging, deploy with no active call, check production hashes,
   logs and timing, retain previous source backups for rollback.

No deployment yet for this audit. A phase is complete only when verification is
recorded below. Report source: actual code, private production metadata snapshot
upgrade-baseline.json, regression tests, and current vendor contracts. The source
documents' opaque citation placeholders are not independent verification.

## API contracts verified

* [OpenAI Live delegation](https://developers.openai.com/api/docs/guides/live-delegation):
  silent thinking versus spoken commentary; app owns tasks/permissions.
* [OpenAI Live event reference](https://developers.openai.com/api/reference/python/resources/live):
  continuous audio/timeline fragments, no invented Realtime cancellation events.

## Tests, changed files, deployment and before/after measurements

In progress. Existing baseline regression suite and new failing cases run before
implementation. No acoustic p95 or effectively-once guarantee is asserted without
the corresponding test evidence. Human handset/carrier quality remains distinct
from deterministic software and synthetic audio tests.

## Implemented phase: conversation ownership and prepared reads

Local and staged implementation, awaiting deployment verification:

- `backend/app/phone_runtime.py`: call/turn/topic/response metadata traces, caller
  floor, pending tasks, interrupted output, playback marks and replay rejection.
- `phone_live.py`: durable acceptance context once, no duplicate spoken acceptance
  append; one coherent result update; meaningful state changes only. Output yields
  on caller energy, clears buffered audio and fences old voiced output until the
  provider yields. Timeline/text replay is deduplicated independently of event IDs.
- `phone_presence.py`: no channel-word-only result relevance; successful routine
  mutations stay silent unless asked about. Unplayed assistant words are excluded
  from shared conversation evidence.
- `phone_store.py` and `phone.py`: turn/topic/logical request IDs, capture-authorization
  snapshot, execution class/priority, one task per originating turn, explicit task
  cancellation, independent read claims. Continuations retain original bindings.
- Native `reads.py`: no model round for exact latest-inbox and day-calendar queries;
  separate worker, 12-second deadline, explicit account/identity checks, bounded
  metadata, source/time/coverage contract and 15-second per-actor cache. Unsupported
  questions retain the full native agent. This is not a full synchronized Gmail or
  Calendar replica, and specific-sender/web/sports reads still use the general agent.
- Native `effects.py`: per-operation attempts including children of connector
  batches; duplicate/changed-batch replay protection; accepted versus verified
  receipts; bounded read-back reconciliation for supported AgentMail, Gmail and
  Calendar receipts. No provider ID after a crash means uncertainty, never replay.
- Native `performance.py` and adapter: no false generic completion when effects
  lack verification; cancellation checked before tools, read-only reconciliation
  survives restarts, current performance feedback remains in subsequent agent turns.
  Earlier successful parts remain recorded when another batch operation fails.

The policy, personality/rank compiler and shared RAG implementation are retained.
Prepared reads use the authenticated native session and dispatcher; eligible call
text remains in the existing evidence path rather than creating a second persona.

## Evidence collected during implementation

Installed-native staging: 50 unit tests and 5 installed-Hermes adapter tests passed,
plus real current persona/context and evidence-idempotence probes. The direct MCP
read initially revealed an extra string `result` envelope in the native dispatcher;
this was reproduced, fixed and regression-tested. A real empty Gmail query through
that dispatcher subsequently returned a valid response in 1,297 ms. No message sent.

Real GPT-Live synthetic audio exposed duplicate acceptance/result preambles from
multiple context/commentary injections. The final tested path produced one short
"Okay, I'll check it" acknowledgment, one lookup job and one result, with zero
forwarded voiced bytes during caller speech. Known model/team questions created no
jobs. This is controlled audio with a simulated 14-second worker, not a real handset
latency percentile. Prompt compliance alone is not a universal acoustic guarantee.

Focused/backend and production results are recorded in the next release section.

## Explicit remaining limits

- Carrier/handset echo cancellation, acoustic false positives, naturalness and p95
  playout latency require actual telephone acceptance; no echo cause was established.
- Generic shell/browser mutations and arbitrary connector operations are not covered
  by provider reconciliation. Recognized unresolved writes are held for review.
- Multiple independent actions in an utterance share a durable parent request and
  per-effect receipts; a general dependency graph/resource-lock scheduler is absent.
- Topic identity is an application turn anchor plus conservative relevance, not a
  trained semantic topic tracker. Very ambiguous pivots may be held for the summary.
- The phone transport is PSTN/Twilio, not an in-app WebRTC microphone implementation.
- iMessage reconnection and Notion activation remain explicitly deferred.
