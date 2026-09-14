import React, { useEffect, useRef, useState } from 'react';
import { AppState, Linking, TextInput, View } from 'react-native';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import type { Api } from './api';
import { ApiError } from './api';
import type { Card, FeedbackCategory, FeedbackRequest } from './types';
import { drafts } from './drafts';
import { Body, Button, Heading, Notice, Panel, s, Small } from './ui';

export function Composer({ api, owner, card, mode, online, onSent, close }: {
  api: Api; owner: string; card?: Card; mode: 'request' | 'feedback'; online: boolean; onSent: () => Promise<void>; close: () => void;
}) {
  const [text, setText] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [category, setCategory] = useState<FeedbackCategory>('priority_correction');
  const [disposition, setDisposition] = useState<FeedbackRequest['disposition']>('modify');
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState('');
  const [storageError, setStorageError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const currentText = useRef('');
  const locked = useRef(false);
  const mounted = useRef(true);
  const ready = useRef(false);
  const dictatedPrefix = useRef('');
  const kind = `${mode}.${card?.id || 'general'}`;
  const limit = mode === 'request' ? 4000 : 2000;
  const save = (value: string) => drafts.save(owner, kind, value).then(() => {
    if (mounted.current) setStorageError('');
    return true;
  }).catch(() => {
    if (mounted.current) setStorageError('Your draft could not be saved on this phone. Keep this screen open until you send it.');
    return false;
  });
  const update = (value: string) => { currentText.current = value.slice(0, limit); setText(currentText.current); setError(''); };

  useEffect(() => {
    mounted.current = true;
    void drafts.load(owner, kind).then(value => {
      if (mounted.current) { currentText.current = value; setText(value); setLoaded(true); ready.current = true; }
    }).catch(() => { if (mounted.current) { setLoaded(true); setStorageError('The saved draft could not be opened.'); } });
    const sub = AppState.addEventListener('change', state => {
      if (state !== 'active') { ExpoSpeechRecognitionModule.abort(); if (ready.current) void save(currentText.current); }
    });
    return () => { mounted.current = false; sub.remove(); ExpoSpeechRecognitionModule.abort(); if (ready.current) void save(currentText.current); };
    // Owner and draft key are fixed for this mounted composer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [owner, kind]);
  useEffect(() => {
    if (!loaded) return;
    const timer = setTimeout(() => { void save(text); }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, loaded]);

  useSpeechRecognitionEvent('start', () => setListening(true));
  useSpeechRecognitionEvent('end', () => setListening(false));
  useSpeechRecognitionEvent('result', event => {
    const transcript = event.results[0]?.transcript;
    if (transcript && !locked.current) update(`${dictatedPrefix.current}${transcript}`);
  });
  useSpeechRecognitionEvent('error', event => {
    setListening(false);
    if (event.error !== 'aborted') setError(event.error === 'not-allowed' ? 'Dictation permission was denied. You can type your request.' : 'Dictation stopped. You can edit the text or try again.');
  });
  async function dictate() {
    if (listening) { ExpoSpeechRecognitionModule.stop(); return; }
    try {
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permission.granted) { setPermissionDenied(true); setError('Allow microphone and speech recognition in Settings, or type your request.'); return; }
      setPermissionDenied(false);
      dictatedPrefix.current = currentText.current.trim() ? `${currentText.current.trim()} ` : '';
      ExpoSpeechRecognitionModule.start({ lang: 'en-US', interimResults: true, continuous: false, addsPunctuation: true });
    } catch { setError('Dictation is unavailable on this device. You can type instead.'); }
  }

  async function send() {
    if (locked.current || !text.trim() || !online || uncertain) return;
    locked.current = true;
    ExpoSpeechRecognitionModule.abort();
    setBusy(true); setError('');
    try {
      const result = mode === 'request'
        ? await api.voice(text.trim())
        : await api.feedback({ category, feedback: text.trim(), ...(card ? { item_id: card.id, disposition } : {}) });
      if (!mounted.current) return;
      setReceipt(`${result.status === 'queued' ? 'Safely queued' : 'Recorded with Eli'}. ${'message' in result ? result.message : result.detail}`);
      currentText.current = ''; setText('');
      await save('');
      void onSent();
    } catch (problem) {
      if (!mounted.current) return;
      setError(problem instanceof Error ? problem.message : 'Could not send your request.');
      setUncertain(problem instanceof ApiError && problem.uncertain);
    } finally { if (mounted.current) setBusy(false); locked.current = false; }
  }
  async function saveAndClose() { if (await save(currentText.current)) close(); }

  return <View style={s.gap}>
    <Body>{mode === 'request' ? 'Tell Eli what you need. Review the text, then send it for capture and follow-through.' : 'Help Eli improve the brief or record a change you want to the command center.'}</Body>
    {!!card && <Panel><Small>Regarding this priority</Small><Heading>{card.title}</Heading></Panel>}
    {!receipt && mode === 'feedback' && <View style={s.gap}>
      {(['priority_correction', 'dashboard_change', 'positive_reinforcement'] as const).map(value => <Button key={value} secondary={category !== value} label={{ priority_correction: 'Correct priorities', dashboard_change: 'Request an app change', positive_reinforcement: 'Reinforce good judgment' }[value]} disabled={busy} onPress={() => setCategory(value)} />)}
      {!!card && <View style={[s.row, { flexWrap: 'wrap' }]}>{(['modify', 'complete', 'dismiss', 'not_relevant'] as const).map(value => <Button key={value} secondary={disposition !== value} label={{ modify: 'Modify', complete: 'Mark complete', dismiss: 'Dismiss', not_relevant: 'Not relevant' }[value]} disabled={busy} onPress={() => setDisposition(value)} />)}</View>}
    </View>}
    {!!storageError && <Notice danger>{storageError}</Notice>}
    {!!error && <Notice danger>{error}</Notice>}
    {!!receipt ? <><Notice>{receipt}</Notice><Button label="Done" onPress={close} /></> : <>
      <TextInput accessibilityLabel={mode === 'request' ? 'Request for Eli' : 'Feedback for Eli'} style={s.input} multiline maxLength={limit} value={text} editable={loaded && !busy && !listening} onChangeText={update} placeholder={loaded ? 'Write here, or use dictation…' : 'Opening saved draft…'} onBlur={() => { void save(currentText.current); }} />
      <View style={s.between}><Small>{text.length}/{limit}</Small><Small>{storageError ? 'Draft not saved' : 'Draft saves securely on this phone'}</Small></View>
      <Button secondary label={listening ? 'Stop dictation' : 'Dictate'} icon={listening ? 'stop-circle-outline' : 'mic-outline'} onPress={() => { void dictate(); }} disabled={!loaded || busy || uncertain} />
      {permissionDenied && <Button secondary label="Open iPhone Settings" onPress={() => { void Linking.openSettings(); }} />}
      {!online && <Notice>You can keep writing offline. Reconnect to send.</Notice>}
      {uncertain ? <Notice>Delivery is uncertain. Your draft is preserved. Check the command center before sending this request again.</Notice> : <Button label={mode === 'request' ? 'Send request to Eli' : 'Send feedback'} icon="arrow-up-outline" busy={busy} disabled={!loaded || !text.trim() || !online || listening} onPress={() => { void send(); }} />}
      <Small>Requests receive a capture receipt. This screen does not provide a live conversational reply. Please keep patient-identifiable information out of the command center.</Small>
      <Button secondary label="Save draft and close" disabled={!loaded || busy} onPress={() => { void saveAndClose(); }} />
    </>}
  </View>;
}
