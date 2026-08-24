"use client";

import { FormEvent, useState } from "react";
import { CheckCircle2, MessageSquareText, RefreshCw, Send } from "lucide-react";
import { api, Card, FeedbackCategory, FeedbackResponse } from "@/lib/api";

const categories: { value: FeedbackCategory; label: string; description: string }[] = [
  { value: "priority_correction", label: "Priority correction", description: "Tell Eli what should move up, down, appear, or disappear." },
  { value: "dashboard_change", label: "Dashboard change", description: "Request a layout, workflow, or feature improvement." },
  { value: "positive_reinforcement", label: "Working well", description: "Reinforce a judgment Eli should repeat." },
];

export default function FeedbackPanel({ cards, onChanged }: { cards: Card[]; onChanged: () => void }) {
  const [category, setCategory] = useState<FeedbackCategory>("priority_correction");
  const [itemId, setItemId] = useState("");
  const [feedback, setFeedback] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "retrying">("idle");
  const [result, setResult] = useState<FeedbackResponse | null>(null);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState("sending");
    setError("");
    setResult(null);
    try {
      const response = await api.feedback({
        category,
        feedback: feedback.trim(),
        ...(itemId ? { item_id: itemId } : {}),
        ...(itemId && category === "priority_correction" ? { disposition: "modify" as const } : {}),
      });
      setResult(response);
      if (response.eli_agent_writeback) {
        setFeedback("");
        setItemId("");
      }
      if (response.next_brief_refresh) onChanged();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Feedback could not be submitted");
    } finally {
      setState("idle");
    }
  }

  async function retry() {
    if (!result?.feedback_id) return;
    setState("retrying");
    setError("");
    try {
      const response = await api.retryFeedback(result.feedback_id);
      setResult(response);
      if (response.eli_agent_writeback) {
        setFeedback("");
        setItemId("");
        onChanged();
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Feedback retry failed");
    } finally {
      setState("idle");
    }
  }

  return (
    <section className="feedback-panel" aria-labelledby="feedback-title">
      <div className="feedback-heading">
        <span><MessageSquareText size={19} /></span>
        <div>
          <p className="kicker">Continuous improvement</p>
          <h2 id="feedback-title">Teach Eli what matters</h2>
          <p>Correct priorities, reinforce good judgment, or request a command-center improvement.</p>
        </div>
      </div>

      <form onSubmit={submit}>
        <fieldset className="feedback-categories">
          <legend>What kind of feedback is this?</legend>
          {categories.map(option => (
            <label className={category === option.value ? "selected" : ""} key={option.value}>
              <input type="radio" name="feedback-category" value={option.value} checked={category === option.value} onChange={() => setCategory(option.value)} />
              <span><b>{option.label}</b><small>{option.description}</small></span>
            </label>
          ))}
        </fieldset>

        <div className="feedback-fields">
          <label>
            <span>Related item <small>optional</small></span>
            <select value={itemId} onChange={event => setItemId(event.target.value)}>
              <option value="">Whole command center</option>
              {cards.map(card => <option value={card.id} key={card.id}>{card.title}</option>)}
            </select>
          </label>
          <label>
            <span>Feedback for Eli</span>
            <textarea value={feedback} onChange={event => setFeedback(event.target.value)} maxLength={2000} rows={4} placeholder="What should change, and what would better reflect your priorities?" />
            <small className="feedback-count">{feedback.length}/2000</small>
          </label>
        </div>

        <div className="feedback-actions">
          <p>No patient information. Dashboard-change requests become tracked Eli improvement work.</p>
          <button type="submit" className="primary feedback-submit" disabled={feedback.trim().length < 3 || state !== "idle"}>
            <Send size={15} />{state === "sending" ? "Sending…" : "Send feedback to Eli"}
          </button>
        </div>
      </form>

      {result && <div className={`feedback-result ${result.status}`} role="status"><CheckCircle2 size={17} /><span>{result.detail}</span>{result.retriable && <button type="button" onClick={retry} disabled={state !== "idle"}><RefreshCw size={14} />{state === "retrying" ? "Retrying…" : "Retry now"}</button>}</div>}
      {error && <div className="feedback-result feedback-error" role="alert">{error}</div>}
    </section>
  );
}
