export type Lane = "now" | "protect" | "delegate" | "monitor";
export type Card = { id:string; priority:string; lane:Lane; category:string; title:string; context:string; consequence:string; deadline?:string|null; calendar_event_id?:string|null; source:string; mission_alignment:string; action:{label:string;kind:string;tool_name?:string|null;arguments:Record<string,unknown>;account:string;recipients:string[];reversible:boolean} };
export type CalendarItem = { id:string; title:string; start:string; end?:string|null; all_day:boolean; source:string; kind:"calendar"|"priority"; priority_id?:string|null };
export type EliStatus = {
  checked_at?: string; health_checked_at?: string; healthy?: boolean; gateway?: string;
  memory?: {status?:string; semantic?:string; files?:number; chunks?:number; checked_at?:string};
  persona?: {stage?:number; character_review?:string; status?:string; checked_at?:string; autonomy?:{category:string;level:number;clean_streak:number}[]};
  jobs?: {total:number;enabled:number;failed:number}; platforms?:Record<string,string>; alerts?:string[];
  sources?: {path:string;modified_at:string;included:boolean;revision:string}[];
};
export type Dashboard = { generated_at:string; expires_at?:string; timezone?:string; eli?:EliStatus; live:boolean; greeting:string; focus:string; cards:Card[]; calendar_items?:CalendarItem[]; admin_count:number; integrations:Record<string,boolean|string>; warnings:string[] };
export type FeedbackCategory = "priority_correction" | "dashboard_change" | "positive_reinforcement";
export type FeedbackRequest = { category:FeedbackCategory; feedback:string; item_id?:string; disposition?:"dismiss"|"not_relevant"|"modify"|"complete" };
export type FeedbackResponse = { feedback_id:string; status:"recorded"|"queued"; eli_agent_writeback:boolean; retriable:boolean; next_brief_refresh:boolean; detail:string };
export type VoiceResponse = { command_id:string; status:"recorded"|"queued"; intent:"priority_feedback"|"dashboard_change"|"action_request"; message:string; eli_agent_writeback:boolean; retriable:boolean; next_brief_refresh:boolean };
export type AuthUser = { email:string; name:string; picture?:string|null; role:"owner"|"chief_of_staff" };
export type PhoneJob = {id:string;transcript:string;state:string;created:number;result:string;error:string;callback_requested:number;question?:string;resume_job?:string;parent_id?:string;actions?:{event_id:string;status:string;content:string}[]};
export type PhoneCall = {id:string;recipient:string;message:string;purpose:string;payload_hash:string;state:string;expires:number;error:string;reply:string};
export type PhoneSummary = {id:string;created:number;ended:number;items:{id:string;request:string;state:string;result:string;error:string;question:string;heard_at:number|null}[]};
export type PhoneAccess = {phone:string;eli_number:string;webhook_url?:string;conversation_mode?:"live"|"request";pin_configured:boolean;pin_required?:boolean;followup_mode?:string;bridge_online:boolean;outbound_enabled:boolean;jobs:PhoneJob[];outbound:PhoneCall[];summaries?:PhoneSummary[]};

export const GOOGLE_CREDENTIAL_KEY = "eli_google_credential";

export class ApiError extends Error {
  constructor(message:string, public status:number) { super(message); this.name = "ApiError"; }
}

const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
function token(){ return typeof window === "undefined" ? "" : sessionStorage.getItem(GOOGLE_CREDENTIAL_KEY) || ""; }
async function call<T>(path:string, init?:RequestInit):Promise<T>{
  const response=await fetch(`${base}${path}`,{...init,headers:{"Content-Type":"application/json","Authorization":`Bearer ${token()}`,...init?.headers},cache:"no-store"});
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    if(response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("eli:unauthorized"));
    throw new ApiError(body.detail || `Request failed (${response.status})`, response.status);
  }
  return response.json();
}
export const api={
  me:()=>call<AuthUser>("/api/auth/me"),
  dashboard:(refresh=false)=>call<Dashboard>(`/api/dashboard?refresh=${refresh}`),
  feedback:(request:FeedbackRequest)=>call<FeedbackResponse>("/api/feedback",{method:"POST",body:JSON.stringify(request)}),
  retryFeedback:(feedback_id:string)=>call<FeedbackResponse>(`/api/feedback/${encodeURIComponent(feedback_id)}/retry`,{method:"POST"}),
  approve:(item:Card)=>call<{approval_id:string;payload_hash:string}>("/api/approvals",{method:"POST",body:JSON.stringify({item})}),
  execute:(approval_id:string,payload_hash:string)=>call<{status:string}>("/api/execute",{method:"POST",body:JSON.stringify({approval_id,payload_hash})}),
  voice:(transcript:string)=>call<VoiceResponse>("/api/voice",{method:"POST",body:JSON.stringify({transcript})}),
  phone:()=>call<PhoneAccess>("/api/phone/access"),
  answerPhoneQuestion:(id:string,answer:string)=>call<{status:string;job_id:string}>(`/api/phone/jobs/${encodeURIComponent(id)}/answer`,{method:"POST",body:JSON.stringify({answer})}),
  phonePin:()=>call<{pin:string;phone:string}>("/api/phone/access/pin",{method:"POST"}),
  proposeCall:(recipient:string,message:string,purpose:string)=>call<PhoneCall>("/api/phone/outbound",{method:"POST",body:JSON.stringify({recipient,message,purpose})}),
  approveCall:(id:string,payload_hash:string)=>call<{status:string}>(`/api/phone/outbound/${encodeURIComponent(id)}/approve`,{method:"POST",body:JSON.stringify({payload_hash})}),
  cancelCall:(id:string)=>call<{status:string}>(`/api/phone/outbound/${encodeURIComponent(id)}/cancel`,{method:"POST"}),
};
