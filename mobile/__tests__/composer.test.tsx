import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Composer } from '../src/Composer';
import { ApiError, type Api } from '../src/api';
import { drafts } from '../src/drafts';
jest.mock('@expo/vector-icons/Ionicons', () => 'Icon');
jest.mock('../src/drafts', () => ({ drafts: { load: jest.fn().mockResolvedValue('Saved planning request'), save: jest.fn().mockResolvedValue(undefined), flush: jest.fn().mockResolvedValue(undefined) } }));
jest.mock('expo-speech-recognition', () => ({ useSpeechRecognitionEvent: jest.fn(), ExpoSpeechRecognitionModule: { abort: jest.fn(), stop: jest.fn(), start: jest.fn(), requestPermissionsAsync: jest.fn().mockResolvedValue({ granted: false }) } }));

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
