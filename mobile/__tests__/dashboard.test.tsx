import { act, renderHook } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import { useDashboard } from '../src/useDashboard';
import { dashboard } from './fixture';
import type { Api } from '../src/api';

let mockNetwork: (state: { isConnected: boolean; isInternetReachable: boolean }) => void;
jest.mock('@react-native-community/netinfo', () => ({ __esModule: true, default: { addEventListener: (callback: typeof mockNetwork) => { mockNetwork = callback; return jest.fn(); } } }));
const initial = Date.parse('2026-09-14T18:00:00Z');
let changeState: (value: AppStateStatus) => void;
beforeEach(() => {
  jest.useFakeTimers(); jest.setSystemTime(initial);
  Object.defineProperty(AppState, 'currentState', { value: 'active', configurable: true, writable: true });
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_name, callback) => { changeState = callback; return { remove: jest.fn() }; });
});
afterEach(() => { jest.useRealTimers(); jest.restoreAllMocks(); });

test('foregrounding after expiry hides the old brief before a network response', async () => {
  const read = jest.fn().mockResolvedValueOnce(dashboard(initial)).mockImplementation(() => new Promise(() => {}));
  const api = { dashboard: read } as unknown as Api;
  const { result } = renderHook(() => useDashboard(api));
  await act(async () => {});
  expect(result.current.current).not.toBeNull();
  act(() => { changeState('background'); });
  jest.setSystemTime(initial + 301_000);
  act(() => { changeState('active'); });
  expect(result.current.current).toBeNull();
  expect(read).toHaveBeenCalledTimes(2);
});
test('failed refresh clears previously visible data', async () => {
  const read = jest.fn().mockResolvedValueOnce(dashboard(initial)).mockRejectedValueOnce(new Error('offline'));
  const api = { dashboard: read } as unknown as Api;
  const { result } = renderHook(() => useDashboard(api));
  await act(async () => {});
  await act(async () => { await result.current.refresh(true); });
  expect(result.current.current).toBeNull(); expect(result.current.error).toBe('offline');
});
test('does not accept a response from before connectivity was lost', async () => {
  let resolveOld!: (value: ReturnType<typeof dashboard>) => void;
  const read = jest.fn().mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValue(dashboard(initial));
  const api = { dashboard: read } as unknown as Api;
  const { result } = renderHook(() => useDashboard(api));
  act(() => { mockNetwork({ isConnected: false, isInternetReachable: false }); });
  await act(async () => { resolveOld(dashboard(initial)); });
  expect(result.current.current).toBeNull();
  await act(async () => { mockNetwork({ isConnected: true, isInternetReachable: true }); });
  expect(result.current.current).not.toBeNull(); expect(read).toHaveBeenCalledTimes(2);
});
test('a successful mutation forces a replacement brief', async () => {
  const read = jest.fn().mockResolvedValue(dashboard(initial));
  const api = { dashboard: read } as unknown as Api;
  const { result } = renderHook(() => useDashboard(api));
  await act(async () => {});
  await act(async () => { await result.current.afterMutation(); });
  expect(read.mock.calls).toEqual([[false], [true]]);
});
