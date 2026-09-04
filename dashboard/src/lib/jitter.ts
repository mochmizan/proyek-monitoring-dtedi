/**
 * Computes a randomized interval around a base duration (default +/- 15%).
 * Re-evaluated by TanStack Query v5 after every poll tick to prevent
 * client synchronization and database cache stampedes ("thundering herd").
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
