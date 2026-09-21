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
| R.22 Transport, turn-taking and barge-in | Implemented but needs improvement | Twilio/GPT-Live is already the telephony path; local energy-based clearing lacks adaptive backchannel discrimination. |
| R.23 WebRTC should carry the interactive voice path | Missing | The installed iPhone application opens a PSTN call. It has no in-app microphone/WebRTC transport; adding one is a separate transport feature, not a prerequisite to repair phone calls. |
| R.24 Phone calls need a telephony-specific path | Already implemented and working | Signed Twilio Media Streams use inbound PCMU 8 kHz and continuous PCMU output, with registered callers and telephony call lifecycle. |
| R.25 Choose exactly one turn authority | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.26 Recommended LiveKit turn profile | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.27 Backchannels are not interruptions | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.28 Barge-in must stop local playback before doing anything else | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.29 Bound the downstream audio queue | Implemented but needs improvement | Blueprint guidance compared with the actual GPT-Live/Twilio/native deployment; specific findings and limits are recorded in this report and the detailed rows below. |
| R.30 Preempt intelligently | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.31 Native Realtime configuration | Conflicting / obsolete | Installed path is Twilio Media Streams -> GPT-Live, not legacy Realtime/STT/TTS. No native in-app microphone path currently exists. Vendor-specific settings cannot be copied into Live. |
| R.32 Cascaded versus native realtime | Already implemented and working | The production speaking lane uses native GPT-Live audio. A separate cascaded diagnostic oracle is absent; no evidence warrants replacing the engine. |
| R.33 Repetition, audio cutoffs and output integrity | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.34 Diagnose repetition in the correct order | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.35 Add sequence numbers everywhere audio can be duplicated | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.36 Treat response text as segmented speech | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.37 Do not “fix” exact duplication using temperature | Already implemented and working | No temperature change proposed. Model repetition cannot be inferred from aggregate task logs. |
| R.38 Prevent response cutoffs caused by competing lifecycle events | Implemented but needs improvement | Provider is continuous GPT-Live with incremental fragments, no Realtime response IDs or transcript-done event. Existing event-ID dedup misses same timeline/text with new IDs. Local clear lacks general playback provenance; energy gate can clip output. |
| R.39 Long-term memory, personality and user evolution | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.40 Do not build memory as “one vector database” | Already implemented and working | Production keeps canonical vault records, hybrid retrieval, SessionDB episodes, persona state and relational task receipts separate. |
| R.41 Storage recommendation | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.42 Core memory schema | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.43 Make raw episodes immutable | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.44 Memory write pipeline | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.45 Memory admission policy | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.46 Never overwrite evolving facts | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.47 Retrieval should be hybrid and time-aware | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.48 Memory cards should carry provenance | Implemented but needs improvement | Existing canonical Markdown memory + hybrid retrieval + SessionDB + persona learning/storage already provide provenance, confidence, supersession and rank boundaries. Compare temporal retrieval before any migration; no Postgres migration justified. |
| R.49 Personality and authority are not ordinary memories | Already implemented and working | Installed persona policy/compiler and principal-session gates separate character, authority and private evidence from general recalled facts. |
| R.50 Implementation blueprint, observability and acceptance gates | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.51 Recommended service decomposition | Already implemented and working | Railway LiveCall, native PhoneAdapter workers, task ledgers and existing persona/RAG services are already separated. |
| R.52 Canonical event envelope | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.53 Persist a turn timing record | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.54 Production SLOs | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |
| R.55 Add transport metrics | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |
| R.56 Critical regression scenarios | Implemented but needs improvement | Native full-duplex model is the single speaking authority. App tracks partial acoustic state and keyword relevance; explicit turns/topics/playback/trace ownership needs improvement. |
| R.57 Audio-specific chaos testing | Unable to verify | No pre-change turn-level/audio/network percentile evidence. Synthetic regression and live metadata can establish coverage; handset/carrier acceptance requires actual audio testing. |
| R.58 Use the cascaded engine as a debugging oracle | Missing | No independent STT/text/TTS reference engine exists. It is an optional diagnostic aid; its absence does not establish a defect in the current native speech engine. |
| R.59 Recommended rollout sequence | Implemented but needs improvement | Baseline has regression/CI/Railway release and native maintenance workflows. This run adds saved baseline measurements, staged tests, source backups and a feature-gated read rollout. |
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

All releases listed below are deployed and verified. Report source: actual code, private production metadata snapshot
upgrade-baseline.json, regression tests, and current vendor contracts. The source
documents' opaque citation placeholders are not independent verification.

## API contracts verified

* [OpenAI Live delegation](https://developers.openai.com/api/docs/guides/live-delegation):
  silent thinking versus spoken commentary; app owns tasks/permissions.
* [OpenAI Live event reference](https://developers.openai.com/api/reference/python/resources/live):
  continuous audio/timeline fragments, no invented Realtime cancellation events.

## Tests, changed files, deployment and before/after measurements

The baseline regression suite and reproduced failing cases ran before
implementation. No acoustic p95 or effectively-once guarantee is asserted without
the corresponding test evidence. Human handset/carrier quality remains distinct
from deterministic software and synthetic audio tests.

## Implemented phase: conversation ownership and prepared reads

Implementation deployed in phase 1, followed by the production read activation:

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

Installed-native staging: 52 unit tests and 5 installed-Hermes adapter tests passed,
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

## Requirement verification after implementation

This table refines the baseline matrix with the actual delivered behavior. A source
requirement remains **Implemented but needs improvement** when only bounded cases
are covered. The report does not certify universal exactly-once delivery, acoustic
latency targets, or all optional vendor recommendations.

| Source IDs / detailed requirement | Current status | Concrete evidence and boundary |
|---|---|---|
| D.1-2, D.20, D.38; R.1-4, R.51: conversation/action separation | Already implemented and working | LiveCall audio loops never await ordinary native mutations. Synthetic 14-second lookup kept the voice live; native durable work finishes after hangup. |
| D.3; R.12, R.15, R.20-21: classify execution | Implemented but needs improvement | Closed prepared-read grammar plus general background action lane. No general four-class semantic classifier; complex reads still enter the native agent. |
| D.4-6, D.16-17, D.32-34; R.6-7: durable authoritative task state | Implemented but needs improvement | SQLite task/claim ledger and native work/effect journals own state. Explicit queued/claimed/running/waiting/resumed/completed/failed/uncertain/cancelled. Provider effect state is separate from the agent reply; no arbitrary tool completion guarantee. |
| D.5: user/session/origin/logical/task/authorization/time binding | Already implemented and working | actor + authenticated identity; call_id; origin_turn_id; origin_topic_id; logical_request_id; id; idempotency_key; authorization JSON; created/updated/state. Continuations preserve origin and source-job linkage. Root-bound effect ledger supplies provider IDs and receipts. |
| D.7, D.28; R.19: acknowledge after acceptance, once | Implemented but needs improvement | Delegated speech is withheld until enqueue; one accepted state update. Removed duplicate commentary/context stimuli. Last real-model simulation gave one short acknowledgment. Acoustic/model compliance remains a telephone acceptance item. |
| D.8, D.37; R.26, R.31, R.41: vendor examples | Conflicting / obsolete | Keep existing SQLite, GPT-Live and hybrid vault retrieval. LiveKit/Temporal/Postgres/legacy Realtime APIs cannot simply be copied into this deployment. |
| D.9-10, D.18-19, D.24; R.17: concurrency and multiple actions | Implemented but needs improvement | Reads have an independent claim lane and priority; ordinary actions remain actor-serialized. Multiple requests persist; batch effects deduplicate separately. No general DAG/resource-lock scheduler. |
| D.11-13; R.10-11, R.30: topic-bound result relevance | Implemented but needs improvement | Current/recent turn-topic anchors, exact origin context, stricter topic terms, silent successful mutation policy. Reproduced unrelated-email false positive is fixed. Semantic topic understanding is still model/heuristic based. |
| D.14-15, D.22, D.25-27, D.29, D.31: receipts/retry/reconciliation | Implemented but needs improvement | Per-effect starts/receipts survive crashes and modified connector batches. Known provider IDs support bounded read-back. A crash before saving a provider ID is held uncertain; arbitrary shell/browser effects have no universal reconciliation. |
| D.21: explicit cancellation separate from speech interruption | Already implemented and working | Current-call cancel, authenticated web/iPhone endpoint and UI. Queued work closes, running work blocks subsequent tools; already accepted effects are never claimed undone. |
| D.23: calendar/email example | Implemented but needs improvement | Current-day/tomorrow calendar and latest email have direct reads; authorized mutations keep native policy. Calendar read-back supports recognized connector writes with exact IDs/account and matching returned fields. |
| D.30, D.36; R.50, R.52-55: trace and latency | Implemented but needs improvement | Persistent metadata events link call/turn/topic/response/task with acoustic/first-audio/delegation/persistence/settlement timings. Production cold AgentMail diagnostic completed in 1,367 ms; a handset p95/SLO is not established. |
| D.35; R.56-57, R.61: acceptance regression gate | Implemented but needs improvement | Automated persistence, cancellation, duplicate, partial-batch, rapid-stack, quiet/pivot and synthetic audio checks pass. Handset noise, packet loss and acoustic echo chaos remain unverified. |
| R.5, R.9-10: working conversational state | Implemented but needs improvement | Runtime tracks floor, turn/topic stack, pending jobs, interrupted outputs, generated/playout offsets and connection. Meaningful state changes enter model context; archive and tasks survive calls. No provider response.done/final-transcript event is fabricated. |
| R.8, R.36: generated/sent/played separation | Implemented but needs improvement | Twilio marks cover general voiced output buffer progress. Marks returned after clear are invalidated. Primary audio has no session timestamps, so byte duration is never used to label transcript words heard. Unconfirmed generated speech is stored separately as tentative actor-scoped context, not learned as heard dialogue. |
| R.13: synchronized read models | Missing | A bounded 15-second source snapshot exists; no full Gmail push-sync or Calendar replica. The measured direct path removes the dominant current model/queue delay without building a private-message mirror. |
| R.14, R.18: freshness/narrow requests | Already implemented and working | Direct reads return source, observed time, cached/live and coverage; Gmail requests only one metadata record, calendar bounds one day/25 records in the source timezone, AgentMail remains bounded. |
| R.16: hard deadlines | Implemented but needs improvement | Prepared reads have a 12-second caller-result deadline. A timed-out blocking read thread may finish later but cannot become a mutation or inject its stale result. General native actions retain their existing timeouts. |
| R.22, R.27-28: turn-taking/backchannels | Implemented but needs improvement | Immediate buffered-audio clear and old-output fence preserve authorized actions. Zero overlap bytes in the controlled test. Local energy detection is not adaptive acoustic/semantic VAD; short real-world backchannels need acceptance testing. |
| R.23: in-app WebRTC | Missing | The TestFlight app currently calls the real telephone number. No new microphone/WebRTC transport was built in this phone repair. |
| R.24-25, R.32: telephony and one speaking authority | Already implemented and working | Twilio PCMU media uses one GPT-Live connection/output consumer. There is no second TTS engine or response.create loop. |
| R.29: bounded downstream audio | Implemented but needs improvement | Chunks are forwarded immediately and Twilio buffer is cleared on interruption. No sentence/MP3 backlog. Full carrier/client jitter and queue latency are not measurable from server marks alone. |
| R.33-35, R.38: repetition/cutoff diagnosis | Implemented but needs improvement | Same-span transcripts, audio event/timeline replay and inbound sequence replay are guarded. Exact outgoing-media loopback is diagnosed via short-lived hashes; acoustic echo cancellation is not claimed. Duplicate context/commentary preambles were reproduced in real-model staging and removed. |
| R.37: no temperature workaround | Already implemented and working | No generation temperature change. Fixes address reproduced event, routing and lifecycle causes. |
| R.39-40, R.42-49: continuity and memory | Implemented but needs improvement | Existing persona compiler/evidence/learning/policy and hybrid vault retrieval retained. Source audit confirms confidence, supersession, contradiction and principal-session gates. Phone episodes enter SessionDB and eligible evidence once. Full temporal-question quality is not benchmarked by this release. |
| R.58: cascaded diagnostic oracle | Missing | Controlled native GPT-Live audio tests exist, but no independent STT/text/TTS reference engine. Building a second engine is not needed to fix the reproduced duplicate event paths. |
| R.59-60: incremental implementation | Already implemented and working | Baseline f9d331d; f4c7234 backend with reads off; native backup/restart; production direct read; reads enabled with b06e0ac app release; ad0ee2a follow-up guards; 4d4262e playback provenance. Each retains source rollback and existing durable data. |

## Test scenario coverage

| Requested scenario | Evidence | Limit |
|---|---|---|
| Rapid topic pivot during work | Presence/continuity tests, unrelated-email regression and real-model synthetic 14-second lookup/topic-pivot test | Semantic relevance is conservative, not perfect. |
| Multiple actions in one utterance | Complete fragment capture and per-child batch receipts/partial-outcome tests | General native agent still chooses execution order. |
| Duplicate tool call | Root/effect identity, replay and changed-batch tests | Unrecognized shell effects excluded. |
| Worker crash after write | Reopen durable start/accepted ledger, never replay; reconcile saved provider ID by read | Missing provider ID stays uncertain. |
| Voice drop during action | Existing disconnect/hangup persistence tests | No live carrier outage deliberately induced. |
| Barge-in while acknowledging | Immediate clear/output fence and synthetic overlapping speech | Handset audible result needs actual call. |
| Explicit cancellation | Queued/running cancellation and iPhone double-tap regression | Irreversible effects already accepted may finish. |
| Partial batch failure | Independent child verified/uncertain receipts and truthful completion guard | Unknown children remain for review. |
| Delayed lookup after pivot | Result held, not marked heard; origin included when relevant again | Ambiguous topics may remain in summary. |
| TTS/STT echo | Exact media loopback diagnostic fixture; single audio sender verified | Physical acoustic echo is not simulated by an exact-byte fixture. |
| Duplicate final transcript | GPT-Live has fragments, not finals; identical timeline/text with new ID is deduplicated | No fictional provider final event used. |
| Reconnect replay | One activated stream ticket and durable origin/delegation/effect IDs; sequence replay rejected | New telephone calls are distinct sessions. |
| Simultaneous pending tasks | Independent read lane plus distinct origins for rapid stacked requests | Ordinary mutations remain actor-serialized. |
| Very fast interruption | First voiced input clears Twilio buffer; cleared marks never count heard | End-to-end carrier clearing time unknown. |
| Short pauses vs end-of-turn | Fragments remain one request until audio and transcripts settle; post-commit speech creates new origin | Long thoughtful pauses remain a voice-model acceptance case. |

## Production verification and rollout record

Verified 2026-09-21 UTC:

- Native source release: `ad0ee2abbce852c18088ab4348a76024b95a6333`.
  Final backend playback-provenance correction: `4d4262eec1a1072fd12c62ec12ddae931502542e`.
  Every production phone-module hash matches the repository after newline normalization.
- Web/iPhone cancellation UI: `b06e0acccbeb330540b50bd18ce0b8b063db9ece`.
  Expo production update group `f22d7c87-09ec-42b0-8514-27c71d3fe053` was published
  against the compatible installed runtime. This is an OTA update, not a new binary.
- CI: 173 backend tests, 46 web tests/build, 52 native unit tests, 31 iPhone tests,
  mobile typecheck/export all passed. Installed native staging also passed 5 gateway
  adapter tests and the current identity/persona/evidence probes.
- Native gateway running, phone connected, no drain left behind, zero active agents
  at verification; configuration preserved across both controlled restarts.
- `PHONE_FAST_READS_ENABLED=true`, GPT-Live enabled, PIN false, follow-up mode app.
  Bridge heartbeat age 0.099 seconds at final capture; both identity-scoped personality
  packets were 51 seconds old and populated.
- No test email, text, WhatsApp or outbound telephone call was sent. Production
  diagnostics were read-only. iMessage/Notion were not reconnected.

| Measurement | Before | After | Interpretation |
|---|---:|---:|---|
| Comparable controlled native inbox reads | 10.4 s and 15.96 s | 1.367 s queue-to-result | One uncached new production sample; not an acoustic percentile. |
| Actual provider inbox read | 186 / 405 ms historical successes | 421 ms | Main saving came from removing general model/queue overhead. |
| New read claim | Historical mixed-task median 652 ms | 230 ms | Independent read lane; workload/sample populations differ. |
| New native read processing | Historical mixed-task median 15,217 ms | 797 ms | No model round in prepared read. |
| Gmail empty-query probe | 875 ms direct MCP | 1,297 ms via native dispatcher | Validates current connector path, not a before/after optimization claim. |
| Synthetic voice overlap | Original real-call value unavailable | 0 voiced bytes forwarded over caller speech | Does not establish carrier/handset acoustic delay. |

Release CI records: [final backend and web](https://github.com/practiceopsai/Dr.-Shaye-Dashboard/actions/runs/35562569371),
[native guards](https://github.com/practiceopsai/Dr.-Shaye-Dashboard/actions/runs/35562079446),
[iPhone verification](https://github.com/practiceopsai/Dr.-Shaye-Dashboard/actions/runs/35561902025),
[iPhone publication](https://github.com/practiceopsai/Dr.-Shaye-Dashboard/actions/runs/35561942775).
Private source verification, native backup manifests, staged output and synthetic
checks are retained in the dated production repair record.

Rollback points: the baseline public code is `f9d331d`; phase-one public code is
`f4c7234`. Turn off `PHONE_FAST_READS_ENABLED` and redeploy to disable routing into
the new lane while retaining durable jobs. Original native files are in the first
backup manifest; phase-one native files are in `backup-v2`. A full rollback restores
matching backend/native source together. Do not roll a live task database back to
an older snapshot, since that could erase receipts and invite duplicate effects.

The user has been asked to perform the final real-phone acceptance check. This
report intentionally leaves acoustic SLOs, a full synchronized read replica,
in-app WebRTC and unrestricted-provider reconciliation unverified or missing;
it does not describe the entire blueprint as complete.

### Final provenance correction

A real-model staging check exposed another clock mismatch: primary GPT-Live audio
chunks omit session timestamps, while transcript fragments use session time.
Cumulative audio byte duration therefore cannot prove that particular transcript
words were played. The implementation now keeps those clocks separate. Generated
assistant text with unverified playback is retained as tentative, actor-scoped
context; it is excluded from heard dialogue and persona evidence. Confirmed user
speech and durable task receipts retain their existing memory routes. This follows
[the provider transcript/playback contract](https://developers.openai.com/api/docs/guides/live-conversations#manage-speech-and-transcripts).
Precise per-word playback provenance would require additional timestamp alignment;
this release does not pretend to have it.

The additional real-model topic-pivot test passed: the caller switched to a general
question about short meetings while a 14-second lookup continued. Eli answered the
new topic, one task completed, and the old email subject was held in the summary.
No old result was spoken and zero voiced bytes were forwarded over caller speech.

The synthetic audio records were captured before the final provenance correction.
Their generated-text, job-count and overlap measurements remain useful. Any older
per-fragment `played` labels in those raw records are not evidence that particular
words were heard; the final implementation and regression tests enforce the stricter
clock separation described above.

## Reproduction and evidence locations

- `backend/tests/test_phone_upgrade.py`: origin/replay isolation, independent read
  claim, queued/running cancellation, output fence, echo observation, transcript
  clock separation and unconfirmed-context retention.
- Existing `test_phone_live.py`, `test_phone_presence.py`, `test_phone_continuity.py`:
  real transport contract, hangup preservation, quiet result delivery, clarification,
  callback boundaries and late-topic origin. Updated assertions retain behavioral checks.
- `integrations/hermes_phone/test_reads_effects.py` and `test_operations.py`:
  source/identity/cache contracts, read-back failure, crash recovery, batch dedup,
  existing provider IDs, incomplete outcomes and status questions versus instructions.
- Web and iPhone phone-page tests exercise cancellation without claiming an already
  accepted provider effect was reversed.
- Private production evidence: `upgrade-baseline.json`, `release-verification.json`,
  `deployment.json`, `deployment-v2.json`, `tests-staged.txt`, `probe_read.log`, and
  synthetic normal/fast/pivot audio verification records. These contain no API keys.

No automatic learning policy was granted new authority. Measured slow/failed tool
routes still enter the existing bounded performance feedback, and eligible caller
facts still pass the existing persona admission/contradiction process. Corrections
from this maintenance run are recorded as operator instructions with provenance,
not misrepresented as Dr. Shaye's personal preferences.
