"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Mic, Send, Square, X } from "lucide-react";
import { api } from "@/lib/api";

type ChatMessage = { id: string; role: "user" | "assistant"; text: string };
type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: { transcript: string }[][] }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type RecognitionConstructor = new () => Recognition;

const welcome: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Tell me what should change, what matters more, or what you want handled. I will write it back to Eli and confirm what happens next.",
};

export default function VoiceCommand({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const [sending, setSending] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([welcome]);
  const recognition = useRef<Recognition | null>(null);

  useEffect(() => () => recognition.current?.stop(), []);

  function append(role: ChatMessage["role"], text: string) {
    setMessages(current => [...current, { id: `${role}-${Date.now()}-${current.length}`, role, text }]);
  }

  async function sendTranscript(value: string) {
    const transcript = value.trim();
    if (!transcript || sending) return;
    append("user", transcript);
    setDraft("");
    setSending(true);
    try {
      const response = await api.voice(transcript);
      append("assistant", response.message);
      if (response.next_brief_refresh) onChanged();
    } catch (requestError) {
      append("assistant", requestError instanceof Error ? requestError.message : "I could not record that request. Please try again.");
    } finally {
      setSending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendTranscript(draft);
  }

  function toggleListening() {
    if (listening) {
      recognition.current?.stop();
      setListening(false);
      return;
    }
    const browserWindow = window as typeof window & {
      SpeechRecognition?: RecognitionConstructor;
      webkitSpeechRecognition?: RecognitionConstructor;
    };
    const Speech = browserWindow.SpeechRecognition || browserWindow.webkitSpeechRecognition;
    if (!Speech) {
      append("assistant", "Microphone input is not supported in this browser. You can still type your request below.");
      setOpen(true);
      return;
    }
    const instance = new Speech();
    recognition.current = instance;
    instance.continuous = false;
    instance.interimResults = false;
    instance.lang = "en-US";
    instance.onresult = event => {
      const transcript = event.results[0][0].transcript;
      setListening(false);
      void sendTranscript(transcript);
    };
    instance.onend = () => setListening(false);
    instance.onerror = () => {
      setListening(false);
      append("assistant", "I could not hear that clearly. Please try the microphone again or type your request.");
    };
    instance.start();
    setOpen(true);
    setListening(true);
  }

  function close() {
    recognition.current?.stop();
    setListening(false);
    setOpen(false);
  }

  return (
    <div className="voice-wrap">
      <button className={`voice ${listening ? "active" : ""}`} onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}>
        <Mic size={17} /><span>Talk to Eli</span>
      </button>
      {open && (
        <section className="eli-chat" role="dialog" aria-modal="false" aria-labelledby="eli-chat-title">
          <header>
            <div><span className="eli-chat-presence" /><div><b id="eli-chat-title">Talk to Eli</b><small>Requests are written back to Eli Agent</small></div></div>
            <button type="button" onClick={close} aria-label="Close Talk to Eli"><X size={17} /></button>
          </header>
          <div className="eli-chat-messages" aria-live="polite">
            {messages.map(message => <div className={`eli-message ${message.role}`} key={message.id}>{message.text}</div>)}
            {sending && <div className="eli-message assistant pending" role="status">Eli is recording your request…</div>}
          </div>
          <form className="eli-chat-compose" onSubmit={submit}>
            <button type="button" className={`eli-mic ${listening ? "active" : ""}`} onClick={toggleListening} disabled={sending} aria-label={listening ? "Stop listening" : "Speak to Eli"}>
              {listening ? <Square size={16} /> : <Mic size={17} />}
            </button>
            <label className="sr-only" htmlFor="eli-chat-input">Message Eli</label>
            <textarea id="eli-chat-input" value={draft} onChange={event => setDraft(event.target.value)} placeholder={listening ? "Listening…" : "Type a request or use the microphone"} rows={2} disabled={sending} />
            <button type="submit" className="eli-send" disabled={sending || !draft.trim()} aria-label="Send to Eli"><Send size={17} /></button>
          </form>
          <p className="eli-chat-policy">External actions remain approval-gated. Do not include patient information.</p>
        </section>
      )}
    </div>
  );
}
