"use client";

import { useState } from "react";
import { ArrowUpRight, Check, Clock3, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { api, Card } from "@/lib/api";

const priorityTone: Record<string, string> = { P0: "critical", P1: "critical", P2: "important", P3: "strategic", P4: "routine" };

type SignalState = { phase: "idle" | "sending" | "recorded" | "queued" | "error"; detail: string };

export default function ActionCard({ card, onChanged }: { card: Card; onChanged: () => void }) {
  const [state, setState] = useState<"idle" | "working" | "done">("idle");
  const [error, setError] = useState("");
  const [signal, setSignal] = useState<SignalState>({ phase: "idle", detail: "" });

  async function sendSignal(useful: boolean) {
    if (signal.phase === "sending" || signal.phase === "recorded" || signal.phase === "queued") return;
    setSignal({ phase: "sending", detail: "" });
    try {
      const response = await api.feedback(
        useful
          ? {
              category: "positive_reinforcement",
              item_id: card.id,
              feedback: "The recommended action on this item was useful; reinforce similar recommendations.",
            }
          : {
              category: "priority_correction",
              item_id: card.id,
              disposition: "modify",
              feedback: "The recommended action on this item was not useful; reconsider this kind of recommendation.",
            },
      );
      setSignal({ phase: response.status === "recorded" ? "recorded" : "queued", detail: response.detail });
    } catch (requestError) {
      setSignal({ phase: "error", detail: requestError instanceof Error ? requestError.message : "Could not record the signal" });
    }
  }

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
      await api.feedback({
        category: "priority_correction",
        item_id: card.id,
        disposition: "not_relevant",
        feedback: "Not relevant for today's command center; reduce recurrence unless circumstances materially change.",
      });
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
      <div className="meta"><span><ShieldCheck size={13} />{card.action.kind === "eli_agent_queue" ? "Eli Agent review" : "Exact action"}</span></div>
      {error && <p className="error">{error}</p>}
      <div className="card-actions">
        <button className="primary" onClick={execute} disabled={state !== "idle"}>
          {state === "working" ? "Securing approval…" : state === "done" ? <><Check size={16} />Queued</> : <>Approve & act<ArrowUpRight size={16} /></>}
        </button>
        <button className="icon-button" onClick={dismiss} disabled={state !== "idle"} aria-label="Not relevant"><X size={17} /></button>
      </div>
      <div className="usefulness" role="group" aria-label="Was this action useful?">
        <span>Was this action useful?</span>
        <button type="button" className="signal" onClick={() => sendSignal(true)} disabled={signal.phase !== "idle" && signal.phase !== "error"} aria-label="Useful"><ThumbsUp size={13} /></button>
        <button type="button" className="signal" onClick={() => sendSignal(false)} disabled={signal.phase !== "idle" && signal.phase !== "error"} aria-label="Not useful"><ThumbsDown size={13} /></button>
        {signal.phase === "sending" && <small className="signal-status">Sending…</small>}
        {(signal.phase === "recorded" || signal.phase === "queued") && <small className="signal-status" role="status">{signal.phase === "recorded" ? "Recorded" : "Queued"}{signal.detail ? ` · ${signal.detail}` : ""}</small>}
        {signal.phase === "error" && <small className="signal-status signal-error" role="alert">{signal.detail}</small>}
      </div>
      <p className="source">Source: {card.source}</p>
    </article>
  );
}
