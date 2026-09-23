# Calls requested in chat

Fabio and Dr. Shaye can request one live call from their registered direct-message
conversation. "Call me" resolves to the authenticated sender. "Call Dr. Shaye and
tell him the report is ready" resolves to the configured contact and carries the
supplied message. The same behavior works in either direction. An absent message
for the other person prompts a clarification attached to that task; self-callbacks
need no topic. Other recipients retain the existing exact-call approval flow.

The text ingress persists the original transport message ID, the structured
planner creates a `call` job, and the native prepared-action worker submits it
through the authenticated bridge. The backend owns Twilio submission, using the
existing one-attempt worker. A unique source job prevents repeat submissions.
Cancellation and correction holds are checked again immediately before dialing.
Provider uncertainty never causes an automatic redial.

The outbound record retains both requester and recipient identities. On answer,
the live conversation uses the recipient's identity, memory scope, and permissions.
The opening attributes the supplied message to the requester. It does not transfer
the requester's conversation history or grant their identity to the recipient.

Acceptance by Twilio proves call submission, not message delivery. Original-chat
notifications distinguish queued, accepted, unanswered/busy/failed, and ended
states. Neither call completion nor generated speech proves every word was heard.

Examples:

- Fabio: "Call me."
- Fabio: "Call Dr. Shaye and tell him I'm running ten minutes late."
- Dr. Shaye: "Call me."
- Dr. Shaye: "Call Fabio and tell him the report is ready."

The existing active iMessage connection is Photon. The separately deferred
BlueBubbles connection is not required for this flow. No unsolicited deployment
test calls or messages are sent.
