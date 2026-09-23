# Text response handoff repair

Eight incoming messages reached the existing Photon text adapter but were
intercepted by the shared task hook and never submitted to the backend. Ordinary
messages such as “Who are you?”, “Hello?” and punctuation were affected whenever
the actor had any unanswered task, including a question from an older phone call.
The normal native conversation route still had recent successful reply records.

The text pump reconstructed `SessionSource` as `SimpleNamespace`, omitting the
`delivered_via_upstream_relay` default required by the installed gateway's real
authorization method. That raised `AttributeError` before backend submission.
The outer exception handler hid its type and retried the first broken item about
once a second, blocking every following message. Mock-only tests accepted any
sender object and did not exercise that contract.

## Repair and validation

- Restore the real gateway `SessionSource` with its safe deserialization method.
  Re-check authorization without restoring upstream-relay trust from storage.
- Keep ordinary questions and greetings in the existing native conversation path.
  A free-form answer enters the shared ledger only after a clarification was
  successfully delivered to that actor in the same platform and conversation.
- Retry failures per item with bounded backoff and content-free error types.
  New messages and healthy items are not blocked by one failed item.
- Preserve uncertain send outcomes without resending them automatically.
- Retain the eight incorrectly intercepted historical messages for review; do not
  reinterpret or automatically execute them as new tasks during the repair.

All 93 native integration unit tests pass. `contract_cross_channel.py`, run with
the installed Hermes Python/source against a temporary home and database,
reproduces the old authorization error and validates the replacement sender,
authorized/unauthorized identities, exactly one simulated handoff/reply, and
normal conversation routing while a real task question is open. No real messages
are sent by that test. Run it on native gateway upgrades as well as unit tests.

The existing text channel and the dedicated Twilio voice number are distinct.
The inspected Twilio number has SMS capability but no inbound SMS webhook or
Twilio message records. This repair addresses the confirmed Photon handoff
failure; it does not establish SMS delivery on that separately configured number.
BlueBubbles remains disconnected as previously deferred.

Production deployment and a live delivery check must be recorded separately from
the isolated test results. Voice audio/turn-taking, backend task execution,
personality and memory are outside this code change.
