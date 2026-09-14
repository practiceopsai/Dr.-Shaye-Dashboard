import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Updates from 'expo-updates';
import { ApiError, createApi, type Api } from './src/api';
import * as auth from './src/auth';
import { config, loginConfigured } from './src/config';
import { useDashboard } from './src/useDashboard';
import { drafts } from './src/drafts';
import type { AuthUser, Card } from './src/types';
import { Composer } from './src/Composer';
import { ApprovalSheet } from './src/ApprovalSheet';
import { Commitments, EliStatus, LegalLinks, Schedule, Today } from './src/screens';
import { displayTime } from './src/freshness';
import { Body, Button, colors, Empty, Heading, Icon, type IconName, Kicker, Notice, Panel, s, Small, Title } from './src/ui';

type Tab = 'today' | 'schedule' | 'commitments' | 'decisions' | 'eli';
type Sheet = { type: 'request' | 'feedback'; card?: Card } | { type: 'approval'; card: Card } | { type: 'settings' };
const tabs: { key: Tab; label: string; title: string; icon: IconName }[] = [
  { key: 'today', label: 'Today', title: 'Today', icon: 'sunny-outline' },
  { key: 'schedule', label: 'Schedule', title: 'Your schedule', icon: 'calendar-outline' },
  { key: 'commitments', label: 'Work', title: 'Commitments', icon: 'layers-outline' },
  { key: 'decisions', label: 'Decide', title: 'Decisions', icon: 'checkmark-circle-outline' },
  { key: 'eli', label: 'Eli', title: 'Eli’s current state', icon: 'leaf-outline' },
];

function Settings({ user, logout, close }: { user: AuthUser; logout: () => void; close: () => void }) {
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [available, setAvailable] = useState(false);
  async function check() {
    if (!Updates.isEnabled) { setMessage('App updates arrive through TestFlight. Your Eli data refreshes automatically.'); return; }
    setBusy(true);
    try {
      const update = await Updates.checkForUpdateAsync();
      if (update.isAvailable) { await Updates.fetchUpdateAsync(); setAvailable(true); setMessage('An update is downloaded. It will apply on the next restart.'); }
      else setMessage('This app is up to date.');
    } catch { setMessage('Updates could not be checked. Your current app remains available.'); }
    finally { setBusy(false); }
  }
  async function apply() {
    setBusy(true);
    try { await drafts.flush(); await Updates.reloadAsync(); }
    catch { setMessage('The app could not restart safely. Try again after closing your drafts.'); setBusy(false); }
  }
  return <View style={s.gap}>
    <Panel><Kicker>Signed in</Kicker><Heading>{user.name}</Heading><Body>{user.email}</Body><Small>{user.role === 'owner' ? 'Principal' : 'Chief of staff'}</Small></Panel>
    <Panel><Kicker>Updates</Kicker><Body>Eli’s data is shared across your devices. The brief refreshes while you use the app and when you return.</Body><Small>Version 1.0.0 · Native changes arrive through TestFlight or the App Store.</Small><Button secondary label="Check for app updates" busy={busy} onPress={() => { void check(); }} />{message ? <Notice>{message}</Notice> : null}{available && <Button label="Restart to apply update" busy={busy} onPress={() => { void apply(); }} />}</Panel>
    <LegalLinks /><Button secondary destructive label="Sign out" icon="log-out-outline" onPress={logout} /><Button label="Done" onPress={close} />
  </View>;
}

export function CommandCenter({ user, api, logout }: { user: AuthUser; api: Api; logout: () => void }) {
  const state = useDashboard(api);
  const [tab, setTab] = useState<Tab>('today');
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const scroll = useRef<ScrollView>(null);
  const current = state.current;
  const actions = { review: (card: Card) => setSheet({ type: 'approval', card }), feedback: (card: Card) => setSheet({ type: 'feedback', card }) };
  const close = () => setSheet(null);
  const title = tab === 'today' ? (current?.greeting || 'Your day, in focus.') : tabs.find(value => value.key === tab)!.title;
  return <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
    <View style={styles.header}><View style={s.row}><View style={styles.mark}><Icon name="leaf-outline" color={colors.white} size={24} /></View><View><Text style={styles.brand}>Eli</Text><Small>COMMAND CENTER</Small></View></View><Pressable accessibilityRole="button" accessibilityLabel="Account and settings" onPress={() => setSheet({ type: 'settings' })} style={styles.avatar}><Text style={{ color: colors.green, fontWeight: '700' }}>{user.name.slice(0, 1).toUpperCase()}</Text></Pressable></View>
    <ScrollView ref={scroll} contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={state.loading} onRefresh={() => { void state.refresh(true); }} tintColor={colors.green} />}>
      <View style={{ gap: 8 }}><Kicker>{new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: current?.timezone || 'America/Los_Angeles' }).format(state.now)}</Kicker><Title>{title}</Title></View>
      <View style={s.between}><View style={[s.row, { flex: 1 }]}><Icon name="ellipse" size={7} color={current?.live ? colors.green : colors.gold} /><Small>{current ? `Updated ${displayTime(current.generated_at, current.timezone)}` : state.online ? 'Waiting for a current brief' : 'Offline'}</Small></View><Pressable accessibilityRole="button" accessibilityLabel="Refresh brief" onPress={() => { void state.refresh(true); }} style={styles.refresh}><Icon name="refresh-outline" size={19} /></Pressable></View>
      <Button label="Send a request to Eli" icon="add-outline" onPress={() => setSheet({ type: 'request' })} secondary />
      {!!state.error && <Notice danger>{state.error}</Notice>}
      {!current ? <Empty title={state.loading ? 'Preparing your brief' : 'A current brief is needed'} message={state.loading ? 'Checking Eli, your priorities, and your calendar.' : 'Pull down to refresh. Expired actions stay hidden until fresh information arrives.'} icon={state.loading ? 'sync-outline' : 'cloud-offline-outline'} /> : <>
        {!current.live && <Notice danger>Some sources could not be verified. Approvals are paused until a complete brief is available.</Notice>}
        {current.warnings.map((warning, i) => <Notice key={`${warning}-${i}`}>{warning}</Notice>)}
        {tab === 'today' && <Today data={current} actions={actions} openSchedule={() => { setTab('schedule'); scroll.current?.scrollTo({ y: 0, animated: false }); }} />}
        {tab === 'schedule' && <Schedule data={current} />}
        {tab === 'commitments' && <Commitments data={current} actions={actions} />}
        {tab === 'decisions' && <Commitments data={current} actions={actions} decisions />}
        {tab === 'eli' && <EliStatus data={current} />}
      </>}
      <Button secondary label="Give feedback on Eli or the app" icon="chatbubble-outline" onPress={() => setSheet({ type: 'feedback' })} />
      <Small style={{ textAlign: 'center', paddingTop: 8 }}>One shared command center · Always dated</Small>
    </ScrollView>
    <SafeAreaView edges={['bottom']} style={styles.tabContainer}><View style={styles.tabs}>{tabs.map(item => <Pressable key={item.key} accessibilityRole="tab" accessibilityLabel={item.title} accessibilityState={{ selected: tab === item.key }} onPress={() => { setTab(item.key); scroll.current?.scrollTo({ y: 0, animated: false }); }} style={styles.tab}><View style={[styles.tabIcon, tab === item.key && { backgroundColor: colors.pale }]}><Icon name={item.icon} color={tab === item.key ? colors.green : colors.muted} /></View><Text style={{ fontSize: 11, fontWeight: tab === item.key ? '700' : '400', color: tab === item.key ? colors.green : colors.muted }}>{item.label}</Text></Pressable>)}</View></SafeAreaView>
    <Modal visible={Boolean(sheet)} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => { /* Close controls save drafts and lock during delivery. */ }}>
      <SafeAreaView style={styles.safe}><KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
        <View style={{ alignItems: 'center' }}><View style={{ width: 36, height: 5, borderRadius: 5, backgroundColor: colors.line }} /></View>
        <Title>{sheet?.type === 'approval' ? 'Review action' : sheet?.type === 'settings' ? 'Your account' : sheet?.type === 'feedback' ? 'Guide Eli' : 'A request for Eli'}</Title>
        {(sheet?.type === 'request' || sheet?.type === 'feedback') && <Composer key={`${sheet.type}.${sheet.card?.id || 'general'}`} api={api} owner={user.email} card={sheet.card} mode={sheet.type} online={state.online} onSent={state.afterMutation} close={close} />}
        {sheet?.type === 'approval' && <ApprovalSheet card={sheet.card} data={current} api={api} online={state.online} onSent={state.afterMutation} close={close} />}
        {sheet?.type === 'settings' && <Settings user={user} logout={logout} close={close} />}
      </ScrollView></KeyboardAvoidingView>{!state.active && <View style={styles.cover}><Icon name="leaf-outline" size={44} /><Heading>Eli Command Center</Heading></View>}</SafeAreaView>
    </Modal>
    {!state.active && <View style={styles.cover}><Icon name="leaf-outline" size={44} /><Heading>Eli Command Center</Heading></View>}
  </SafeAreaView>;
}

function Session() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const epoch = useRef(0);
  const logout = useCallback(() => {
    epoch.current++; setUser(null); setBusy(false);
    void auth.signOut().catch(() => setError('The local session has ended. Google sign-out could not finish; try signing out again.'));
  }, []);
  const [api] = useState(() => createApi(config.apiUrl, auth.getToken, () => {
    epoch.current++; setUser(null); setBusy(false); setError('Your session ended or this account is not authorized. Please sign in again.');
    void auth.signOut().catch(() => undefined);
  }));
  useEffect(() => {
    let alive = true;
    const started = epoch.current;
    void (async () => {
      try { if (await auth.restore()) { const verified = await api.me(); if (alive && epoch.current === started) setUser(verified); } }
      catch { if (alive) setError('Sign in to reconnect to Eli.'); }
      finally { if (alive) setBusy(false); }
    })();
    return () => { alive = false; };
  }, [api]);
  async function login() {
    if (busy) return;
    setBusy(true); setError(''); const started = epoch.current;
    try { if (await auth.signIn()) { const verified = await api.me(); if (epoch.current === started) setUser(verified); } }
    catch (problem) { setError(problem instanceof ApiError ? problem.message : problem instanceof Error ? problem.message : 'Sign-in could not complete.'); }
    finally { setBusy(false); }
  }
  if (user) return <CommandCenter key={user.email} user={user} api={api} logout={logout} />;
  return <SafeAreaView style={styles.safe}><ScrollView contentContainerStyle={styles.login}>
    <View style={[styles.mark, { width: 70, height: 70, borderRadius: 23 }]}><Icon name="leaf-outline" size={38} color={colors.white} /></View>
    <Kicker>Eli Command Center</Kicker><Text style={styles.loginTitle}>A clear view.{ '\n' }A considered next step.</Text><Body style={{ color: colors.muted, fontSize: 17, lineHeight: 26 }}>Your priorities, commitments, and Eli’s current state. Together in one private place.</Body>
    <Panel><Heading>Welcome back</Heading><Body>Sign in with your approved Google Workspace account.</Body>{!!error && <Notice danger>{error}</Notice>}{busy ? <ActivityIndicator color={colors.green} accessibilityLabel="Checking sign-in" /> : <Button label="Continue with Google" icon="logo-google" onPress={() => { void login(); }} disabled={!loginConfigured || Platform.OS === 'web'} />}{!loginConfigured && <Small>Google login is awaiting release configuration.</Small>}{Platform.OS === 'web' && <Small>Install the signed iPhone app to sign in. This browser view is for layout review.</Small>}</Panel>
    <LegalLinks /><Small>Private access for Dr. Shaye and his chief of staff.</Small>
  </ScrollView></SafeAreaView>;
}

class ErrorBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <SafeAreaView style={[styles.safe, { padding: 24, justifyContent: 'center', gap: 20 }]}><Title>Let’s reconnect.</Title><Body>The app encountered a problem. Reopen it to load a fresh brief. Saved drafts remain on this phone.</Body><Button label="Try again" onPress={() => this.setState({ failed: false })} /></SafeAreaView>;
    return this.props.children;
  }
}
export default function App() { return <SafeAreaProvider><StatusBar style="dark" /><ErrorBoundary><Session /></ErrorBoundary></SafeAreaProvider>; }

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.paper },
  header: { paddingHorizontal: 22, paddingVertical: 15, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderColor: colors.line },
  mark: { width: 44, height: 44, borderRadius: 15, backgroundColor: colors.green, alignItems: 'center', justifyContent: 'center' },
  brand: { fontSize: 22, fontWeight: '700', color: colors.ink },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.pale, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.line },
  content: { padding: 22, paddingBottom: 30, gap: 20 },
  refresh: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  tabContainer: { backgroundColor: colors.white, borderTopWidth: 1, borderColor: colors.line },
  tabs: { flexDirection: 'row', paddingHorizontal: 10, paddingVertical: 8 },
  tab: { flex: 1, minHeight: 55, alignItems: 'center', justifyContent: 'center', gap: 3 },
  tabIcon: { borderRadius: 12, paddingHorizontal: 16, paddingVertical: 5 },
  cover: { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: colors.cream, alignItems: 'center', justifyContent: 'center', gap: 16 },
  login: { flexGrow: 1, justifyContent: 'center', padding: 28, gap: 25 },
  loginTitle: { fontSize: 38, lineHeight: 45, color: colors.ink, fontWeight: '600', letterSpacing: -1 },
});
