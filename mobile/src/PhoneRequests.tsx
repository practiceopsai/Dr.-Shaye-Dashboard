import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Linking, TextInput, View } from 'react-native';
import type { Api } from './api';
import type { PhoneAccess } from './types';
import { Body, Button, Heading, Kicker, Notice, Panel, Small, s } from './ui';

export function PhoneRequests({ api, close, sample = false }: { api: Api; close: () => void; sample?: boolean }) {
  const [data, setData] = useState<PhoneAccess | null>(null);
  const [error, setError] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const submitting = useRef(false);
  const refresh = useCallback(async () => {
    try { const next = await api.phone(); if (mounted.current) { setData(next); setError(''); } }
    catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Phone requests could not be loaded.'); }
  }, [api]);
  useEffect(() => {
    mounted.current = true; void refresh();
    const timer = setInterval(() => { if (AppState.currentState === 'active') void refresh(); }, 10000);
    const listener = AppState.addEventListener('change', next => { if (next === 'active') void refresh(); });
    return () => { mounted.current = false; clearInterval(timer); listener.remove(); };
  }, [refresh]);
  async function answer(id: string) {
    const text = (answers[id] || '').trim();
    if (!text || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try {
      await api.answerPhoneQuestion(id, text);
      if (mounted.current) setAnswers(current => ({ ...current, [id]: '' }));
      await refresh();
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Answer could not be confirmed. Refresh to check the task.'); }
    finally { submitting.current = false; if (mounted.current) setBusy(false); }
  }
  return <View style={s.gap}>
    <Body>Requests keep running after you hang up. Updates and missing details stay here. Eli calls back only when you explicitly ask.</Body>
    {!!error && <Notice danger>{error}</Notice>}
    {data && <Panel><Heading>Speak with Eli</Heading><Body>{data.eli_number || 'Sample phone connection'}</Body><Small>Call from {data.phone || 'your registered number'}. {data.pin_required ? 'Your existing phone code is required.' : 'No access code is needed.'}</Small>
      <Button label="Call Eli" icon="call-outline" disabled={sample || !data.eli_number} onPress={() => { void Linking.openURL(`tel:${data.eli_number}`).catch(() => setError('The phone app could not be opened.')); }} />
    </Panel>}
    <Button secondary label="Refresh phone requests" onPress={() => { void refresh(); }} />
    {data?.summaries?.slice(0, 3).map(call => <Panel key={call.id}><Heading>Call summary</Heading><Small>{new Date(call.created * 1000).toLocaleString()}</Small>
      {call.items.map(item => <View key={item.id} style={s.gap}><Body>{item.request}</Body><Small>{item.state.replaceAll('_', ' ')}{item.heard_at ? ' · Shared on call' : ' · Saved here'}</Small><Body>{item.question || item.result || item.error || 'Still working. This summary updates as work finishes.'}</Body></View>)}
    </Panel>)}
    {!data && !error && <Small>Loading phone requests...</Small>}
    {data?.jobs.length === 0 && <Small>No phone requests yet.</Small>}
    {data?.jobs.map(job => <Panel key={job.id}>
      <Kicker>{job.state === 'waiting_for_input' ? 'Needs your answer' : job.state === 'completed' ? 'Response ready' : job.state.replaceAll('_', ' ')}</Kicker>
      <Small>{new Date(job.created * 1000).toLocaleString()}</Small><Body>{job.transcript}</Body>
      {job.actions?.map(action => <Notice key={action.event_id} danger={action.status !== 'sent'}>{action.content}</Notice>)}
      {!!job.result && <Body>{job.result}</Body>}{!!job.error && <Notice danger>{job.error}</Notice>}
      {job.state === 'waiting_for_input' && <><TextInput accessibilityLabel="Your answer" multiline maxLength={3000} style={s.input} value={answers[job.id] || ''} onChangeText={text => setAnswers(current => ({ ...current, [job.id]: text }))} placeholder="Answer Eli's question" editable={!busy} /><Button label="Answer and resume" busy={busy} disabled={!(answers[job.id] || '').trim()} onPress={() => { void answer(job.id); }} /></>}
    </Panel>)}
    {data?.outbound.map(call => <Panel key={call.id}><Kicker>Follow-up call · {call.state.replaceAll('_', ' ')}</Kicker><Body>{call.purpose}</Body>{!!call.error && <Notice danger>{call.error}</Notice>}</Panel>)}
    <Button label="Done" disabled={busy} onPress={close} />
  </View>;
}
