"use client";
import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowRight, Brain, CalendarDays, CheckCircle2, CircleAlert, Command, LockKeyhole, RefreshCw, Sunrise } from "lucide-react";
import ActionCard from "@/components/ActionCard";
import VoiceCommand from "@/components/VoiceCommand";
import { api, Card, Dashboard, Lane } from "@/lib/api";

const lanes:{key:Lane;label:string;eyebrow:string}[]=[{key:"now",label:"Move now",eyebrow:"Time-sensitive"},{key:"protect",label:"Protect",eyebrow:"Important, not urgent"},{key:"delegate",label:"Unblock",eyebrow:"Delegate or decide"},{key:"monitor",label:"Keep watch",eyebrow:"No action yet"}];
export default function Home(){
  const [token,setToken]=useState("");const [ready,setReady]=useState(false);const [data,setData]=useState<Dashboard|null>(null);const [loading,setLoading]=useState(false);const [error,setError]=useState("");
  useEffect(()=>{const t=sessionStorage.getItem("eli_token")||"";setToken(t);setReady(Boolean(t));if(t)load(false);},[]);
  async function load(refresh=true){setLoading(true);setError("");try{setData(await api.dashboard(refresh));}catch(e){setError(e instanceof Error?e.message:"Unable to load command center");}finally{setLoading(false);}}
  function unlock(e:React.FormEvent){e.preventDefault();sessionStorage.setItem("eli_token",token);setReady(true);setTimeout(()=>load(false),0);}
  const grouped=useMemo(()=>Object.fromEntries(lanes.map(l=>[l.key,data?.cards.filter(c=>c.lane===l.key)||[]])) as Record<Lane,Card[]>,[data]);
  if(!ready)return <main className="login-page"><div className="login-mark"><Command size={23}/></div><section className="login-card"><p className="kicker">Private command center</p><h1>Good morning,<br/>Dr. Shaye.</h1><p>Enter your access key to open today’s priorities.</p><form onSubmit={unlock}><label><LockKeyhole size={15}/>Access key</label><input type="password" value={token} onChange={e=>setToken(e.target.value)} autoFocus/><button>Open command center<ArrowRight size={17}/></button></form><small>Protected session · Key stays in this browser tab</small></section></main>;
  return <main className="shell">
    <aside><div className="brand"><span><Command size={20}/></span><div><b>Eli</b><small>Command Center</small></div></div><nav><a className="selected"><Sunrise size={18}/>Today</a><a><CalendarDays size={18}/>Schedule</a><a><CheckCircle2 size={18}/>Commitments</a><a><Brain size={18}/>Decisions</a></nav><div className="systems"><p>Systems</p>{["hermes","composio","anthropic"].map(k=><div key={k}><i className={data?.integrations[k]?"online":"offline"}/><span>{k[0].toUpperCase()+k.slice(1)}</span><small>{data?.integrations[k]?"Connected":"Unavailable"}</small></div>)}</div><div className="privacy"><LockKeyhole size={15}/><p><b>Private by design</b><span>No patient data. Every external action requires exact approval.</span></p></div></aside>
    <section className="workspace"><header><div><p className="date">{new Intl.DateTimeFormat("en-US",{weekday:"long",month:"long",day:"numeric"}).format(new Date())}</p><h1>{data?.greeting||"Good morning, Dr. Shaye."}</h1><p className="focus">{data?.focus||"Loading today’s operating picture…"}</p></div><div className="header-actions"><VoiceCommand/><button className="refresh" onClick={()=>load(true)} disabled={loading}><RefreshCw size={16} className={loading?"spin":""}/></button></div></header>
      {error&&<div className="banner error-banner"><CircleAlert size={18}/><div><b>Couldn’t load the live brief</b><span>{error}</span></div></div>}
      {data?.warnings.map(w=><div className="banner" key={w}><CircleAlert size={16}/><span>{w}</span></div>)}
      <div className="summary-row"><div><Activity size={18}/><span><b>{data?.cards.filter(c=>["P0","P1","P2"].includes(c.priority)).length||0}</b> decisions need attention</span></div><div><CalendarDays size={18}/><span><b>{data?.cards.filter(c=>c.lane==="protect").length||0}</b> protected outcomes</span></div><div className={data?.live?"live":"standby"}><i/>{data?.live?"Live context":"Safe fallback"}</div></div>
      {loading&&!data?<div className="loading-grid">{[1,2,3].map(i=><div key={i}/>)}</div>:<div className="matrix">{lanes.map(l=><section className="lane" key={l.key}><div className="lane-title"><div><span>{l.eyebrow}</span><h2>{l.label}</h2></div><b>{grouped[l.key].length}</b></div><div className="lane-cards">{grouped[l.key].map(card=><ActionCard key={card.id} card={card} onChanged={()=>load(true)}/>)}{!grouped[l.key].length&&<div className="empty"><CheckCircle2 size={18}/><span>Nothing belongs here right now.</span></div>}</div></section>)}</div>}
      <footer><span>Last synthesized {data?new Date(data.generated_at).toLocaleTimeString([],{hour:"numeric",minute:"2-digit"}):"—"}</span><span>Three priorities max · Source-aware · Approval-gated</span></footer>
    </section>
  </main>;
}

