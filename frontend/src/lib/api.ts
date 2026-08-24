export type Lane = "now" | "protect" | "delegate" | "monitor";
export type Card = { id:string; priority:string; lane:Lane; category:string; title:string; context:string; consequence:string; deadline?:string|null; source:string; mission_alignment:string; action:{label:string;kind:string;tool_name?:string|null;arguments:Record<string,unknown>;account:string;recipients:string[];reversible:boolean} };
export type CalendarItem = { id:string; title:string; start:string; end?:string|null; all_day:boolean; source:string; kind:"calendar"|"priority"; priority_id?:string|null };
export type Dashboard = { generated_at:string; live:boolean; greeting:string; focus:string; cards:Card[]; calendar_items?:CalendarItem[]; admin_count:number; integrations:Record<string,boolean|string>; warnings:string[] };
export type FeedbackCategory = "priority_correction" | "dashboard_change" | "positive_reinforcement";
export type FeedbackRequest = { category:FeedbackCategory; feedback:string; item_id?:string; disposition?:"dismiss"|"not_relevant"|"modify"|"complete" };
export type FeedbackResponse = { feedback_id:string; status:"recorded"|"queued"; eli_agent_writeback:boolean; retriable:boolean; next_brief_refresh:boolean; detail:string };

const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
function token(){ return typeof window === "undefined" ? "" : sessionStorage.getItem("eli_token") || ""; }
async function call<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch(`${base}${path}`,{...init,headers:{"Content-Type":"application/json","Authorization":`Bearer ${token()}`,...init?.headers},cache:"no-store"});
  if(!response.ok){ const body=await response.json().catch(()=>({})); throw new Error(body.detail || `Request failed (${response.status})`); }
  return response.json();
}
export const api={
  dashboard:(refresh=false)=>call<Dashboard>(`/api/dashboard?refresh=${refresh}`),
  feedback:(request:FeedbackRequest)=>call<FeedbackResponse>("/api/feedback",{method:"POST",body:JSON.stringify(request)}),
  retryFeedback:(feedback_id:string)=>call<FeedbackResponse>(`/api/feedback/${encodeURIComponent(feedback_id)}/retry`,{method:"POST"}),
  approve:(item:Card)=>call<{approval_id:string;payload_hash:string}>("/api/approvals",{method:"POST",body:JSON.stringify({item})}),
  execute:(approval_id:string,payload_hash:string)=>call<{status:string}>("/api/execute",{method:"POST",body:JSON.stringify({approval_id,payload_hash})}),
  voice:(transcript:string)=>call<{message:string}>("/api/voice",{method:"POST",body:JSON.stringify({transcript})}),
};
