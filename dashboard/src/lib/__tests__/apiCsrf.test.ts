import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  apiFetch,
  clearCsrfToken,
  ensureCsrfToken,
  loginUser,
} from '../api';

const user = {
  username: 'admin',
  display_name: 'Admin',
  role: 'admin',
  is_active: true,
  must_change_password: false,
};

describe('CSRF client lifecycle', () => {
  beforeEach(() => {
    clearCsrfToken();
    vi.restoreAllMocks();
  });

  it('logs in without requesting a CSRF token first', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(user), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(loginUser({ username: 'admin', password: 'secret' })).resolves.toEqual(user);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/auth/login');
  });

  it('coalesces concurrent token requests', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ csrf_token: 'token-a' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(Promise.all([ensureCsrfToken(), ensureCsrfToken()])).resolves.toEqual([
      'token-a',
      'token-a',
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('refreshes and retries once only for an explicit CSRF error', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'token-a' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        detail: { code: 'CSRF_TOKEN_INVALID', message: 'Invalid token' },
      }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'token-b' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }));

    const response = await apiFetch('/api/rooms', { method: 'POST', body: '{}' });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    const retryHeaders = fetchMock.mock.calls[3]?.[1]?.headers as Headers;
    expect(retryHeaders.get('X-CSRF-Token')).toBe('token-b');
  });

  it('coalesces concurrent refreshes after token rejection', async () => {
    let tokenRequests = 0;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (String(input).endsWith('/api/auth/csrf-token')) {
        tokenRequests += 1;
        return new Response(JSON.stringify({
          csrf_token: tokenRequests === 1 ? 'token-old' : 'token-new',
        }), { status: 200 });
      }

      const headers = init?.headers as Headers;
      if (headers.get('X-CSRF-Token') === 'token-old') {
        return new Response(JSON.stringify({
          detail: { code: 'CSRF_TOKEN_INVALID', message: 'Invalid token' },
        }), { status: 403 });
      }
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
    });

    await ensureCsrfToken();
    const responses = await Promise.all([
      apiFetch('/api/rooms', { method: 'POST', body: '{}' }),
      apiFetch('/api/schedules', { method: 'POST', body: '{}' }),
    ]);

    expect(responses.map((response) => response.status)).toEqual([200, 200]);
    expect(tokenRequests).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it('does not retry a role-based 403', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'token-a' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Operation not permitted' }), { status: 403 }));

    const response = await apiFetch('/api/rooms', { method: 'POST', body: '{}' });

    expect(response.status).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('preserves structured error codes', () => {
    const error = new ApiError(403, 'Invalid token', 'CSRF_TOKEN_INVALID');
    expect(error.code).toBe('CSRF_TOKEN_INVALID');
  });
});
