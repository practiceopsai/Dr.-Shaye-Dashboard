"use client";
import { useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { api } from "@/lib/api";

export default function VoiceCommand(){
  const [listening,setListening]=useState(false);const [message,setMessage]=useState("");const recognition=useRef<any>(null);
  function toggle(){
    if(listening){recognition.current?.stop();setListening(false);return;}
    const Speech=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
    if(!Speech){setMessage("Voice input is not supported in this browser.");return;}
    const r=new Speech();recognition.current=r;r.continuous=false;r.interimResults=false;r.lang="en-US";
    r.onresult=async(e:any)=>{const text=e.results[0][0].transcript;setMessage(`Heard: “${text}”`);try{await api.voice(text);}catch(err){setMessage(err instanceof Error?err.message:"Voice command failed");}};
    r.onend=()=>setListening(false);r.start();setListening(true);setMessage("Listening…");
  }
  return <div className="voice-wrap"><button className={`voice ${listening?"active":""}`} onClick={toggle}>{listening?<Square size={16}/>:<Mic size={17}/>}<span>{listening?"Stop":"Talk to Eli"}</span></button>{message&&<div className="voice-note">{message}</div>}</div>;
}

