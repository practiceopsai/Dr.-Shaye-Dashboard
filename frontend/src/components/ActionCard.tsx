"use client";

import { useState } from "react";
import { ArrowUpRight, Check, Clock3, ShieldCheck, Sparkles, X } from "lucide-react";
import { api, Card } from "@/lib/api";

const priorityTone: Record<string, string> = { P0: "critical", P1: "critical", P2: "important", P3: "strategic", P4: "routine" };

export default function ActionCard({ card, onChanged }: { card: Card; onChanged: () => void }) {
  const [state, setState] = useState<"idle" | "working" | "done">("idle");
  const [error, setError] = useState("");

  async function execute() {
    setState("working");
    setError("");
    try {
      const approval = await api.approve(card);
      await api.execute(approval.approval_id, approval.payload_hash);
      setState("done");
      setTimeout(onChanged, 700);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Action failed");
      setState("idle");
    }
  }

  async function dismiss() {
    setState("working");
    try {
      await api.feedback(card.id, "not_relevant", "Not relevant for today's command center; reduce recurrence unless circumstances materially change.");
      onChanged();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not record feedback");
      setState("idle");
    }
  }

  return (
    <article className={`action-card tone-${priorityTone[card.priority] || "routine"}`}>
      <div className="card-top">
        <div className="badges"><span className="priority">{card.priority}</span><span>{card.category}</span></div>
        {card.deadline && <span className="deadline"><Clock3 size={13} />{card.deadline}</span>}
      </div>
      <h3>{card.title}</h3>
      <p className="context">{card.context}</p>
      <div className="why"><span>Why it matters</span><p>{card.consequence}</p></div>
      <div className="suggestion"><Sparkles size={16} /><div><span>Recommended action</span><p>{card.action.label}</p></div></div>
      <div className="meta"><span><ShieldCheck size={13} />{card.action.kind === "eli_agent_queue" ? "Eli Agent review" : "Exact action"}</span><span>{card.mission_alignment}</span></div>
      {error && <p className="error">{error}</p>}
      <div className="card-actions">
        <button className="primary" onClick={execute} disabled={state !== "idle"}>
          {state === "working" ? "Securing approval…" : state === "done" ? <><Check size={16} />Queued</> : <>Approve & act<ArrowUpRight size={16} /></>}
        </button>
        <button className="icon-button" onClick={dismiss} disabled={state !== "idle"} aria-label="Not relevant"><X size={17} /></button>
      </div>
      <p className="source">Source: {card.source}</p>
    </article>
  );
}
