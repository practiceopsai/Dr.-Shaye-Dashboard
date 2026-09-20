# Eli phone channel

The phone service uses Twilio for calls and speech recognition, OpenAI Marin for
spoken responses, and the existing native Hermes gateway for Eli's actual work.
It does not replace the model, memory provider, persona, earned rank, or approval
rules with a separate voice chatbot.

## Setup

1. Sign in at `/phone` with the approved Google account and create a private
   eight digit phone code. Only its salted hash is stored. Resetting it invalidates
   authenticated calls. The registered phone number is configured by the operator.
2. Copy the **private Twilio webhook** from your signed-in Phone page into
   Twilio > Inbound > Custom, select POST and save. Copy the entire URL, including
   its query parameters. Keep it private and use the URL for the selected caller.
   The original `/api/phone/preview` remains a harmless standalone voice sample.
3. On the trial, verify each caller and recipient in Twilio. Use the trial number
   assigned by Twilio for that recipient; it may differ between recipients.
4. Call from the registered number and enter the code. Request a task normally.
   Press one when offered to authorize one callback about that specific request.

## Same Eli and continued work

`integrations/hermes_phone` installs as the external `eli_phone` plugin. It polls
our private queue and dispatches a verified direct-message event through the
existing gateway handler, response policy, model routing, memory, persona, and
tool hooks. Each person has a stable phone session. Long-term context stays in
Eli's existing vault and memory provider. The principal allowlist is retained;
operator sessions do not acquire principal memory access.

The persona evidence gate needs the configured `principal_platforms` list to
include `eli_phone`. Its existing user-ID and direct-message checks remain.

Requests are saved before Twilio receives an acknowledgement. Hanging up does
not cancel the native agent turn. The native operation journal retains results
for idempotent delivery. Interrupted work is marked uncertain and never replayed
automatically. Reconcile an uncertain request before further work for that actor.
A completed turn means Eli returned a reply; that reply may describe an approval
requirement or incomplete action.

Marin reads the returned reply. Private audio uses signed URLs lasting ten minutes
and is cleared after 24 hours. Audio tokens are omitted from access logs. The
Phone page shows each caller's saved requests, replies and outstanding decisions.

## Outbound calls

Prepare a call in the Phone page, or ask Eli to use `eli_phone_propose_call`.
The exact recipient, purpose and spoken message are shown for approval. Approval
expires after one hour. Only explicit approval or a keypad request for one callback
can place a call. Uncertain submissions are never automatically redialed. Twilio
call status is separate from the agent result; completion does not prove listening.

Callbacks require the private code before playing a personal result. Calls to
other people use an AI introduction and the exact approved message, then collect
one response. They do not give the recipient private memory access, authority to
direct Eli, or permission to negotiate commitments. Replies are third-party data,
available through `eli_phone_status` and the Phone page. Further calls or
commitments require their own approval.

Trial destinations must be verified in Twilio. Its current API documentation
also lists only template URLs for trial call creation, despite supporting custom
TwiML in the trial UI. Custom outbound calling must therefore be verified on the
actual account before claiming it works. Errors remain visible in the Phone page;
this integration does not upgrade an account or purchase a number.

## Runtime and verification

Backend secrets: `TWILIO_AUTH_TOKEN`, `OPENAI_API_KEY`, `PHONE_BRIDGE_TOKEN`.
Other settings: `PHONE_ENABLED`, `PHONE_OUTBOUND_ENABLED`, `PHONE_PUBLIC_URL`,
`TWILIO_ACCOUNT_SID`, `TWILIO_PHONE_NUMBER`, `PHONE_CALLERS_JSON`, `PHONE_VOICE`.
The backend requires its persistent `DASHBOARD_STATE_PATH`.

`PHONE_TRIAL_PROXY_ENABLED` defaults to false. On this trial, an actual inbound
call on September 20, 2026 reached the backend without `X-Twilio-Signature`, while
the account and call IDs were present. With the trial option enabled, unsigned
requests require a private HMAC capability tied to the exact route and caller
(entry) or call ID (continuation). Continuations expire after 20 minutes. Outbound
answer/status URLs are bound to their approved call ID. A direct REST lookup,
bounded to 2.5 seconds, independently confirms the exact account, call SID,
From/To endpoints, recent creation and active call status. Provider failures deny
access. Caller allowlisting, PINs, call-step nonces and exact approvals still apply.
Normal signed webhooks retain signature verification; a supplied invalid signature
does not fall back to trial authentication. No public endpoint issues capabilities.
Private URLs are returned only to their signed-in owner with no-store headers,
and query strings are redacted from application access logs. Rotating the bridge
token invalidates the capabilities; disable trial mode after migration to direct
signed Voice webhooks. Trial callbacks still need a real acceptance test.

The native plugin uses the same bridge token in its protected environment and
`plugins.entries.eli_phone.settings` for the URL and pinned identities. Enable
`platforms.eli_phone` with a direct-message allowlist and the relevant existing
tools. No native agent HTTP listener is exposed publicly.

Backend tests cover signatures, PIN isolation and lockout, duplicate webhooks,
continued work, private audio, actor isolation, exact approvals, no repeat dialing
after ambiguous failures, and conversation continuations. Native tests use the
installed Hermes imports before activation. Real inbound and outbound calls remain
separate end-to-end checks with the user.

Trial conversations use Gather, Play, Pause and Redirect. They include pauses
while Eli works and end before the ten-hop budget. This is not full-duplex audio.
Twilio currently blocks Stream and ConversationRelay on trials, limits TwiML
fetches to five seconds, and limits a call to ten minutes.

References: [Twilio trial Voice](https://www.twilio.com/docs/usage/trials/try-out-voice),
[OpenAI speech](https://developers.openai.com/api/docs/guides/text-to-speech).
