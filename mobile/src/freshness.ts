import type { Dashboard, Card } from './types';

export function localDay(value: number | string, zone = 'America/Los_Angeles') {
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value));
  } catch { return ''; }
}

export function isCurrent(data: Dashboard | null, now = Date.now()): data is Dashboard {
  if (!data?.expires_at) return false;
  const generated = Date.parse(data.generated_at);
  const expiry = Date.parse(data.expires_at);
  return Number.isFinite(generated) && generated <= now + 60_000 && expiry > now
    && expiry > generated && Boolean(localDay(now, data.timezone))
    && localDay(generated, data.timezone) === localDay(now, data.timezone);
}

export function canApprove(data: Dashboard | null, card: Card, now = Date.now()) {
  return isCurrent(data, now) && data.live && card.priority !== 'P5'
    && data.cards.some(current => current.id === card.id && JSON.stringify(current) === JSON.stringify(card));
}

export function displayTime(value?: string | null, zone?: string, date = false) {
  if (!value) return 'Not verified';
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: zone, ...(date ? { month: 'short', day: 'numeric' } : {}), hour: 'numeric', minute: '2-digit',
    }).format(new Date(value));
  } catch { return 'Not verified'; }
}

export const humanize = (value: string) => value.replace(/[_-]/g, ' ');
