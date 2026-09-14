import type { EliStatus } from "@/lib/api";

const label = (text: string) => text.replaceAll("_", " ").replaceAll("-", " ");
const time = (value?: string) => value ? new Date(value).toLocaleString() : "Not verified";

export default function EliStatusPanel({ status }: { status?: EliStatus }) {
  if (!status?.checked_at) return null;
  return <details className="eli-detail">
    <summary>Eli status <span>{status.healthy ? "Healthy" : "Needs review"} · Checked {time(status.checked_at)}</span></summary>
    <div className="eli-detail-grid">
      <section><h3>Behavior and familiarity</h3>
        <p>Stage {status.persona?.stage ?? "unknown"} · Character {status.persona?.character_review || "unverified"}</p>
        <p>Maintenance: {status.persona?.status || "unknown"}</p><small>Checked {time(status.persona?.checked_at)}</small>
        <p>Familiarity is earned through verified feedback. It does not grant new permissions.</p>
      </section>
      <section><h3>Shared memory</h3>
        <p>{status.memory?.files ?? "—"} indexed files · {status.memory?.chunks ?? "—"} searchable passages</p>
        <p>Retrieval: {status.memory?.status || "unknown"} · Semantic search: {status.memory?.semantic || "unknown"}</p>
        <small>Checked {time(status.memory?.checked_at)}</small>
      </section>
      <section><h3>Connections and automation</h3>
        {Object.entries(status.platforms || {}).map(([name, value]) => <p key={name}>{label(name)}: {value}</p>)}
        <p>{status.jobs?.enabled ?? "—"} enabled jobs · {status.jobs?.failed ?? "—"} need review</p>
      </section>
      <section><h3>Current authority levels</h3>
        <ul>{status.persona?.autonomy?.map(row => <li key={row.category}>{label(row.category)} <b>Level {row.level}</b></li>)}</ul>
      </section>
    </div>
    <p className="ranking-note">Priority ranking: P0 crisis · P1 critical today · P2 important deadline or decision · P3 protected strategic work · P4 routine administration. P5 stays off the daily view.</p>
    {!!status.alerts?.length && <div><h3>Items awaiting review</h3><ul>{status.alerts.map(alert => <li key={alert}>{label(alert)}</li>)}</ul><small>Health checked {time(status.health_checked_at)}. These alerts do not mean an action was completed.</small></div>}
    <details><summary>Source freshness</summary><ul>{status.sources?.map((source, index) => <li key={`${source.path}-${index}`}>{source.path} · {time(source.modified_at)}{!source.included && " · Excluded: old activity record"}</li>)}</ul></details>
  </details>;
}
