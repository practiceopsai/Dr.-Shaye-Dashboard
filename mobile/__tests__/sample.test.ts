import { createSampleApi } from '../src/sample';

test('sample review, capture, and approval work without any network requests', async () => {
  const transport = jest.spyOn(global, 'fetch').mockRejectedValue(new Error('Preview must not use the network'));
  try {
    const api = createSampleApi();
    expect((await api.me()).email).toBe('sample@example.test');
    const before = await api.dashboard();
    const approval = await api.approve(before.cards[0]);
    expect(approval.exact_action.recipients).toEqual(['colleague@example.test']);
    await api.execute(approval);
    expect((await api.dashboard()).cards).not.toContainEqual(before.cards[0]);
    await expect(api.execute(approval)).rejects.toThrow('no longer available');
    const captured = await api.voice('Plan a sample workshop');
    expect(captured.eli_agent_writeback).toBe(false);
    expect((await api.dashboard()).cards.some(card => card.title === 'Plan a sample workshop')).toBe(true);
    await api.feedback({ category: 'priority_correction', feedback: 'Sample completed', item_id: captured.command_id, disposition: 'complete' });
    expect((await api.dashboard()).cards.some(card => card.id === captured.command_id)).toBe(false);
    expect(transport).not.toHaveBeenCalled();
    expect((await createSampleApi().dashboard()).cards).toEqual(before.cards);
  } finally { transport.mockRestore(); }
});
