import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PhoneRequests } from '../src/PhoneRequests';
import type { Api } from '../src/api';
jest.mock('@expo/vector-icons/Ionicons', () => 'Icon');

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
