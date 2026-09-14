import { createApi, ApiError } from '../src/api';
function response(status: number, data: unknown) { return { ok: status >= 200 && status < 300, status, json: async () => data } as Response; }
const base = 'https://example.test';
test('sends a fresh native token with each read', async () => {
  const transport = jest.fn().mockResolvedValue(response(200, {}));
  const token = jest.fn().mockResolvedValueOnce('token-1').mockResolvedValueOnce('token-2');
  const api = createApi(base, token, jest.fn(), transport);
  await api.me(); await api.dashboard(true);
  expect(transport.mock.calls[0][1].headers.Authorization).toBe('Bearer token-1');
  expect(transport.mock.calls[1][1].headers.Authorization).toBe('Bearer token-2');
  expect(transport.mock.calls[1][0]).toBe(`${base}/api/dashboard?refresh=true`);
});
test.each([401, 403])('ends the private session on HTTP %s', async status => {
  const ended = jest.fn();
  const api = createApi(base, async () => 'token', ended, jest.fn().mockResolvedValue(response(status, { detail: 'Unauthorized' })));
  await expect(api.me()).rejects.toMatchObject({ status }); expect(ended).toHaveBeenCalledTimes(1);
});
test('never retries a write after a transport failure', async () => {
  const transport = jest.fn().mockRejectedValue(new Error('network lost'));
  const api = createApi(base, async () => 'token', jest.fn(), transport);
  await expect(api.voice('Please review this')).rejects.toMatchObject({ uncertain: true });
  expect(transport).toHaveBeenCalledTimes(1);
});
test('passes only the exact approval ID and digest for execution', async () => {
  const transport = jest.fn().mockResolvedValue(response(200, { status: 'queued_for_eli_agent' }));
  const api = createApi(base, async () => 'token', jest.fn(), transport);
  await api.execute({ approval_id: 'id', payload_hash: 'hash', expires_in_seconds: 900, exact_action: {} as never });
  expect(JSON.parse(transport.mock.calls[0][1].body)).toEqual({ approval_id: 'id', payload_hash: 'hash' });
});
test('does not make unauthenticated calls or allow cleartext API transport', async () => {
  const transport = jest.fn();
  await expect(createApi(base, async () => '', jest.fn(), transport).me()).rejects.toBeInstanceOf(ApiError);
  expect(transport).not.toHaveBeenCalled();
  expect(() => createApi('http://example.test', async () => '', jest.fn())).toThrow('HTTPS');
});
