import React, { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import type { Api } from './api';
import type { Approval, Card, Dashboard } from './types';
import { canApprove } from './freshness';
import { Body, Button, Heading, Kicker, Notice, Panel, s, Small } from './ui';

export function ApprovalSheet({ card, data, api, online, onSent, close }: {
  card: Card; data: Dashboard | null; api: Api; online: boolean; onSent: () => Promise<void>; close: () => void;
}) {
  const [approval, setApproval] = useState<Approval | null>(null);
  const [deadline, setDeadline] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const guard = useRef(false);
  const latest = useRef(data); latest.current = data;
  useEffect(() => {
    let alive = true;
    if (canApprove(latest.current, card)) {
      void api.approve(card).then(value => {
        if (alive) { setApproval(value); setDeadline(Date.now() + value.expires_in_seconds * 1000); }
      }).catch(problem => { if (alive) setError(problem instanceof Error ? problem.message : 'Could not prepare approval.'); });
    } else setError('This priority is no longer current. Refresh the brief before approving.');
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { alive = false; clearInterval(timer); };
  }, [api, card]);
  const valid = online && canApprove(data, card, now) && deadline > now && !attempted;
  async function execute() {
    if (guard.current || !approval || !online || deadline <= Date.now() || !canApprove(latest.current, card)) return;
    guard.current = true; setBusy(true); setAttempted(true); setError('');
    try {
      const outcome = await api.execute(approval);
      setResult(outcome.status === 'queued_for_eli_agent'
        ? 'Your approval was queued for Eli. The external action has not been confirmed as completed.'
        : `Action completed.${outcome.eli_agent_writeback === false ? ' Eli’s activity record still needs to be updated.' : ''}`);
      void onSent();
    } catch (problem) { setError(problem instanceof Error ? problem.message : 'The action outcome could not be confirmed.'); }
    finally { setBusy(false); }
  }
  const action = approval?.exact_action || card.action;
  return <View style={s.gap}>
    <Heading>{card.title}</Heading><Body>{card.context}</Body>
    <Panel><Kicker>Exact action for approval</Kicker><Heading>{action.label}</Heading><Body>Account: {action.account}</Body><Body>Recipients: {action.recipients.length ? action.recipients.join(', ') : 'None specified'}</Body><Body>Reversible: {action.reversible ? 'Yes' : 'No'}</Body>{Object.keys(action.arguments).length > 0 && <Text selectable style={s.body}>{JSON.stringify(action.arguments, null, 2)}</Text>}<Small>{action.tool_name || 'Eli action queue'}</Small></Panel>
    {!!error && <Notice danger>{error}</Notice>}
    {!!result && <Notice>{result}</Notice>}
    {!result && !attempted && <><Small>Approval applies only to the action shown above. Direct execution depends on the server’s current permissions.</Small>{!valid && approval && <Notice danger>This approval is unavailable because the brief expired, the item changed, or the phone is offline. Close this screen and refresh.</Notice>}<Button label="Approve exact action" icon="checkmark-outline" disabled={!approval || !valid} busy={busy} onPress={() => { void execute(); }} /></>}
    {attempted && !result && !busy && <Small>This approval will not be retried automatically. Check the outcome before creating another approval.</Small>}
    <Button secondary label={result ? 'Done' : 'Close'} disabled={busy} onPress={close} />
  </View>;
}
