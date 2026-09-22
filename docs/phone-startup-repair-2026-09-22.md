# Voice startup regression

The first handset call after the shared-ledger rollout exposed a presentation
regression. Automatic voice updates expanded from the current call to all open
tasks belonging to the caller. At 18–19 ms after opening, 17 historical tasks
produced 35 thinking appends. Several contained unanswered calendar questions.
The model acknowledged this burst over approximately 6.3–8.9 seconds; two chunks
were retried while acknowledgments were delayed.

The provider transcript records the opening greeting at 1.6–4.0 seconds, extra
greetings/check-ins at 7.4–9.6 seconds, and “Which calendar should I check?” at
11.6–13.0 seconds. No calendar request from the current caller preceded it. The
question matches an old task in the injected backlog. The fallback intake check
had also expanded to historical questions, allowing unrelated new-call speech to
be considered a possible clarification answer.

The trace contains no discarded audio, local interruption command, provider error
or exact-media echo detection. Raw handset audio was not retained; this does not
rule out acoustic echo or independently prove every generated word was heard.
The model owns the continuous audio stream. This repair does not change VAD,
audio filtering, sample forwarding or local barge-in behavior.

## Repair

- Scope automatic task state to logical tasks associated with this call. A later
  text-channel revision of the same logical task remains visible.
- Scope fallback clarification capture to questions in this call.
- Keep explicit prior-call recall and historical open-task status available.
- Treat historical context as reference, not an invitation to resume questions.
- Request one opening greeting, then let the caller speak. A validation update
  is not a turn boundary; ask a relevant unanswered clarification only after the
  caller finishes their thought.

The actor-wide ledger, durable queue, receipts, task versions, personality and
memory integrations remain in place. Historical tasks are preserved; this repair
does not execute, cancel or delete them.

## Validation

55 targeted backend tests passed, including new regressions for silent startup
with a historical question, no accidental intake from an introduction, explicit
historical status retrieval, and visibility after a cross-channel revision.

Private voice probes use the observed backlog, the real voice model, synthetic
caller audio and an isolated database without execution workers or external
actions. Network-aborted runs are recorded separately, not counted as passes.
The final server-side probe gave one opening greeting, remained quiet until the
caller spoke, answered model and arithmetic questions, injected zero historical
task states and created zero jobs. A relay probe does not establish PSTN or
microphone behavior; a handset retest remains necessary.

Release `c54692cb3b016d09ee951e7b94583a807b0963e1` was deployed through successful
CI (248 backend tests, 46 frontend tests and frontend build). The installed source
hashes match the tested files. Backend health returned 200, the OpenAI voice
handshake returned `session.started`, and the native bridge heartbeat was fresh.
A fresh-call projection returned zero automatic task updates while explicit
historical status still exposed the preserved open tasks.
