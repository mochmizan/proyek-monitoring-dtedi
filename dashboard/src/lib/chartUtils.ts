import { GAP_FLOOR_MIN, GAP_FLOOR_BY_TYPE_MIN } from './constants';
import { parseToDate } from './dateUtils';

export { parseToDate };
export const GAP_FLOOR_MS = GAP_FLOOR_MIN * 60 * 1000;

export function formatAxisTime(isoStr: string, range: string): string {
  const d = parseToDate(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  if (range === '1h' || range === '6h' || range === '24h') {
    return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Jakarta' });
  }
  return d.toLocaleString('id-ID', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Jakarta',
  }).replace(',', '');
}

export function formatTooltipTime(isoStr: string): string {
  const d = parseToDate(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleString('id-ID', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Jakarta',
  }) + ' WIB';
}

/**
 * Calculates the type-aware and range-scaled gap threshold in minutes.
 * - Enforces minimum reporting floors by device type (TS: 15m, AC/ACC: 6m, ATS/DEFAULT: 3m).
 * - Dynamically scales for extended historical ranges (> 6h / 360m) to accommodate downsampled intervals.
 */
export function getGapThresholdMinutes(devType?: string, rangeMinutes?: number): number {
  const key = (devType ?? 'DEFAULT').toUpperCase();
  const baseFloor = GAP_FLOOR_BY_TYPE_MIN[key] ?? GAP_FLOOR_BY_TYPE_MIN.DEFAULT;
  if (!rangeMinutes || rangeMinutes <= 0) {
    return baseFloor;
  }
  // Dynamic scaling: for ranges > 6h (360m), scale gap threshold (1 min per hour of range)
  const dynamicFloor = rangeMinutes > 360 ? Math.round(rangeMinutes / 60) : 0;
  return Math.max(baseFloor, dynamicFloor);
}

export function getMedianIntervalMs(pointTimes: (number | null)[], maxFloorMs: number = GAP_FLOOR_MS): number | null {
  const validIntervals: number[] = [];
  const upperLimit = Math.max(GAP_FLOOR_MS, maxFloorMs) * 20;
  for (let i = 1; i < pointTimes.length; i++) {
    const a = pointTimes[i - 1];
    const b = pointTimes[i];
    if (a !== null && b !== null) {
      const d = b - a;
      if (d > 0 && d < upperLimit) validIntervals.push(d);
    }
  }
  if (validIntervals.length < 8) return null;
  validIntervals.sort((a, b) => a - b);
  return validIntervals[Math.floor(validIntervals.length / 2)];
}

export function getGapThresholdMs(
  pointTimes: (number | null)[],
  devType?: string,
  rangeMinutes?: number
): number {
  const floorMin = getGapThresholdMinutes(devType, rangeMinutes);
  const floorMs = floorMin * 60 * 1000;
  const median = getMedianIntervalMs(pointTimes, floorMs);
  if (median === null) return floorMs;
  return Math.max(floorMs, median * 10);
}

export function getOutages(
  pointTimes: (number | null)[],
  minTimeMs: number,
  gapThresholdMs: number,
): { start: number; end: number }[] {
  const list: { start: number; end: number }[] = [];
  for (let i = 1; i < pointTimes.length; i++) {
    const a = pointTimes[i - 1];
    const b = pointTimes[i];
    if (a !== null && b !== null && b - a > gapThresholdMs) list.push({ start: a, end: b });
  }
  const firstValid = pointTimes.find((t) => t !== null) as number | undefined;
  if (firstValid !== undefined && firstValid - minTimeMs > gapThresholdMs) {
    list.unshift({ start: minTimeMs, end: firstValid });
  }
  return list;
}
