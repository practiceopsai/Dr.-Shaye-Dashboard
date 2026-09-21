import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PhoneRequests } from '../src/PhoneRequests';
import type { Api } from '../src/api';
jest.mock('@expo/vector-icons/Ionicons', () => 'Icon');

test('requests cancellation once and does not claim an in-flight effect was undone', async () => {
  const job = { id: 'running', state: 'running', created: 1, transcript: 'Send a message' };
  const api = { phone: jest.fn().mockResolvedValue({ jobs: [job], outbound: [] }), cancelPhoneTask: jest.fn().mockImplementation(async () => {
    api.phone.mockResolvedValue({ jobs: [{ ...job, cancel_requested: 1 }], outbound: [] });
    return { state: 'cancel_requested', effect_cancelled: false };
  }) };
  const view = render(<PhoneRequests api={api as unknown as Api} close={jest.fn()} />);
  await screen.findByText('Stop remaining work');
  await act(async () => {
    fireEvent.press(screen.getByText('Stop remaining work'));
    fireEvent.press(screen.getByText('Stop remaining work'));
  });
  expect(api.cancelPhoneTask).toHaveBeenCalledTimes(1);
  await screen.findByText('Cancellation requested');
  expect(screen.getByText('Actions already accepted by a provider may finish.')).toBeTruthy();
  view.unmount();
});

test('shows a saved clarification and resumes that task once after a double tap', async () => {
  const data = { phone: '+12025550101', eli_number: '+12025550100', pin_required: false, outbound: [], jobs: [
    { id: 'question-one', created: 1, transcript: 'Email Fabio', state: 'waiting_for_input', result: 'What should I say?' },
  ] };
  const api = { phone: jest.fn().mockResolvedValue(data), answerPhoneQuestion: jest.fn().mockResolvedValue({ status: 'resumed', job_id: 'next' }) } as unknown as Api;
  const view = render(<PhoneRequests api={api} close={jest.fn()} />);
  await screen.findByText('Needs your answer');
  expect(screen.getByText(/No access code is needed/)).toBeTruthy();
  fireEvent.changeText(screen.getByLabelText('Your answer'), 'Say hello.');
  await act(async () => {
    fireEvent.press(screen.getByRole('button', { name: 'Answer and resume' }));
    fireEvent.press(screen.getByRole('button', { name: 'Answer and resume' }));
  });
  await waitFor(() => expect(api.answerPhoneQuestion).toHaveBeenCalledTimes(1));
  expect(api.answerPhoneQuestion).toHaveBeenCalledWith('question-one', 'Say hello.');
  view.unmount();
});
