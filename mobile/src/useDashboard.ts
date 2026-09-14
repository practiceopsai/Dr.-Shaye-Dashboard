import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import type { Api } from './api';
import type { Dashboard } from './types';
import { isCurrent } from './freshness';

export function useDashboard(api: Api) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [online, setOnline] = useState(true);
  const [active, setActive] = useState(AppState.currentState === 'active');
  const [now, setNow] = useState(Date.now());
  const mounted = useRef(true);
  const running = useRef<Promise<void> | null>(null);
  const connectionEpoch = useRef(0);
  const reachable = useRef(true);

  const refresh = useCallback((force = false): Promise<void> => {
    if (running.current) return running.current;
    if (!reachable.current) return Promise.resolve();
    setNow(Date.now());
    setLoading(true);
    const epoch = connectionEpoch.current;
    const request = (async () => {
      try {
        const next = await api.dashboard(force);
        if (!mounted.current || epoch !== connectionEpoch.current) return;
        if (!isCurrent(next)) throw new Error('This brief has expired. Pull down to refresh.');
        setData(next);
        setNow(Date.now());
        setError('');
      } catch (problem) {
        if (!mounted.current || epoch !== connectionEpoch.current) return;
        setData(null);
        setError(problem instanceof Error ? problem.message : 'The brief is unavailable.');
      } finally {
        if (mounted.current) setLoading(false);
        running.current = null;
      }
    })();
    running.current = request;
    return request;
  }, [api]);

  const afterMutation = useCallback(async () => {
    // A read started before the write must finish before the replacement read.
    if (running.current) await running.current;
    if (!mounted.current) return;
    setData(null);
    await refresh(true);
  }, [refresh]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    const app = AppState.addEventListener('change', state => {
      setNow(Date.now());
      setActive(state === 'active');
      if (state === 'active') void refresh();
    });
    const network = NetInfo.addEventListener(state => {
      const connected = state.isConnected !== false && state.isInternetReachable !== false;
      const previous = reachable.current;
      reachable.current = connected;
      setOnline(connected);
      if (!connected) {
        connectionEpoch.current++;
        setData(null);
        setError('You are offline. Connect to load a current brief.');
      } else if (!previous) {
        void (running.current || Promise.resolve()).then(() => { if (mounted.current) void refresh(); });
      }
    });
    const clock = setInterval(() => setNow(Date.now()), 15_000);
    const poll = setInterval(() => { if (AppState.currentState === 'active') void refresh(); }, 60_000);
    return () => { mounted.current = false; connectionEpoch.current++; app.remove(); network(); clearInterval(clock); clearInterval(poll); };
  }, [refresh]);

  return { data, current: online && active && isCurrent(data, now) ? data : null, error, loading, online, active, now, refresh, afterMutation };
}
