// Synced from frontend/src/lib/api.ts by scripts/sync-contract.cjs.
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

export type Approval = { approval_id: string; payload_hash: string; expires_in_seconds: number; exact_action: Card["action"] };
export type Execution = { status: "queued_for_eli_agent" | "executed"; eli_agent_writeback?: boolean };
