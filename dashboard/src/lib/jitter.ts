import { useMemo } from 'react';

/**
 * Computes a randomized interval around a base duration (default +/- 15%).
 * Randomizes client polling phase to prevent synchronization stampedes ("thundering herd").
 *
 * @param baseMs Base polling interval in milliseconds
 * @param jitterFactor Variance fraction (0.15 = +/- 15%)
 * @returns Jittered interval in milliseconds (integer)
 */
export function getJitteredInterval(baseMs: number, jitterFactor = 0.15): number {
  if (baseMs <= 0) return 0;
  const min = Math.floor(baseMs * (1 - jitterFactor));
  const max = Math.ceil(baseMs * (1 + jitterFactor));
  return Math.floor(Math.random() * (max - min + 1) + min);
}

/**
 * Hook to produce a stable jittered polling interval across component re-renders.
 * Prevents TanStack Query v5 from clearing and restarting interval timers on every render.
 */
export function useJitteredInterval(baseMs: number, jitterFactor = 0.15): number {
  return useMemo(() => getJitteredInterval(baseMs, jitterFactor), [baseMs, jitterFactor]);
}

