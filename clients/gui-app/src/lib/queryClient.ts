import { QueryClient, QueryCache, MutationCache } from '@tanstack/react-query';
import { STALE_MS } from './constants';

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
      retry: 1,
    },
  },
});
