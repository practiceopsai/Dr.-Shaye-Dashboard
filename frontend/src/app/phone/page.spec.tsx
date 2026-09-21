import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PhonePage from "./page";
import { api, GOOGLE_CREDENTIAL_KEY } from "@/lib/api";

vi.mock("@/components/GoogleSignIn",()=>({default:({onCredential}:{onCredential:(value:string)=>void})=><button onClick={()=>onCredential("new-credential")}>Test sign in</button>}));
vi.mock("@/lib/api",()=>({GOOGLE_CREDENTIAL_KEY:"test-credential",api:{me:vi.fn(),phone:vi.fn(),phonePin:vi.fn(),answerPhoneQuestion:vi.fn(),cancelPhoneTask:vi.fn(),proposeCall:vi.fn(),approveCall:vi.fn(),cancelCall:vi.fn()}}));
const owner={email:"owner@example.com",name:"Owner",role:"owner" as const};
const access={phone:"+12025550101",eli_number:"+12025550100",pin_configured:false,bridge_online:true,outbound_enabled:true,jobs:[],outbound:[]};
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();sessionStorage.setItem(GOOGLE_CREDENTIAL_KEY,"initial");vi.mocked(api.me).mockResolvedValue(owner);vi.mocked(api.phone).mockResolvedValue(access);});

describe("private phone setup",()=>{
  it("cancels the selected task and preserves uncertainty about in-flight effects",async()=>{
    vi.mocked(api.phone).mockResolvedValue({...access,jobs:[{id:"running-one",transcript:"Send the approved email",state:"running",created:1,result:"",error:"",callback_requested:0}]});
    vi.mocked(api.cancelPhoneTask).mockResolvedValue({state:"cancel_requested",effect_cancelled:false});
    render(<PhonePage/>);
    fireEvent.click(await screen.findByText("Stop remaining work"));
    await waitFor(()=>expect(api.cancelPhoneTask).toHaveBeenCalledWith("running-one"));
    expect(screen.getByText("Actions already accepted by a provider may finish.")).toBeInTheDocument();
  });
  it("separates a completed response from a blocked message",async()=>{
    vi.mocked(api.phone).mockResolvedValue({...access,jobs:[{id:"job-one",transcript:"Text Fabio hello",state:"completed",created:1,result:"iMessage needs reconnection.",error:"",callback_requested:0,actions:[{event_id:"receipt-one",status:"failed",content:"The iMessage send is not confirmed."}]}]});
    render(<PhonePage/>);
    expect(await screen.findByText("Response ready")).toBeInTheDocument();
    expect(screen.getByText("The iMessage send is not confirmed.")).toBeInTheDocument();
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
  });
  it("copies the signed-in user's full private webhook and removes it on sign-out",async()=>{
    const webhook="https://phone.example/api/phone/incoming?scope=entry&token=private-test-token";
    const writeText=vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText}});
    vi.mocked(api.phone).mockResolvedValue({...access,webhook_url:webhook});
    render(<PhonePage/>);
    fireEvent.click(await screen.findByText("Copy private Twilio webhook"));
    await waitFor(()=>expect(writeText).toHaveBeenCalledWith(webhook));
    expect(await screen.findByText("Webhook copied")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Sign out"));
    expect(screen.queryByDisplayValue(webhook)).not.toBeInTheDocument();
  });
  it("shows a newly created code only in the current signed-in session",async()=>{
    vi.mocked(api.phone).mockResolvedValue({...access,pin_required:true});
    vi.mocked(api.phonePin).mockResolvedValue({pin:"12345678",phone:access.phone});
    render(<PhonePage/>);
    fireEvent.click(await screen.findByText("Create my access code"));
    expect(await screen.findByText("12345678")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Sign out"));
    expect(screen.queryByText("12345678")).not.toBeInTheDocument();
  });
  it("starts without codes and resumes an exact waiting task",async()=>{
    vi.mocked(api.phone).mockResolvedValue({...access,pin_required:false,jobs:[{id:"waiting-one",transcript:"Email Fabio",state:"waiting_for_input",created:1,result:"What should I say?",question:"What should I say?",error:"",callback_requested:0}]});
    vi.mocked(api.answerPhoneQuestion).mockResolvedValue({status:"resumed",job_id:"continuation"});
    render(<PhonePage/>);
    expect(await screen.findByText("Needs your answer")).toBeInTheDocument();
    expect(screen.queryByText("Create my access code")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Your answer"),{target:{value:"Say hello."}});
    fireEvent.click(screen.getByText("Answer and resume"));
    await waitFor(()=>expect(api.answerPhoneQuestion).toHaveBeenCalledWith("waiting-one","Say hello."));
  });
  it("requires an explicit click on the reviewed exact call",async()=>{
    vi.mocked(api.phone).mockResolvedValue({...access,outbound:[{id:"call-one",recipient:"+12025550199",message:"Please confirm your hours.",purpose:"Hours",payload_hash:"exact-payload",state:"pending_approval",expires:Date.now()/1000+300,error:"",reply:""}]});
    vi.mocked(api.approveCall).mockResolvedValue({status:"approved"});
    render(<PhonePage/>);
    const button=await screen.findByText("Approve and place this call");
    expect(api.approveCall).not.toHaveBeenCalled();
    expect(screen.getByText(/Please confirm your hours/)).toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(()=>expect(api.approveCall).toHaveBeenCalledWith("call-one","exact-payload"));
  });
  it("discards an older account response after another account signs in",async()=>{
    let finish!:(value:typeof access)=>void;
    vi.mocked(api.phone).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({...access,phone:"+12025550102"});
    vi.mocked(api.me).mockResolvedValueOnce(owner).mockResolvedValue({email:"operator@example.com",name:"Operator",role:"chief_of_staff"});
    render(<PhonePage/>);
    fireEvent.click(await screen.findByText("Sign out"));
    fireEvent.click(screen.getByText("Test sign in"));
    expect(await screen.findByText("+12025550102")).toBeInTheDocument();
    await act(async()=>finish(access));
    expect(screen.queryByText("+12025550101")).not.toBeInTheDocument();
  });
});
