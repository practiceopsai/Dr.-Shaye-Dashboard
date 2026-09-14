import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { ApprovalSheet } from '../src/ApprovalSheet';
import type { Api } from '../src/api';
import { card, dashboard } from './fixture';
jest.mock('@expo/vector-icons/Ionicons', () => 'Icon');
const approval = { approval_id: 'approval', payload_hash: 'digest', expires_in_seconds: 900, exact_action: card.action };

test('shows recipients before approval and submits only once after a double tap', async () => {
  const api = { approve: jest.fn().mockResolvedValue(approval), execute: jest.fn().mockResolvedValue({ status: 'queued_for_eli_agent' }) } as unknown as Api;
  const refreshed = jest.fn().mockResolvedValue(undefined);
  render(<ApprovalSheet card={card} data={dashboard()} api={api} online onSent={refreshed} close={jest.fn()} />);
  expect(screen.getByText('Recipients: review@example.test')).toBeTruthy();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve exact action' })).toBeEnabled());
  await act(async () => { fireEvent.press(screen.getByRole('button', { name: 'Approve exact action' })); fireEvent.press(screen.getByRole('button', { name: 'Approve exact action' })); });
  expect(api.execute).toHaveBeenCalledTimes(1);
  expect(api.execute).toHaveBeenCalledWith(approval);
  expect(screen.getByText(/external action has not been confirmed/)).toBeTruthy();
  expect(refreshed).toHaveBeenCalledTimes(1);
});
test('an expired brief disables a previously prepared approval', async () => {
  const api = { approve: jest.fn().mockResolvedValue(approval), execute: jest.fn() } as unknown as Api;
  const data = dashboard();
  const props = { card, api, online: true, onSent: jest.fn(), close: jest.fn() };
  const { rerender } = render(<ApprovalSheet {...props} data={data} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve exact action' })).toBeEnabled());
  rerender(<ApprovalSheet {...props} data={{ ...data, expires_at: '2020-01-01T00:00:00Z' }} />);
  expect(screen.getByRole('button', { name: 'Approve exact action' })).toBeDisabled();
  fireEvent.press(screen.getByRole('button', { name: 'Approve exact action' }));
  expect(api.execute).not.toHaveBeenCalled();
});
