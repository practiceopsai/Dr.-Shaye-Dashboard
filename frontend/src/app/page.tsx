"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowRight, CalendarDays, CheckCircle2, CircleAlert, Command, LockKeyhole, RefreshCw } from "lucide-react";
import ActionCard from "@/components/ActionCard";
import FeedbackPanel from "@/components/FeedbackPanel";
import SystemStatus from "@/components/SystemStatus";
import ViewNav from "@/components/ViewNav";
import VoiceCommand from "@/components/VoiceCommand";
import { api, Card, Dashboard, Lane } from "@/lib/api";
import { cardsForView, ViewKey, viewLabels } from "@/lib/views";

const lanes: { key: Lane; label: string; eyebrow: string }[] = [
  { key: "now", label: "Move now", eyebrow: "Time-sensitive" },
  { key: "protect", label: "Protect", eyebrow: "Important, not urgent" },
  { key: "delegate", label: "Unblock", eyebrow: "Delegate or decide" },
  { key: "monitor", label: "Keep watch", eyebrow: "No action yet" },
];

const viewDescriptions: Record<ViewKey, string> = {
  today: "Dr. Shaye's complete priority matrix.",
  schedule: "Time-bound work and calendar-driven commitments.",
  commitments: "Items that need action or delegation now.",
  decisions: "The highest-priority choices awaiting attention.",
};

export default function Home() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeView, setActiveView] = useState<ViewKey>("today");

  useEffect(() => {
    const savedToken = sessionStorage.getItem("eli_token") || "";
    setToken(savedToken);
    setReady(Boolean(savedToken));
    if (savedToken) load(false);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const sync = () => {
      if (document.visibilityState === "visible") load(true);
    };
    const interval = window.setInterval(sync, 5 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [ready]);

  async function load(refresh = true) {
    setLoading(true);
    setError("");
    try {
      setData(await api.dashboard(refresh));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load command center");
    } finally {
      setLoading(false);
    }
  }

  function unlock(event: React.FormEvent) {
    event.preventDefault();
    sessionStorage.setItem("eli_token", token);
    setReady(true);
    setTimeout(() => load(false), 0);
  }

  const visibleCards = useMemo(() => cardsForView(data?.cards || [], activeView), [data, activeView]);
  const grouped = useMemo(
    () => Object.fromEntries(lanes.map(lane => [lane.key, visibleCards.filter(card => card.lane === lane.key)])) as Record<Lane, Card[]>,
    [visibleCards],
  );

  if (!ready) {
    return (
      <main className="login-page">
        <div className="login-mark"><Command size={23} /></div>
        <section className="login-card">
          <p className="kicker">Private command center</p>
          <h1>Good morning,<br />Dr. Shaye.</h1>
          <p>Enter your access key to open today&apos;s priorities.</p>
          <form onSubmit={unlock}>
            <label><LockKeyhole size={15} />Access key</label>
            <input type="password" value={token} onChange={event => setToken(event.target.value)} autoFocus />
            <button>Open command center<ArrowRight size={17} /></button>
          </form>
          <small>Protected session · Key stays in this browser tab</small>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside>
        <div className="brand"><span><Command size={20} /></span><div><b>Eli</b><small>Command Center</small></div></div>
        <ViewNav current={activeView} onChange={setActiveView} className="side-nav" idPrefix="side" />
        <SystemStatus integrations={data?.integrations || {}} />
        <div className="privacy"><LockKeyhole size={15} /><p><b>Private by design</b><span>No patient data. Every external action requires exact approval.</span></p></div>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="date">{new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric" }).format(new Date())}</p>
            <h1>{data?.greeting || "Good morning, Dr. Shaye."}</h1>
            <p className="focus">{data?.focus || "Loading today's operating picture…"}</p>
          </div>
          <div className="header-actions"><VoiceCommand /><button className="refresh" onClick={() => load(true)} disabled={loading} aria-label="Refresh command center"><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div>
        </header>

        <ViewNav current={activeView} onChange={setActiveView} className="mobile-nav" idPrefix="mobile" />

        {error && <div className="banner error-banner"><CircleAlert size={18} /><div><b>Couldn&apos;t load the live brief</b><span>{error}</span></div></div>}
        {data?.warnings.map(warning => <div className="banner" key={warning}><CircleAlert size={16} /><span>{warning}</span></div>)}

        <div className="summary-row">
          <div><Activity size={18} /><span><b>{data?.cards.filter(card => ["P0", "P1", "P2"].includes(card.priority)).length || 0}</b> decisions need attention</span></div>
          <div><CalendarDays size={18} /><span><b>{data?.cards.filter(card => card.lane === "protect").length || 0}</b> protected outcomes</span></div>
          <div className={data?.live ? "live" : "standby"}><i />{data?.live ? "Live context" : "Safe fallback"}</div>
        </div>

        <FeedbackPanel cards={data?.cards || []} onChanged={() => load(true)} />

        {loading && !data ? (
          <div className="loading-grid">{[1, 2, 3].map(item => <div key={item} />)}</div>
        ) : (
          <section id={`view-${activeView}`} role="tabpanel" aria-label={viewLabels[activeView]}>
            {activeView === "today" ? (
              <div className="matrix">
                {lanes.map(lane => (
                  <section className={`lane lane-${lane.key}`} id={`lane-${lane.key}`} key={lane.key} aria-labelledby={`lane-${lane.key}-title`}>
                    <div className="lane-title"><div><span>{lane.eyebrow}</span><h2 id={`lane-${lane.key}-title`}>{lane.label}</h2></div><b>{grouped[lane.key].length}</b></div>
                    <div className="lane-cards">
                      {grouped[lane.key].map(card => <ActionCard key={card.id} card={card} onChanged={() => load(true)} />)}
                      {!grouped[lane.key].length && <div className="empty"><CheckCircle2 size={18} /><span>Nothing belongs here right now.</span></div>}
                    </div>
                  </section>
                ))}
              </div>
            ) : (
              <div className="focused-view">
                <div className="view-heading"><p className="kicker">Focused view</p><h2>{viewLabels[activeView]}</h2><p>{viewDescriptions[activeView]}</p></div>
                {visibleCards.length ? (
                  <div className="focused-grid">{visibleCards.map(card => <ActionCard key={card.id} card={card} onChanged={() => load(true)} />)}</div>
                ) : (
                  <div className="view-empty"><CheckCircle2 size={22} /><b>No items in {viewLabels[activeView].toLowerCase()}</b><span>The view will update when the priority brief changes.</span></div>
                )}
              </div>
            )}
          </section>
        )}

        <footer><span>Last synthesized {data ? new Date(data.generated_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "—"}</span><span>Three priorities max · Source-aware · Approval-gated</span></footer>
      </section>
    </main>
  );
}
