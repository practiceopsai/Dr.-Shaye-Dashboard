"use client";

import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { api } from "@/lib/api";

export default function VoiceCommand() {
  const [listening, setListening] = useState(false);
  const [message, setMessage] = useState("");
  const recognition = useRef<any>(null);

  function toggle() {
    if (listening) {
      recognition.current?.stop();
      setListening(false);
      return;
    }
    const Speech = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Speech) {
      setMessage("Voice input is not supported in this browser.");
      return;
    }
    const instance = new Speech();
    recognition.current = instance;
    instance.continuous = false;
    instance.interimResults = false;
    instance.lang = "en-US";
    instance.onresult = async (event: any) => {
      const transcript = event.results[0][0].transcript;
      setMessage(`Heard: “${transcript}”`);
      try {
        await api.voice(transcript);
      } catch (requestError) {
        setMessage(requestError instanceof Error ? requestError.message : "Voice command failed");
      }
    };
    instance.onend = () => setListening(false);
    instance.start();
    setListening(true);
    setMessage("Listening…");
  }

  return (
    <div className="voice-wrap">
      <button className={`voice ${listening ? "active" : ""}`} onClick={toggle}>
        {listening ? <Square size={16} /> : <Mic size={17} />}<span>{listening ? "Stop" : "Talk to Eli"}</span>
      </button>
      {message && <div className="voice-note">{message}</div>}
    </div>
  );
}
