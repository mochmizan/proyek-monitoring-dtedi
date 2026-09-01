import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useDeviceHistory } from '../useDeviceHistory';
import * as api from '../../lib/api';

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api');
  return {
    ...actual,
    fetchDeviceHistory: vi.fn(),
  };
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe('useDeviceHistory Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches device history and returns full query state', async () => {
    const mockData = {
      dev_id: 'DEV-01',
      dev_type: 'ATS',
      range: '24h',
      total_points: 2,
      points: [
        { timestamp: '2026-09-01T10:00:00Z', pln: 220, genset: 0, aki: 12.6, state: 'STANDBY' },
        { timestamp: '2026-09-01T11:00:00Z', pln: 221, genset: 0, aki: 12.5, state: 'STANDBY' },
      ],
    };

    vi.mocked(api.fetchDeviceHistory).mockResolvedValueOnce(mockData);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDeviceHistory('DEV-01', '24h'), { wrapper });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.isFetching).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.data).toEqual(mockData);
    expect(result.current.isFetching).toBe(false);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.refetch).toBe('function');
    expect(typeof result.current.dataUpdatedAt).toBe('number');
    expect(result.current.dataUpdatedAt).toBeGreaterThan(0);
    expect(api.fetchDeviceHistory).toHaveBeenCalledWith('DEV-01', '24h');
  });

  it('handles range changes between realtime (6h, 24h) and long-term (7d, 30d)', async () => {
    vi.mocked(api.fetchDeviceHistory).mockResolvedValue({
      dev_id: 'DEV-01',
      dev_type: 'TS',
      range: '6h',
      total_points: 0,
      points: [],
    });

    const { wrapper, queryClient } = createWrapper();

    // 6h range -> should query with 6h
    const { result, rerender } = renderHook(
      ({ range }: { range: '6h' | '24h' | '7d' | '30d' }) => useDeviceHistory('DEV-01', range),
      { wrapper, initialProps: { range: '6h' } }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.fetchDeviceHistory).toHaveBeenCalledWith('DEV-01', '6h');

    // Query defaults / options check for 6h (15s refetchInterval)
    const query6h = queryClient.getQueryCache().find({
      queryKey: ['devices', 'history', 'DEV-01', { range: '6h' }],
    });
    expect(query6h).toBeDefined();

    // Re-render with 24h
    rerender({ range: '24h' });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.fetchDeviceHistory).toHaveBeenCalledWith('DEV-01', '24h');

    // Re-render with 7d
    rerender({ range: '7d' });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.fetchDeviceHistory).toHaveBeenCalledWith('DEV-01', '7d');

    // Re-render with 30d
    rerender({ range: '30d' });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(api.fetchDeviceHistory).toHaveBeenCalledWith('DEV-01', '30d');
  });

  it('handles query error state correctly', async () => {
    vi.mocked(api.fetchDeviceHistory).mockRejectedValueOnce(new Error('Failed to load history'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDeviceHistory('DEV-01', '6h'), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe('Failed to load history');
  });
});
