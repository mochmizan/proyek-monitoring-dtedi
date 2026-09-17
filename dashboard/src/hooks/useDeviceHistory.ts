import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { fetchDeviceHistory } from '../lib/api';
import { POLL_TIER3_PRESENCE_MS, STALE_TIER3_PRESENCE_MS } from '../lib/constants';
import { useJitteredInterval } from '../lib/jitter';
import type { DeviceHistoryResponse } from '../types/api';

export type TimeRange = '6h' | '24h' | '7d' | '30d';

export function useDeviceHistory(deviceId: string, timeRange: TimeRange) {
  const isRealtime = timeRange === '6h' || timeRange === '24h';
  const jitteredInterval = useJitteredInterval(POLL_TIER3_PRESENCE_MS);
  const refetchInterval = isRealtime ? jitteredInterval : false;
  const query = useQuery<DeviceHistoryResponse>({
    queryKey: queryKeys.devices.history(deviceId, timeRange),
    queryFn: () => fetchDeviceHistory(deviceId, timeRange),
    refetchInterval,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    staleTime: STALE_TIER3_PRESENCE_MS,
  });

  return {
    data: query.data,
    isFetching: query.isFetching,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
    dataUpdatedAt: query.dataUpdatedAt,
  };
}
