import React, { useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import type { Card, Dashboard } from './types';
import { Body, Button, colors, Empty, Heading, Icon, Kicker, Notice, Panel, s, Small } from './ui';
import { displayTime, humanize, localDay } from './freshness';
import { config } from './config';

export type CardActions = { review: (card: Card) => void; feedback: (card: Card) => void };
export function Priority({ card, data, actions }: { card: Card; data: Dashboard; actions: CardActions }) {
  const urgent = ['P0', 'P1'].includes(card.priority);
  return <Panel>
    <View style={s.between}><View style={[s.row, { flex: 1 }]}><Text style={{ backgroundColor: urgent ? '#fbece8' : colors.pale, color: urgent ? colors.red : colors.green, fontWeight: '700', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8 }}>{card.priority}</Text><Small style={{ flexShrink: 1 }}>{humanize(card.lane)} · {humanize(card.category)}</Small></View><Icon name="ellipse" size={7} color={urgent ? colors.red : colors.gold} /></View>
    <Heading>{card.title}</Heading>
    <Body style={{ color: colors.muted }}>{card.context}</Body>
    {!!card.consequence && <View style={{ borderLeftWidth: 2, borderLeftColor: colors.gold, paddingLeft: 12 }}><Small style={{ color: colors.ink }}>{card.consequence}</Small></View>}
    {!!card.deadline && <View style={s.row}><Icon name="time-outline" size={16} /><Small>Due {displayTime(card.deadline, data.timezone, true)}</Small></View>}
    <Small>Source: {card.source}</Small>
    <Button label={card.action.label || 'Review action'} icon="arrow-forward-outline" onPress={() => actions.review(card)} disabled={!data.live} />
    <Button label="Correct or update this priority" secondary icon="create-outline" onPress={() => actions.feedback(card)} />
  </Panel>;
}

export function Today({ data, actions, openSchedule }: { data: Dashboard; actions: CardActions; openSchedule: () => void }) {
  const cards = data.cards.filter(card => card.priority !== 'P5' && card.priority !== 'P4');
  const upcoming = data.calendar_items?.filter(event => event.all_day || Date.parse(event.end || event.start) >= Date.now()).slice(0, 2) || [];
  return <View style={s.gap}>
    <Panel style={{ backgroundColor: colors.green, borderColor: colors.green, padding: 24 }}>
      <Kicker><Text style={{ color: '#dec18c' }}>Your focus</Text></Kicker>
      <Text style={{ fontSize: 24, lineHeight: 33, fontWeight: '500', color: colors.white }}>{data.focus}</Text>
      <View style={{ height: 1, backgroundColor: '#ffffff30', marginVertical: 3 }} />
      <Small style={{ color: '#d5e2d6' }}>{cards.length} priorities · {data.admin_count} administrative items</Small>
    </Panel>
    <View style={s.between}><Heading>What needs you</Heading><Small>{data.live ? 'Verified brief' : 'Partial brief'}</Small></View>
    {cards.length ? cards.map(card => <Priority key={card.id} card={card} data={data} actions={actions} />) : <Empty title="Room to focus" message="There are no high-priority items in this brief." />}
    {!!upcoming.length && <Panel><View style={s.between}><Heading>On your schedule</Heading><Icon name="calendar-outline" /></View>{upcoming.map(item => <View key={item.id} style={s.gap}><Small>{item.all_day ? 'All day' : displayTime(item.start, data.timezone, true)}</Small><Body>{item.title}</Body></View>)}<Button secondary label="See schedule" onPress={openSchedule} /></Panel>}
    <Small>Priority order follows Eli’s current ranking. Routine work is available under Commitments.</Small>
  </View>;
}

export function Schedule({ data }: { data: Dashboard }) {
  const [selected, setSelected] = useState('all');
  const events = [...(data.calendar_items || [])].sort((a, b) => a.start.localeCompare(b.start));
  const days = Array.from(new Set(events.map(item => /^\d{4}-\d{2}-\d{2}$/.test(item.start) ? item.start : localDay(item.start, data.timezone))));
  const filtered = events.filter(item => selected === 'all' || (/^\d{4}-\d{2}-\d{2}$/.test(item.start) ? item.start : localDay(item.start, data.timezone)) === selected);
  return <View style={s.gap}>
    <Notice>Times shown in {data.timezone || 'America/Los_Angeles'}.</Notice>
    <View style={[s.row, { flexWrap: 'wrap' }]}>{['all', ...days].map(day => <Pressable accessibilityRole="button" accessibilityState={{ selected: selected === day }} key={day} onPress={() => setSelected(day)} style={{ minHeight: 44, justifyContent: 'center', paddingHorizontal: 14, paddingVertical: 9, backgroundColor: selected === day ? colors.green : colors.pale, borderRadius: 12 }}><Text style={{ color: selected === day ? colors.white : colors.green, fontWeight: '600' }}>{day === 'all' ? 'All dates' : day}</Text></Pressable>)}</View>
    {filtered.length ? filtered.map(event => <Panel key={event.id}>
      <View style={s.row}><Icon name={event.kind === 'priority' ? 'flag-outline' : 'calendar-outline'} /><Kicker>{event.kind === 'priority' ? 'Priority deadline' : 'Calendar event'}</Kicker></View>
      <Heading>{event.title}</Heading>
      <Body>{event.all_day ? `${event.start.slice(0, 10)} · All day` : displayTime(event.start, data.timezone, true)}{!event.all_day && event.end ? ` – ${displayTime(event.end, data.timezone)}` : ''}</Body>
      <Small>{event.source}</Small>
    </Panel>) : <Empty title="No scheduled items" message="No calendar entries or dated priorities are available for this selection." icon="calendar-outline" />}
  </View>;
}

export function Commitments({ data, actions, decisions = false }: { data: Dashboard; actions: CardActions; decisions?: boolean }) {
  const [lane, setLane] = useState('all');
  const cards = data.cards.filter(card => card.priority !== 'P5' && (!decisions || card.lane === 'now') && (lane === 'all' || card.lane === lane));
  return <View style={s.gap}>
    <Body style={{ color: colors.muted }}>{decisions ? 'Current priorities in Eli’s Now lane. Review each proposed action before approving.' : 'Current commitments surfaced by Eli, including routine administration.'}</Body>
    {!decisions && <View style={[s.row, { flexWrap: 'wrap' }]}>{['all', 'now', 'protect', 'delegate', 'monitor'].map(value => <Pressable accessibilityRole="button" accessibilityState={{ selected: lane === value }} key={value} onPress={() => setLane(value)} style={{ padding: 12, minHeight: 44, borderRadius: 12, backgroundColor: lane === value ? colors.green : colors.pale }}><Text style={{ color: lane === value ? colors.white : colors.green, textTransform: 'capitalize' }}>{value}</Text></Pressable>)}</View>}
    {cards.length ? cards.map(card => <Priority key={card.id} card={card} data={data} actions={actions} />) : <Empty title={decisions ? 'No decisions surfaced' : 'Nothing in this lane'} message="Eli has no current items for this view." icon="checkmark-circle-outline" />}
  </View>;
}

export function EliStatus({ data }: { data: Dashboard }) {
  const eli = data.eli;
  const [sources, setSources] = useState(false);
  return <View style={s.gap}>
    <Panel><View style={s.row}><Icon name={eli?.healthy ? 'checkmark-circle-outline' : 'alert-circle-outline'} /><Heading>{eli?.healthy ? 'Eli is healthy' : 'Eli needs review'}</Heading></View><Small>Checked {displayTime(eli?.checked_at, data.timezone, true)}</Small><Body>Gateway: {eli?.gateway || 'Not verified'}</Body></Panel>
    <Panel><Kicker>Behavior and familiarity</Kicker><Heading>Stage {eli?.persona?.stage ?? 'not verified'}</Heading><Body>Character: {eli?.persona?.character_review || 'Not verified'}</Body><Body>Maintenance: {eli?.persona?.status || 'Not verified'}</Body><Small>Checked {displayTime(eli?.persona?.checked_at, data.timezone, true)}</Small><Small>Familiarity is earned through verified feedback. It does not grant new permissions.</Small></Panel>
    <Panel><Kicker>Shared memory</Kicker><Heading>{eli?.memory?.files?.toLocaleString() ?? '—'} indexed files</Heading><Body>{eli?.memory?.chunks?.toLocaleString() ?? '—'} searchable passages</Body><Body>Retrieval: {eli?.memory?.status || 'Not verified'}</Body><Body>Semantic search: {eli?.memory?.semantic || 'Not verified'}</Body><Small>Checked {displayTime(eli?.memory?.checked_at, data.timezone, true)}</Small></Panel>
    <Panel><Kicker>Current authority levels</Kicker>{eli?.persona?.autonomy?.length ? eli.persona.autonomy.map(row => <View key={row.category} style={s.between}><Body style={{ flex: 1 }}>{humanize(row.category)}</Body><Text style={{ color: colors.green, fontWeight: '700' }}>Level {row.level}</Text></View>) : <Body>No verified authority ledger is available.</Body>}</Panel>
    <Panel><Kicker>Priority ranking</Kicker>{['P0 · Crisis', 'P1 · Critical today', 'P2 · Important deadline or decision', 'P3 · Protected strategic work', 'P4 · Routine administration', 'P5 · Kept off the daily view'].map(label => <Body key={label}>{label}</Body>)}</Panel>
    <Panel><Kicker>API connections</Kicker>{Object.entries(data.integrations).map(([name, value]) => <View key={name} style={s.between}><Body style={{ flex: 1 }}>{humanize(name)}</Body><Small style={{ color: value === true ? colors.green : colors.red }}>{value === true ? 'Verified' : value === false ? 'Unavailable' : value}</Small></View>)}</Panel>
    <Panel><Kicker>Channels and automation</Kicker>{Object.entries(eli?.platforms || {}).map(([name, value]) => <View key={name} style={s.between}><Body style={{ flex: 1 }}>{humanize(name)}</Body><Small>{value}</Small></View>)}<Body>{eli?.jobs?.enabled ?? '—'} enabled jobs · {eli?.jobs?.failed ?? '—'} need review</Body></Panel>
    {!!eli?.alerts?.length && <Panel><Kicker>Items awaiting review</Kicker>{eli.alerts.map((alert, i) => <Body key={`${alert}-${i}`}>• {humanize(alert)}</Body>)}<Small>Health checked {displayTime(eli.health_checked_at, data.timezone, true)}</Small></Panel>}
    <Button label={sources ? 'Hide source dates' : 'Show source dates'} secondary onPress={() => setSources(value => !value)} icon="document-text-outline" />
    {sources && <Panel>{eli?.sources?.map((source, i) => <View key={`${source.path}-${i}`} style={{ gap: 4 }}><Body selectable>{source.path}</Body><Small>{displayTime(source.modified_at, data.timezone, true)} · {source.included ? 'Included' : 'Excluded: old activity record'}</Small></View>)}</Panel>}
  </View>;
}

export function LegalLinks() {
  const open = (url: string) => { void Linking.openURL(url).catch(() => undefined); };
  return <View style={[s.row, { justifyContent: 'center' }]}><Button secondary label="Privacy" onPress={() => open(config.privacyUrl)} /><Button secondary label="Support" onPress={() => open(config.supportUrl)} /></View>;
}
