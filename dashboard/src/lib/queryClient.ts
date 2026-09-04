import { QueryClient, QueryCache, MutationCache, keepPreviousData } from '@tanstack/react-query';
import { STALE_MS } from './constants';
import { ApiError } from './api';

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      console.error('[QueryCache]', error);
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      console.error('[MutationCache]', error);
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: STALE_MS,
      gcTime: 5 * 60 * 1000,
      placeholderData: keepPreviousData,
      refetchOnWindowFocus: true,
      refetchIntervalInBackground: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status === 401) return false;
        return failureCount < 1;
      },
    },
  },
});
