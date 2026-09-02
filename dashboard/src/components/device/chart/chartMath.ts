import type { TelemetryHistoryPoint } from '../../../types/api';
import { GAP_FLOOR_MS } from '../../../lib/chartUtils';

export interface PathSegmentsResult {
  linePath: string;
  areaPath: string;
  isolated: { x: number; y: number }[];
}

/**
 * Maps a timestamp (in ms) to the corresponding SVG X pixel coordinate.
 */
export function timeToX(
  timeMs: number,
  minTimeMs: number,
  maxTimeMs: number,
  plotWidth: number,
  paddingLeft: number
): number {
  if (maxTimeMs <= minTimeMs) return paddingLeft + plotWidth / 2;
  const ratio = Math.max(0, Math.min(1, (timeMs - minTimeMs) / (maxTimeMs - minTimeMs)));
  return paddingLeft + ratio * plotWidth;
}

/**
 * Maps a numeric telemetry value to the corresponding SVG Y pixel coordinate.
 */
export function getY(
  val: number,
  minY: number,
  maxY: number,
  plotHeight: number,
  paddingTop: number
): number {
  if (maxY === minY) return paddingTop + plotHeight / 2;
  return paddingTop + plotHeight - ((val - minY) / (maxY - minY)) * plotHeight;
}

/**
 * Finds the index of the point whose timestamp is closest to targetMs using binary search O(log N).
 */
export function findClosestPointIndex(times: (number | null)[], targetMs: number): number {
  if (!times || times.length === 0) return 0;
  if (times.length === 1) return 0;

  let low = 0;
  let high = times.length - 1;
  let closestIdx = 0;
  let minDiff = Infinity;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const val = times[mid];

    if (val === null || isNaN(val)) {
      // Local linear search around mid to find the nearest valid value
      let resolvedMidVal: number | null = null;
      let resolvedMidIdx = mid;
      for (let offset = 1; offset <= Math.max(mid - low, high - mid); offset++) {
        if (mid - offset >= low && times[mid - offset] !== null && !isNaN(times[mid - offset]!)) {
          resolvedMidVal = times[mid - offset]!;
          resolvedMidIdx = mid - offset;
          break;
        }
        if (mid + offset <= high && times[mid + offset] !== null && !isNaN(times[mid + offset]!)) {
          resolvedMidVal = times[mid + offset]!;
          resolvedMidIdx = mid + offset;
          break;
        }
      }

      if (resolvedMidVal === null) break;

      const diff = Math.abs(resolvedMidVal - targetMs);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = resolvedMidIdx;
      }

      if (resolvedMidVal < targetMs) {
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    } else {
      const diff = Math.abs(val - targetMs);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = mid;
      }

      if (val === targetMs) {
        return mid;
      } else if (val < targetMs) {
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
  }

  return closestIdx;
}

/**
 * Finds the closest point index by SVG X coordinate using binary search O(log N).
 */
export function findClosestIndexByX(
  count: number,
  getXCoord: (idx: number) => number,
  targetX: number
): number {
  if (count <= 0) return 0;
  if (count === 1) return 0;

  let low = 0;
  let high = count - 1;
  let closestIdx = 0;
  let minDiff = Infinity;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const x = getXCoord(mid);
    const diff = Math.abs(x - targetX);

    if (diff < minDiff) {
      minDiff = diff;
      closestIdx = mid;
    }

    if (Math.abs(x - targetX) < 0.5) {
      return mid;
    } else if (x < targetX) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return closestIdx;
}

/**
 * Detects outages/offline gap intervals in point times.
 */
export function getOutages(
  pointTimes: (number | null)[],
  minTimeMs: number,
  _maxTimeMs?: number,
  gapThresholdMs: number = GAP_FLOOR_MS
): { start: number; end: number }[] {
  const list: { start: number; end: number }[] = [];
  if (!pointTimes || pointTimes.length === 0) return list;

  for (let i = 1; i < pointTimes.length; i++) {
    const a = pointTimes[i - 1];
    const b = pointTimes[i];
    if (a !== null && b !== null && b - a > gapThresholdMs) {
      list.push({ start: a, end: b });
    }
  }

  const firstValid = pointTimes.find((t): t is number => t !== null && typeof t === 'number' && !isNaN(t));
  if (firstValid !== undefined && firstValid - minTimeMs > gapThresholdMs) {
    list.unshift({ start: minTimeMs, end: firstValid });
  }

  return list;
}

/**
 * Builds SVG line path, filled area path, and isolated sample dots with offline gap handling.
 */
export function buildPathSegments(
  points: TelemetryHistoryPoint[],
  getValue: (p: TelemetryHistoryPoint) => number | null | undefined,
  getXCoord: (index: number) => number,
  getYCoord: (value: number) => number,
  plotBottomY: number,
  pointTimes: (number | null)[],
  gapThresholdMs: number = GAP_FLOOR_MS
): PathSegmentsResult {
  const segments: string[] = [];
  const areas: string[] = [];
  const isolated: { x: number; y: number }[] = [];
  let current: { x: number; y: number }[] = [];

  const flush = () => {
    if (current.length >= 2) {
      const seg = current.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ');
      segments.push(seg);
      areas.push(
        `${seg} L ${current[current.length - 1].x.toFixed(1)} ${plotBottomY.toFixed(1)} L ${current[0].x.toFixed(1)} ${plotBottomY.toFixed(1)} Z`
      );
    } else if (current.length === 1) {
      isolated.push({ x: current[0].x, y: current[0].y });
    }
    current = [];
  };

  let lastT: number | null = null;
  points.forEach((p, idx) => {
    const v = getValue(p);
    if (typeof v !== 'number' || isNaN(v)) {
      flush();
      return;
    }
    const t = pointTimes[idx] ?? null;
    if (t !== null && lastT !== null && t - lastT > gapThresholdMs) {
      flush();
    }
    current.push({ x: getXCoord(idx), y: getYCoord(v) });
    lastT = t;
  });
  flush();

  return {
    linePath: segments.join(' '),
    areaPath: areas.join(' '),
    isolated,
  };
}

export interface YScaleResult {
  minY: number;
  maxY: number;
  yTicks: number[];
}

export type PresetMetricType = 'temp' | 'humid' | 'pln' | 'genset' | 'battery';

export const PRESET_SCALES: Record<PresetMetricType, YScaleResult> = {
  temp: { minY: 15, maxY: 40, yTicks: [15, 20, 25, 30, 35, 40] },
  humid: { minY: 0, maxY: 100, yTicks: [0, 25, 50, 75, 100] },
  pln: { minY: 0, maxY: 260, yTicks: [0, 65, 130, 195, 260] },
  genset: { minY: 0, maxY: 260, yTicks: [0, 65, 130, 195, 260] },
  battery: { minY: 10, maxY: 15, yTicks: [10, 11, 12, 13, 14, 15] },
};

/**
 * Returns fixed preset scale bounds and ticks for standard telemetry metrics.
 */
export function getPresetScale(metric: 'temp' | 'humid' | 'pln' | 'genset' | 'battery'): YScaleResult {
  return PRESET_SCALES[metric];
}

/**
 * Computes Y-axis scale min, max, and ticks.
 */
export function computeYScale(
  values: number[],
  fallbackMin: number,
  fallbackMax: number,
  thresholds?: (number | null | undefined)[],
  paddingRatio: number = 0.1,
  minSpan: number = 6,
  clampMin?: number,
  clampMax?: number
): YScaleResult {
  let rawMin = values.length > 0 ? Math.min(...values) : fallbackMin;
  let rawMax = values.length > 0 ? Math.max(...values) : fallbackMax;

  if (thresholds) {
    thresholds.forEach((t) => {
      if (typeof t === 'number' && !isNaN(t)) {
        rawMin = Math.min(rawMin, t);
        rawMax = Math.max(rawMax, t);
      }
    });
  }

  const span = Math.max(rawMax - rawMin, minSpan);
  let minY = Math.floor(rawMin - span * paddingRatio);
  let maxY = Math.ceil(rawMax + span * paddingRatio);

  if (clampMin !== undefined) {
    minY = Math.max(clampMin, minY);
  }
  if (clampMax !== undefined) {
    maxY = Math.min(clampMax, maxY);
  }

  const yTicks = [0, 1, 2, 3, 4].map((i) => minY + (i / 4) * (maxY - minY));

  return { minY, maxY, yTicks };
}

