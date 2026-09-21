# Concurrent clarification and action receipts

The September 21 handset call exposed a task-state failure after the earlier single-message repair. This report describes observed production records; synthetic delivery tests are labeled separately.

## Observed breakpoints

Times below are seconds from the beginning of the 465-second call. Task IDs are abbreviated; full transcripts, tool events and receipts are retained in the private maintenance evidence.

| Time | Request or event | What actually happened |
| --- | --- | --- |
| 172 | Find an article, `654816c5` | Saved waiting for its topic. |
| 184 | AI article and delivery to Fabio, `81e55497` | Created another root instead of extending the first request. Asked source and delivery channel. |
| 205–219 | Any source; WhatsApp, `d8e282f2` | Created a separate clarification job. Its “Got it” result was marked completed while the article remained unfinished. |
| 219–323 | Article continuation, `ed9f7e39` | Spent about 104 seconds on skill/context/browser discovery, then an RSS lookup. Browser routes hit CAPTCHA/access failures. |
| 222 | Calendar invitation, `38c18663` | Saved waiting for details. |
| 230 | “Email, two o'clock tomorrow, label it AI Test Meeting,” `83baded1` | Became a new ambiguous root. The original invitation still waited. |
| 259 | Calendar, Fabio, Pacific, 2:00, `cc73a3e3` | Created a clarification job that itself asked for date and duration. |
| 273–335 | Tomorrow, one hour, `ae7d1c40` | Answer waited behind article work sharing the global resource. It eventually completed as answer text, not a calendar operation. |
| 295 | First article send attempt | Guard rejected the selected URL because it was absent from literal caller dictation. No message was sent. |
| 331–347 | Calendar answer continuation, `f280065d` | Completed with “Tomorrow at 2:00 PM Pacific Time, for one hour.” This was not an event receipt. |
| 341–368 | Spoken completion | Eli said: “I sent the article and set the one-hour AI Test Meeting for tomorrow at 2 p.m. Pacific, with Fabio invited.” No calendar-create tool had run, and the article send had been rejected. |
| 356 | Article approval job, `219b8116` | Completed with “Approved.” The delivery task remained open. |
| 373 | Calendar continuation, `ae8b184b` | Asked again whether to create a calendar event or send email. Earlier intent had been lost between roots. |
| 390 | Second article send attempt, `430ed4d6` | Same literal-message rejection despite approval. |
| 417 | Repeated article question | Asked the caller to dictate the whole URL. |

Historical outcome for these two requested actions: **0 calendar invitations and 0 article messages sent**. Several answer-routing jobs were incorrectly presented as successful work. An unrelated simple email did have a verified provider receipt but was mislabeled failed because its receipt status was `verified`, while the completion check accepted only `sent`. That message must not be resent.

## Execution after the repair

1. GPT-Live continues to answer from session context and owns conversation/audio. Work intake persists the caller's words.
2. The structured planner separates independent jobs. Current questions include their task ID, original request and saved details.
3. An answer updates the selected task directly in a database transaction. It creates a revision under the same root, retaining original words, every answer and the question IDs. It does not run an extra Hermes answer job or produce a completed-action notice.
4. The planner rebuilds that one task before processing the next caller fragment. Missing information keeps it waiting; complete tasks become independently runnable. Pure clarification planning never waits for the native execution pool.
5. Calendar and article work use bounded native operations and the existing transports/policies. Each action has its own durable receipt and cannot inherit its sibling's success.
6. Verified results update the voice model's reference state. `completion_allowed` is true only for a completed action with its required receipt. Answer saved, queued, running, waiting and uncertain states cannot authorize a completion claim. No new forced speech, local audio clear or VAD control is introduced.

## Calendar hosting

Eli asks which account should host each invitation; she does not choose by default.

- **Eli's email:** send an RFC 5545 invitation from Eli's configured identity to both Dr. Shaye's configured primary address and the guest. Verify the provider message, recipients, subject and attachment bytes. This sends an invitation recipients can accept; it does not directly write Fabio's calendar.
- **Dr. Shaye's calendar:** use the connected primary personal Google Calendar, with guest notifications enabled. Read back the event and compare title, start/end and attendees. Existing principal access restrictions remain in force; operator access does not grant a private-calendar mutation permission.

The account choice and event details survive later clarification. A started or uncertain attempt is retained for reconciliation, never automatically repeated.

## Article delivery

For a bounded “find an AI article, any source, send its link” request, perform a timed RSS lookup and persist the selected title/URL as an immutable artifact attached to the task, recipient and channel. Only that exact saved artifact can satisfy the derived-content guard. Unrelated generated messages still require their own authorization. A caller who authorized selection and delivery need not dictate an opaque URL.

Search failure, unavailable messaging, missing receipts or failed verification leave an explicit failure/uncertain result. “Latest” means the newest usable result returned by the bounded feed, not a claim to exhaustive coverage of the internet.

## Validation

Backend transaction tests cover interleaved answers, root preservation, replan ordering, missing hosting account, independent claiming and receipt-gated completion. Native tests cover both hosting routes, principal restrictions, both invitation recipients, provider read-back, article selection/delivery, altered-artifact rejection and no replay after timeout.

Release checks and real-model replay results are recorded with the deployment evidence. Simulated provider success is not evidence of a delivered email, message or calendar invitation. Final handset acceptance must confirm actual provider receipts separately.

The actual GPT-5.6 Luna planner replay preserved two tasks across four utterances and multiple clarification revisions: two fully specified actions, zero remaining questions, zero orphan roots. The GPT-Live-1 cloud voice replay completed both simulated deliveries, answered a topic change, and accurately reported the invitation and WhatsApp article when asked. It forwarded all 36,200 ms of generated voiced audio, issued no local audio clear, and reported no provider errors. Both completions had distinct simulated receipts. No real invitation or message was sent by these rehearsals.

The rehearsals also caught a channel-case mismatch (`WhatsApp` versus `whatsapp`) and unnecessary requests for known contact addresses. Channel values are now constrained and normalized, configured contacts are supplied to intake, and continuation evidence is retained verbatim rather than re-quoted by the planner. Current-task status questions use the local execution ledger.
