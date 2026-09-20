# Conversational Eli phone connection

The trial connection collects a request, queues it to native Eli, and plays a
completed audio file. It does not provide natural continuous conversation.

The live connection uses Twilio bidirectional Media Streams and OpenAI GPT-Live
with Marin. Audio passes continuously in G.711 mu-law at 8 kHz. GPT-Live handles
listening, speaking, interruptions and short acknowledgments while the existing
native Eli gateway handles delegated questions, memory and actions. Existing
identity, persona/rank, account routing and approval rules remain authoritative.

## Activation

1. Verify that the owning Twilio account has been upgraded and that its actual
   Voice number is provisioned. A trial-assigned shared number is not proof of
   ownership after upgrade. Number purchases require the user's authorization.
2. Set the number's incoming Voice webhook to the backend's `/api/phone/incoming`,
   using POST. Direct Twilio webhooks use standard signatures.
3. Keep the existing caller allowlist and phone access codes. Set
   `TWILIO_PHONE_NUMBER` to the verified owned number, `PHONE_TRIAL_PROXY_ENABLED=false`,
   `PHONE_LIVE_ENABLED=true`, `PHONE_LIVE_MODEL=gpt-live-1`, and `PHONE_VOICE=marin`.
   The existing OpenAI server API key is used. Never expose it to a browser.
4. After a successful PIN check, the server returns `<Connect><Stream>` pointing
   to `/api/phone/live`. The WebSocket must pass the Twilio signature check and
   present a single-use ticket tied to that exact authenticated call. PINs are
   never forwarded to the voice model. Resetting a PIN revokes an active stream.
5. Perform a real call covering greeting, a question and follow-up, interruption,
   an approved harmless task, and hangup with work pending. Test callbacks
   separately. Internal protocol tests do not prove telephone audio quality.

## Durable work and limitations

Client delegations use timestamped user and assistant transcript fragments.
Assistant context is explicitly labeled and cannot itself authorize an action.
Validated requests enter the existing `phone_jobs` queue, keyed idempotently by
call and delegation. Results are returned as soon as native Eli completes; MP3
generation and the old five-second redirect wait are bypassed. Backend outcomes
remain visible in the command center, displaying the caller's words rather than
internal context instructions. Hangup stops audio and polling, not accepted work.

The native gateway retains its existing execution/recovery rules. Interrupting
speech does not prove cancellation of an external action. Changed requests are
delegated and the voice model must wait for a verified outcome. The three-pending-
request limit, patient-information boundary and approval requirements remain.
Memory/rank are accessed through native Eli, not a separate voice memory copy.

The native phone plugin exposes `eli_phone_send_whatsapp` for an explicit caller
instruction. It uses the already-connected native WhatsApp transport, independently
of Twilio. The current authenticated caller, active native request, exact message,
channel and named configured contact or dictated number must match. A durable
receipt prevents the same request from sending twice; uncertain attempts require
reconciliation. Only a successful provider message ID confirms a send. An older
message with the same subject or body does not fulfill a newly requested action.
Eli's own inbox and the caller's personal inbox must be identified separately.

Sessions are limited to twenty minutes and stored voice recordings are disabled.
The model handles duplex turn taking; audio chunks are forwarded immediately.
Questions requiring native work still incur that work's latency. Telephone
bandwidth also limits fidelity compared with a direct app microphone connection.

Live mode defaults off, and enabling it while trial proxy mode is on cannot emit
unsupported Stream instructions. Rollback is `PHONE_LIVE_ENABLED=false`; durable
jobs and the existing request-mode connection remain available.

References checked September 20, 2026:

- https://www.twilio.com/docs/usage/trials/try-out-voice
- https://www.twilio.com/docs/voice/media-streams/websocket-messages
- https://www.twilio.com/docs/usage/security
- https://developers.openai.com/api/docs/guides/live
- https://developers.openai.com/api/docs/guides/live-delegation
- https://developers.openai.com/api/docs/guides/voice-websockets?api=live
