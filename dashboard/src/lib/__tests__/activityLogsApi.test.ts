import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getActivityLogs } from '../api';
import { queryKeys } from '../queryKeys';
import type { ActivityLogsResponse } from '../../types/api';

const mockResponse: ActivityLogsResponse = {
  items: [
    {
      id: 'log-1',
      user_name: 'admin',
      user_id: 'u-1',
      role: 'admin',
      activity: {
        action: 'Login',
        category: 'auth',
        details: { ip: '127.0.0.1' },
        status: 'success',
        ip_address: '127.0.0.1',
      },
      created_at: '2026-09-16T14:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
};

describe('Activity Logs API and QueryKeys', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches activity logs with default parameters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const result = await getActivityLogs();

    expect(result).toEqual(mockResponse);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(calledUrl.pathname).toBe('/api/admin/users/activity-logs');
  });

  it('fetches activity logs with filtering parameters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await getActivityLogs({
      page: 2,
      limit: 20,
      username: 'johndoe',
      role: 'operator',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(calledUrl.searchParams.get('page')).toBe('2');
    expect(calledUrl.searchParams.get('limit')).toBe('20');
    expect(calledUrl.searchParams.get('username')).toBe('johndoe');
    expect(calledUrl.searchParams.get('role')).toBe('operator');
  });

  it('constructs query keys accurately', () => {
    const filter = { page: 1, limit: 50, username: 'admin' };
    expect(queryKeys.activityLogs.list(filter)).toEqual([
      'activityLogs',
      'list',
      filter,
    ]);
    expect(queryKeys.users.activityLogs(filter)).toEqual([
      'users',
      'activityLogs',
      filter,
    ]);
  });
});
