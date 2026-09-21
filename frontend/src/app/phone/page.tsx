"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import GoogleSignIn from "@/components/GoogleSignIn";
import { api, AuthUser, GOOGLE_CREDENTIAL_KEY, PhoneAccess } from "@/lib/api";

export default function PhonePage() {
  const [user,setUser]=useState<AuthUser|null>(null);
  const [data,setData]=useState<PhoneAccess|null>(null);
  const [pin,setPin]=useState("");
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const [webhookCopied,setWebhookCopied]=useState(false);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [recipient,setRecipient]=useState("");
  const [message,setMessage]=useState("");
  const [purpose,setPurpose]=useState("");
  const signOut=useCallback(()=>{
    sessionStorage.removeItem(GOOGLE_CREDENTIAL_KEY);setUser(null);setData(null);setPin("");setAnswers({});setWebhookCopied(false);
  },[]);
  const refresh=useCallback(async()=>{
    const credential=sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY);
    try {const result=await api.phone();if(sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY)===credential){setData(result);setError("");}}
    catch(e){if(sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY)===credential){setData(null);setError(e instanceof Error?e.message:"Unable to load phone access");}}
  },[]);
  async function signIn(credential:string){
    sessionStorage.setItem(GOOGLE_CREDENTIAL_KEY,credential);
    try{const result=await api.me();if(sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY)!==credential)return;setUser(result);await refresh();}
    catch(e){signOut();setError(e instanceof Error?e.message:"Sign-in failed");}
  }
  useEffect(()=>{
    const credential=sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY);
    if(credential)void signIn(credential);
    window.addEventListener("eli:unauthorized",signOut);
    return()=>window.removeEventListener("eli:unauthorized",signOut);
    // Restore only once; subsequent refreshes do not replace the identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[signOut]);
  useEffect(()=>{
    if(!user)return;
    const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void refresh();},10000);
    return()=>window.clearInterval(timer);
  },[user,refresh]);
  async function perform(action:()=>Promise<unknown>){
    setBusy(true);setError("");
    try{await action();await refresh();}catch(e){setError(e instanceof Error?e.message:"Request failed");}
    finally{setBusy(false);}
  }
  async function copyWebhook(){
    if(!data?.webhook_url)return;
    const credential=sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY);
    try{
      await navigator.clipboard.writeText(data.webhook_url);
      if(sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY)===credential)setWebhookCopied(true);
    }catch{
      if(sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY)===credential)setError("Select the private URL above and copy it manually.");
    }
  }
  return <main className="phone-page">
    <header><Link href="/">← Command Center</Link><h1>Speak with Eli</h1><p>Same Eli. Requests continue after you hang up.</p></header>
    {error&&<p role="alert" className="phone-error">{error}</p>}
    {!user?<section className="phone-card"><h2>Private phone access</h2><p>Sign in with your approved account to review and answer your phone requests.</p><GoogleSignIn onCredential={credential=>void signIn(credential)}/></section>:<>
      <p className="phone-account">{user.email} <button onClick={signOut}>Sign out</button></p>
      <section className="phone-card"><h2>Your phone access</h2>
        {data?<><p>Call <a href={`tel:${data.eli_number}`}>{data.eli_number}</a> from <strong>{data.phone}</strong>.</p>
          <p>{data.bridge_online?"Eli is connected.":"Eli is reconnecting. Accepted requests stay saved."}</p>
          <p>{data.conversation_mode==="live"?"Live conversation is enabled. Speak naturally and interrupt when you need to.":"Phone requests are enabled. Live conversation requires the upgraded phone connection."}</p>
          <p>{data.pin_required?"Enter your eight digit code when Eli answers.":"Call from your registered number and start talking. No access code is needed."}</p>
          {data.conversation_mode!=="live"&&data.webhook_url&&<div className="phone-webhook"><h3>Twilio connection</h3>
            <p>Copy this entire private URL into Twilio → Inbound → Custom → Webhook URL. Select POST and save. Keep the link private.</p>
            <label>Private Twilio webhook<input readOnly value={data.webhook_url} onFocus={event=>event.target.select()}/></label>
            <button onClick={()=>void copyWebhook()}>{webhookCopied?"Webhook copied":"Copy private Twilio webhook"}</button>
          </div>}
          {data.pin_required&&<button disabled={busy} onClick={()=>void perform(async()=>{const credential=sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY);const result=await api.phonePin();if(sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY)===credential)setPin(result.pin);})}>{data.pin_configured?"Create a replacement access code":"Create my access code"}</button>}
          {data.pin_required&&pin&&<div className="phone-code"><span>Your private access code</span><strong>{pin}</strong><p>Save this code privately. Creating another code replaces it.</p><button onClick={()=>setPin("")}>Hide code</button></div>}
          <p>Long requests can finish after the call. Approval-sensitive work keeps Eli&apos;s existing rules. Leave patient information out of this channel.</p>
        </>:<p>Loading phone access…</p>}
      </section>
      {!!data?.summaries?.length&&<section className="phone-card"><h2>Call summaries</h2>{data.summaries.slice(0,3).map(call=><article className="phone-item" key={call.id}><time>{new Date(call.created*1000).toLocaleString()}</time>{call.items.map(item=><div key={item.id}><p>{item.request}</p><small>{item.state.replaceAll("_"," ")} · {item.heard_at?"Shared on call":"Saved here"}</small><p>{item.question||item.result||item.error||"Still working. This summary updates as work finishes."}</p></div>)}</article>)}</section>}
      <section className="phone-card"><h2>Phone requests</h2><p>Tasks needing details stay open until you answer. Eli calls back only when you explicitly ask.</p>
        {data?.jobs.length?data.jobs.map(job=><article className="phone-item" key={job.id}><div><b>{job.state==="planning"?"Request saved":job.state==="completed"?"Response ready":job.state==="waiting_for_input"?"Needs your answer":job.state.replaceAll("_"," ")}</b><time>{new Date(job.created*1000).toLocaleString()}</time></div><p>{job.transcript}</p>{job.actions?.map(action=><p key={action.event_id} className={["sent","verified"].includes(action.status)?"phone-result":"phone-error"}>{action.content}</p>)}{job.result&&<p className="phone-result">{job.result}</p>}{job.error&&<p className="phone-error">{job.error}</p>}{job.state==="waiting_for_input"&&<form onSubmit={event=>{event.preventDefault();void perform(async()=>{await api.answerPhoneQuestion(job.id,answers[job.id]||"");setAnswers(current=>({...current,[job.id]:""}));});}}><label>Your answer<textarea required maxLength={3000} value={answers[job.id]||""} onChange={event=>setAnswers(current=>({...current,[job.id]:event.target.value}))}/></label><button disabled={busy||!(answers[job.id]||"").trim()}>Answer and resume</button></form>}{["planning","queued","claimed","running","waiting_for_input"].includes(job.state)&&<><button disabled={busy||!!job.cancel_requested} onClick={()=>void perform(()=>api.cancelPhoneTask(job.id))}>{job.cancel_requested?"Cancellation requested":job.state==="running"?"Stop remaining work":"Cancel request"}</button>{job.state==="running"&&<small>Actions already accepted by a provider may finish.</small>}</>}{!!job.callback_requested&&<small>One callback requested. Its status appears below.</small>}</article>):<p>No phone requests yet.</p>}
      </section>
      <section className="phone-card"><h2>Approve an outbound call</h2><p>Eli introduces herself as an AI assistant, speaks the exact approved message, and saves the recipient&apos;s response here. Outside recipients do not get access to your private Eli conversation.</p>
        <form onSubmit={event=>{event.preventDefault();void perform(async()=>{await api.proposeCall(recipient,message,purpose);setRecipient("");setMessage("");setPurpose("");});}}>
          <label>Recipient number<input required type="tel" pattern="\+[1-9][0-9]{7,14}" placeholder="+13105550123" value={recipient} onChange={event=>setRecipient(event.target.value)}/></label>
          <label>Purpose<input required maxLength={400} value={purpose} onChange={event=>setPurpose(event.target.value)}/></label>
          <label>Exact message<textarea required maxLength={1800} value={message} onChange={event=>setMessage(event.target.value)}/></label>
          <button disabled={busy||!data}>Prepare for review</button>
        </form>
        {data?.conversation_mode!=="live"&&<p>On the trial, outbound destinations must be verified with Twilio. Provider restrictions may prevent a call; failures appear below.</p>}
        {data?.outbound.map(call=><article className="phone-item" key={call.id}><div><b>{call.state.replaceAll("_"," ")}</b><span>{call.recipient}</span></div><p>{call.purpose}</p><p className="phone-result">Hello, I&apos;m Eli, an AI assistant. {call.message}</p>
          {call.state==="pending_approval"&&<button disabled={busy||!data.outbound_enabled||call.expires*1000<Date.now()} onClick={()=>void perform(()=>api.approveCall(call.id,call.payload_hash))}>Approve and place this call</button>}
          {["pending_approval","approved","preparing"].includes(call.state)&&<button disabled={busy} onClick={()=>void perform(()=>api.cancelCall(call.id))}>Cancel</button>}
          {call.error&&<p className="phone-error">{call.error}</p>}{call.reply&&<p><b>Recipient&apos;s response:</b> {call.reply}</p>}
        </article>)}
      </section>
    </>}
  </main>;
}
