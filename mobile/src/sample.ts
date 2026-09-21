import type { Api } from './api';
import type { Approval, AuthUser, Card, Dashboard } from './types';

export const sampleUser: AuthUser = { name: 'Sample Principal', email: 'sample@example.test', role: 'owner' };
export const sampleNotice = 'Sample mode. All data is fictional. Requests and approvals stay in this preview.';

// This client has no transport, credentials, or reference to the production API.
// Each preview gets its own disposable state; signing in uses the real API client.
export function createSampleApi(): Api {
  let sequence = 0;
  const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
  const makeCard = (id: string, title: string, priority: string, lane: Card['lane'], context: string): Card => ({
    id, title, priority, lane, context, category: 'planning', source: 'Fictional example',
    consequence: 'Review the proposed next step and decide whether it should proceed.',
    mission_alignment: 'Protect time and follow through on commitments.',
    action: { label: 'Review sample next step', kind: 'eli_queue', arguments: { request: title },
      account: sampleUser.email, recipients: ['colleague@example.test'], reversible: true },
  });
  let cards = [
    makeCard('sample-planning', 'Confirm the planning agenda', 'P2', 'now', 'An example decision to prepare a team meeting.'),
    makeCard('sample-focus', 'Protect an hour for focused work', 'P3', 'protect', 'Keep an uninterrupted block for strategic planning.'),
    makeCard('sample-followup', 'Review the weekly project update', 'P3', 'delegate', 'A sample commitment delegated to a colleague.'),
    makeCard('sample-admin', 'Organize the reference folder', 'P4', 'monitor', 'An example of routine administration kept off Today.'),
  ];
  const approvals = new Map<string, { approval: Approval; cardId: string; expires: number }>();
  function dashboard(): Dashboard {
    const now = Date.now();
    const date = (offset = 0) => new Date(now + offset).toISOString();
    return copy({
      generated_at: date(), expires_at: date(300_000), timezone: 'America/Los_Angeles', live: true,
      greeting: 'Explore a sample day.', focus: 'Prepare the planning agenda and protect time to think.',
      cards, admin_count: cards.filter(card => card.priority === 'P4').length,
      calendar_items: [
        { id: 'sample-meeting', title: 'Sample team planning meeting', start: date(3_600_000), end: date(5_400_000), all_day: false, source: 'Fictional calendar', kind: 'calendar' },
        { id: 'sample-focus-time', title: 'Sample focus time', start: date(7_200_000), end: date(10_800_000), all_day: false, source: 'Fictional calendar', kind: 'calendar' },
      ],
      integrations: { calendar: 'Sample', email: 'Sample', eli: 'Sample' }, warnings: [],
      eli: { checked_at: date(), healthy: true, gateway: 'Sample connection',
        memory: { status: 'Sample index', semantic: 'Sample search', files: 12, chunks: 48, checked_at: date() },
        persona: { stage: 1, character_review: 'Fictional example', status: 'Sample maintenance', checked_at: date(),
          autonomy: [{ category: 'calendar_planning', level: 0, clean_streak: 0 }, { category: 'internal_organization', level: 1, clean_streak: 3 }] },
        jobs: { total: 3, enabled: 3, failed: 0 }, platforms: { calendar: 'Sample', requests: 'Preview only' },
        sources: [{ path: 'Sample memory/preferences.md', modified_at: date(), included: true, revision: 'sample' }],
      },
    } satisfies Dashboard);
  }
  return {
    phone: async () => ({ phone: '', eli_number: '', pin_configured: false, pin_required: false, bridge_online: false, outbound_enabled: false, jobs: [], outbound: [] }),
    answerPhoneQuestion: async () => { throw new Error('No live phone requests are available in sample mode.'); },
    me: async () => copy(sampleUser),
    dashboard: async () => dashboard(),
    voice: async transcript => {
      const id = `sample-request-${++sequence}`;
      cards.push(makeCard(id, transcript.slice(0, 140), 'P3', 'monitor', 'A request captured only in this preview.'));
      return { command_id: id, status: 'recorded', intent: 'action_request', message: 'Sample request captured. Nothing was sent to Eli.', eli_agent_writeback: false, retriable: false, next_brief_refresh: true };
    },
    feedback: async request => {
      if (request.item_id && ['complete', 'dismiss', 'not_relevant'].includes(request.disposition || '')) cards = cards.filter(card => card.id !== request.item_id);
      return { feedback_id: `sample-feedback-${++sequence}`, status: 'recorded', detail: 'Sample feedback captured. Eli and the live command center are unchanged.', eli_agent_writeback: false, retriable: false, next_brief_refresh: true };
    },
    retryFeedback: async () => { throw new Error('Sample feedback is recorded immediately and does not need a retry.'); },
    approve: async card => {
      const current = cards.find(value => value.id === card.id);
      if (!current || JSON.stringify(current.action) !== JSON.stringify(card.action)) throw new Error('This sample item changed. Refresh the preview.');
      const approval: Approval = { approval_id: `sample-approval-${++sequence}`, payload_hash: `sample-${sequence}`, expires_in_seconds: 900, exact_action: copy(current.action) };
      approvals.set(approval.approval_id, { approval, cardId: card.id, expires: Date.now() + 900_000 });
      return copy(approval);
    },
    execute: async supplied => {
      const entry = approvals.get(supplied.approval_id);
      if (!entry || entry.approval.payload_hash !== supplied.payload_hash || entry.expires <= Date.now() || !cards.some(card => card.id === entry.cardId)) throw new Error('This sample approval is no longer available.');
      approvals.delete(supplied.approval_id);
      cards = cards.filter(card => card.id !== entry.cardId);
      return { status: 'executed', eli_agent_writeback: false };
    },
  };
}
