import type { Approval, AuthUser, Card, Dashboard, Execution, FeedbackRequest, FeedbackResponse, PhoneAccess, VoiceResponse } from './types';

export class ApiError extends Error {
  constructor(message: string, public status = 0, public uncertain = false) { super(message); this.name = 'ApiError'; }
}

export function createApi(base: string, getToken: () => Promise<string>, unauthorized: () => void, transport: typeof fetch = fetch) {
  if (!base.startsWith('https://')) throw new Error('The Eli API must use HTTPS.');
  async function call<T>(path: string, body?: unknown): Promise<T> {
    const token = await getToken();
    if (!token) throw new ApiError('Sign in to continue.', 401);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120_000);
    try {
      const response = await transport(`${base.replace(/\/$/, '')}${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: controller.signal,
      });
      if (response.status === 401 || response.status === 403) unauthorized();
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new ApiError(typeof result.detail === 'string' ? result.detail : `Request failed (${response.status}).`, response.status, body !== undefined && response.status >= 500);
      return result as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(body === undefined
        ? 'Eli could not be reached. Check your connection and refresh.'
        : 'Delivery could not be confirmed. Check Eli before sending again to avoid a duplicate.', 0, body !== undefined);
    } finally { clearTimeout(timeout); }
  }
  return {
    phone: () => call<PhoneAccess>('/api/phone/access'),
    answerPhoneQuestion: (id: string, answer: string) => call<{status: string; job_id: string}>(`/api/phone/jobs/${encodeURIComponent(id)}/answer`, { answer }),
    me: () => call<AuthUser>('/api/auth/me'),
    dashboard: (refresh = false) => call<Dashboard>(`/api/dashboard?refresh=${refresh}`),
    feedback: (request: FeedbackRequest) => call<FeedbackResponse>('/api/feedback', request),
    retryFeedback: (id: string) => call<FeedbackResponse>(`/api/feedback/${encodeURIComponent(id)}/retry`, {}),
    voice: (transcript: string) => call<VoiceResponse>('/api/voice', { transcript }),
    approve: (item: Card) => call<Approval>('/api/approvals', { item }),
    execute: (approval: Approval) => call<Execution>('/api/execute', { approval_id: approval.approval_id, payload_hash: approval.payload_hash }),
  };
}
export type Api = ReturnType<typeof createApi>;
