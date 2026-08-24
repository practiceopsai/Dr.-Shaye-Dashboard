"use client";

import { useEffect, useState } from "react";
import { ArrowUpRight, Check, Clock3, PencilLine, ShieldCheck, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { api, Card } from "@/lib/api";

const priorityTone: Record<string, string> = { P0: "critical", P1: "critical", P2: "important", P3: "strategic", P4: "routine" };

type SignalState = { phase: "idle" | "sending" | "recorded" | "queued" | "error"; detail: string };

export default function ActionCard({ card, onChanged }: { card: Card; onChanged: () => void }) {
  const [effectiveCard, setEffectiveCard] = useState(card);
  const [state, setState] = useState<"idle" | "working" | "done">("idle");
  const [error, setError] = useState("");
  const [signal, setSignal] = useState<SignalState>({ phase: "idle", detail: "" });
  const [alternativeOpen, setAlternativeOpen] = useState(false);
  const [alternative, setAlternative] = useState("");
  const [alternativeState, setAlternativeState] = useState<SignalState>({ phase: "idle", detail: "" });

  useEffect(() => {
    setEffectiveCard(card);
    setAlternativeOpen(false);
    setAlternative("");
    setAlternativeState({ phase: "idle", detail: "" });
  }, [card]);

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
      const approval = await api.approve(effectiveCard);
      await api.execute(approval.approval_id, approval.payload_hash);
      setState("done");
      setTimeout(onChanged, 700);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Action failed");
      setState("idle");
    }
  }

  async function useAlternative(event: React.FormEvent) {
    event.preventDefault();
    const requestedAction = alternative.trim();
    if (!requestedAction || alternativeState.phase === "sending") return;
    setAlternativeState({ phase: "sending", detail: "" });
    setError("");
    try {
      const response = await api.feedback({
        category: "priority_correction",
        item_id: card.id,
        disposition: "modify",
        feedback: `For this item, replace the suggested action "${card.action.label}" with Dr. Shaye's alternative: "${requestedAction}". Use this correction when recommending similar daily actions in future briefs.`,
      });
      setEffectiveCard(current => ({
        ...current,
        action: {
          label: requestedAction,
          kind: "eli_agent_queue",
          tool_name: null,
          arguments: {},
          account: "personal",
          recipients: [],
          reversible: true,
        },
      }));
      setAlternativeState({ phase: response.status === "recorded" ? "recorded" : "queued", detail: response.detail });
      setAlternativeOpen(false);
    } catch (requestError) {
      setAlternativeState({ phase: "error", detail: requestError instanceof Error ? requestError.message : "Could not save the alternative action" });
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
    <article className={`action-card tone-${priorityTone[effectiveCard.priority] || "routine"}`}>
      <div className="card-top">
        <div className="badges"><span className="priority">{effectiveCard.priority}</span><span>{effectiveCard.category}</span></div>
        {effectiveCard.deadline && <span className="deadline"><Clock3 size={13} />{effectiveCard.deadline}</span>}
      </div>
      <h3>{effectiveCard.title}</h3>
      <p className="context">{effectiveCard.context}</p>
      <div className="why"><span>Why it matters</span><p>{effectiveCard.consequence}</p></div>
      <div className="suggestion"><Sparkles size={16} /><div><span>{alternativeState.phase === "recorded" || alternativeState.phase === "queued" ? "Your selected action" : "Recommended action"}</span><p>{effectiveCard.action.label}</p></div></div>
      <button type="button" className="alternative-toggle" onClick={() => setAlternativeOpen(value => !value)} aria-expanded={alternativeOpen}><PencilLine size={14} />Choose a different action</button>
      {alternativeOpen && (
        <form className="alternative-form" onSubmit={useAlternative}>
          <label htmlFor={`alternative-${card.id}`}>What should Eli do instead?</label>
          <textarea id={`alternative-${card.id}`} value={alternative} onChange={event => setAlternative(event.target.value)} maxLength={600} rows={3} placeholder="Describe the action you want taken instead" />
          <div><small>{alternative.length}/600</small><button type="submit" disabled={!alternative.trim() || alternativeState.phase === "sending"}>{alternativeState.phase === "sending" ? "Saving…" : "Use this action"}</button></div>
        </form>
      )}
      {(alternativeState.phase === "recorded" || alternativeState.phase === "queued") && <p className={`alternative-result ${alternativeState.phase}`} role="status"><Check size={13} />Alternative selected and {alternativeState.phase === "recorded" ? "learned" : "queued for learning"}. Approve below to act.</p>}
      {alternativeState.phase === "error" && <p className="alternative-result error" role="alert">{alternativeState.detail}</p>}
      <div className="meta"><span><ShieldCheck size={13} />{effectiveCard.action.kind === "eli_agent_queue" ? "Eli Agent review" : "Exact action"}</span></div>
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
      <p className="source">Source: {effectiveCard.source}</p>
    </article>
  );
}
