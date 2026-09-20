# Eli phone integration

## Current stage: Marin voice preview

The backend serves a short, explicitly labeled synthetic introduction using
OpenAI's Marin voice, with warm, clear feminine delivery and a conversational
pace. It identifies Eli as an AI assistant. The public preview
contains no private information and makes no runtime requests to OpenAI or Eli.

In Twilio's trial console, select **Inbound → Custom**, use **POST**, and set
the webhook to `https://<backend-domain>/api/phone/preview`. Calling the trial
number from a verified phone plays the preview and ends the call. It does not
yet accept requests or hold a conversation.

`RAILWAY_PUBLIC_DOMAIN` supplies the canonical audio URL. The backend does not
trust caller-supplied host headers to construct that URL. The bundled MP3 is
available at `/api/phone/preview.mp3`. The TwiML adds a version query parameter
to the audio URL when the voice changes, so cached audio does not preserve the
previous voice. The configured Twilio webhook URL stays the same. Preview
routes deliberately accept public requests because they serve only this fixed,
non-sensitive audio.

## Work required for actual conversations

- Connect a verified caller to the existing Hermes runtime and its current
  memory, behavior, authority limits, and approval process.
- Add a second identity check before private context or actions; caller ID
  alone is not sufficient. Distinguish the operator from the principal.
- Validate Twilio webhook signatures and bind each conversation to its call.
- Use durable, deduplicated work for agent turns and action execution. Do not
  retry ambiguous external writes or announce completion without evidence.
- Generate Marin audio from Eli's actual reply; authenticate access to private
  audio and give it a short lifetime.
- Save requests and verified results in the command center. Requests that need
  approval remain pending until the exact action has been confirmed.
- Exercise real inbound calls, failed services, dropped calls, and concurrent
  requests before treating the phone channel as operational.

The existing dashboard's direct external execution remains disabled. The
Hermes conversation API was not enabled at the September 20 inspection. A
voice preview does not change either setting.

## Trial constraints

Twilio currently permits `Gather`, `Say`, and `Play` on trials, but blocks
`Stream` and `ConversationRelay`. Its documented limits include a five-second
TwiML fetch timeout, ten action/redirect hops, ten minutes per call, and 75
total voice minutes. The trial implementation needs asynchronous work and a
bounded polling/turn budget; it cannot assume an unlimited conversation.
OpenAI speech generation is billed separately from the Twilio trial.

References: [Twilio trial Voice](https://www.twilio.com/docs/usage/trials/try-out-voice),
[OpenAI speech](https://developers.openai.com/api/docs/guides/text-to-speech),
[Hermes API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server).
