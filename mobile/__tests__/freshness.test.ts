import { canApprove, isCurrent } from '../src/freshness';
import { card, dashboard } from './fixture';
const now = Date.parse('2026-09-14T18:00:00Z');
test('expires the brief at the server deadline', () => {
  const data = dashboard(now);
  expect(isCurrent(data, now + 299_999)).toBe(true);
  expect(isCurrent(data, now + 300_000)).toBe(false);
});
test('expires yesterday’s brief at principal midnight even if its TTL remains', () => {
  const data = dashboard(Date.parse('2026-09-15T06:59:00Z'));
  expect(isCurrent(data, Date.parse('2026-09-15T07:00:00Z'))).toBe(false);
});
test.each([undefined, '', 'invalid', '2020-01-01T00:00:00Z'])('rejects absent or invalid expiry: %s', expires_at => expect(isCurrent({ ...dashboard(now), expires_at }, now)).toBe(false));
test('requires current exact action and verified sources for approval', () => {
  const data = dashboard(now);
  expect(canApprove(data, card, now)).toBe(true);
  expect(canApprove({ ...data, live: false }, card, now)).toBe(false);
  expect(canApprove(data, { ...card, action: { ...card.action, recipients: ['changed@example.test'] } }, now)).toBe(false);
  expect(canApprove(data, card, now + 300_000)).toBe(false);
});
test('rejects invalid timezone and far-future generation time', () => {
  expect(isCurrent({ ...dashboard(now), timezone: 'invalid-zone' }, now)).toBe(false);
  expect(isCurrent(dashboard(now + 120_000), now)).toBe(false);
});
