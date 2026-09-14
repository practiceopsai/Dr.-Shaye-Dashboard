import type { Dashboard } from "./api";

export function isCurrent(data: Dashboard | null, now = new Date()): boolean {
  if (!data || !data.expires_at || now.getTime() >= Date.parse(data.expires_at)) return false;
  if (!Number.isFinite(Date.parse(data.expires_at)) || !Number.isFinite(Date.parse(data.generated_at)) || Date.parse(data.generated_at) > now.getTime() + 60000) return false;
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: data.timezone || "America/Los_Angeles" });
  return date.format(new Date(data.generated_at)) === date.format(now);
}
