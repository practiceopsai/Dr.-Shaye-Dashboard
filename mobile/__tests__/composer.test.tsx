import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';
import { Composer } from '../src/Composer';
import { ApiError, type Api } from '../src/api';
import { drafts } from '../src/drafts';
jest.mock('@expo/vector-icons/Ionicons', () => 'Icon');
jest.mock('../src/drafts', () => ({ drafts: { load: jest.fn().mockResolvedValue('Saved planning request'), save: jest.fn().mockResolvedValue(undefined), flush: jest.fn().mockResolvedValue(undefined) } }));
jest.mock('expo-speech-recognition', () => ({ useSpeechRecognitionEvent: jest.fn(), ExpoSpeechRecognitionModule: { abort: jest.fn(), stop: jest.fn(), start: jest.fn(), requestPermissionsAsync: jest.fn().mockResolvedValue({ granted: false }) } }));

beforeEach(() => {
  jest.mocked(drafts.load).mockReset().mockResolvedValue('Saved planning request');
  jest.mocked(drafts.save).mockReset().mockResolvedValue(undefined);
});

test('restores account-specific draft and retains typing when dictation permission is denied', async () => {
  render(<Composer api={{} as Api} owner="owner@example.test" mode="request" online onSent={jest.fn()} close={jest.fn()} />);
  await waitFor(() => expect(screen.getByDisplayValue('Saved planning request')).toBeTruthy());
  expect(drafts.load).toHaveBeenCalledWith('owner@example.test', 'request.general');
  fireEvent.press(screen.getByRole('button', { name: 'Dictate' }));
  await waitFor(() => expect(screen.getByText(/Allow microphone/)).toBeTruthy());
  expect(screen.getByDisplayValue('Saved planning request')).toBeTruthy();
});
test('preserves a draft and prevents retry after an uncertain write', async () => {
  const api = { voice: jest.fn().mockRejectedValue(new ApiError('Delivery uncertain', 0, true)) } as unknown as Api;
  render(<Composer api={api} owner="owner@example.test" mode="request" online onSent={jest.fn()} close={jest.fn()} />);
  await waitFor(() => expect(screen.getByDisplayValue('Saved planning request')).toBeTruthy());
  fireEvent.press(screen.getByRole('button', { name: 'Send request to Eli' }));
  await waitFor(() => expect(screen.getByText(/Delivery is uncertain/)).toBeTruthy());
  expect(screen.queryByRole('button', { name: 'Send request to Eli' })).toBeNull();
  expect(screen.getByDisplayValue('Saved planning request')).toBeTruthy();
  expect(api.voice).toHaveBeenCalledTimes(1);
});

test('keeps unsent text visible when saving fails, and closes after a successful retry', async () => {
  const close = jest.fn();
  jest.mocked(drafts.save).mockRejectedValue(new Error('Keychain unavailable'));
  render(<Composer api={{} as Api} owner="owner@example.test" mode="request" online onSent={jest.fn()} close={close} />);
  await waitFor(() => expect(screen.getByDisplayValue('Saved planning request')).toBeTruthy());
  fireEvent.press(screen.getByRole('button', { name: 'Save draft and close' }));
  await waitFor(() => expect(screen.getByText(/could not be saved on this phone/)).toBeTruthy());
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByDisplayValue('Saved planning request')).toBeTruthy();
  jest.mocked(drafts.save).mockResolvedValue(undefined);
  fireEvent.press(screen.getByRole('button', { name: 'Save draft and close' }));
  await waitFor(() => expect(close).toHaveBeenCalledTimes(1));
  expect(screen.queryByText(/could not be saved on this phone/)).toBeNull();
});

test('does not erase an existing draft when backgrounded before restoration completes', async () => {
  let restore!: (value: string) => void;
  let change!: (state: AppStateStatus) => void;
  jest.mocked(drafts.load).mockReturnValue(new Promise(resolve => { restore = resolve; }));
  const listener = jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, callback) => {
    change = callback;
    return { remove: jest.fn() };
  });
  try {
    render(<Composer api={{} as Api} owner="owner@example.test" mode="request" online onSent={jest.fn()} close={jest.fn()} />);
    act(() => change('background'));
    expect(drafts.save).not.toHaveBeenCalled();
    await act(async () => restore('Existing unsent request'));
    expect(screen.getByDisplayValue('Existing unsent request')).toBeTruthy();
  } finally { listener.mockRestore(); }
});
