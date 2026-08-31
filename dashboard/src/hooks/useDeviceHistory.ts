import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { fetchDeviceHistory } from '../lib/api';
import { POLL_MS } from '../lib/constants';

export function useDeviceHistory(deviceId: string, timeRange: '6h' | '24h' | '7d' | '30d') {
  return useQuery({
    queryKey: queryKeys.devices.history(deviceId, timeRange),
    queryFn: () => fetchDeviceHistory(deviceId, timeRange),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    placeholderData: keepPreviousData,
  });
}
