import { GAP_FLOOR_MIN } from './constants';
import { parseToDate } from './dateUtils';

export { parseToDate };
export const GAP_FLOOR_MS = GAP_FLOOR_MIN * 60 * 1000;

export function formatAxisTime(isoStr: string, range: string): string {
  const d = parseToDate(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  if (range === '6h' || range === '24h') {
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

export function getMedianIntervalMs(pointTimes: (number | null)[]): number | null {
  const validIntervals: number[] = [];
  for (let i = 1; i < pointTimes.length; i++) {
    const a = pointTimes[i - 1];
    const b = pointTimes[i];
    if (a !== null && b !== null) {
      const d = b - a;
      if (d > 0 && d < GAP_FLOOR_MS * 20) validIntervals.push(d);
    }
  }
  if (validIntervals.length < 8) return null;
  validIntervals.sort((a, b) => a - b);
  return validIntervals[Math.floor(validIntervals.length / 2)];
}

export function getGapThresholdMs(pointTimes: (number | null)[]): number {
  const median = getMedianIntervalMs(pointTimes);
  if (median === null) return GAP_FLOOR_MS;
  return Math.max(GAP_FLOOR_MS, median * 10);
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
