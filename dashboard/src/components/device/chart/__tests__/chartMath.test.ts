import { describe, it, expect } from 'vitest';
import {
  timeToX,
  getY,
  findClosestPointIndex,
  findClosestIndexByX,
  getOutages,
  buildPathSegments,
  computeYScale,
  PRESET_SCALES,
  getPresetScale,
} from '../chartMath';
import type { TelemetryHistoryPoint } from '../../../../types/api';

describe('chartMath Unit Tests', () => {
  describe('timeToX', () => {
    it('maps minTime to paddingLeft and maxTime to paddingLeft + plotWidth', () => {
      const minTime = 1000;
      const maxTime = 2000;
      const plotWidth = 500;
      const paddingLeft = 50;

      expect(timeToX(1000, minTime, maxTime, plotWidth, paddingLeft)).toBe(50);
      expect(timeToX(2000, minTime, maxTime, plotWidth, paddingLeft)).toBe(550);
      expect(timeToX(1500, minTime, maxTime, plotWidth, paddingLeft)).toBe(300);
    });

    it('clamps values outside the min/max window', () => {
      const minTime = 1000;
      const maxTime = 2000;
      const plotWidth = 500;
      const paddingLeft = 50;

      expect(timeToX(500, minTime, maxTime, plotWidth, paddingLeft)).toBe(50);
      expect(timeToX(3000, minTime, maxTime, plotWidth, paddingLeft)).toBe(550);
    });

    it('handles identical min and max time without dividing by zero', () => {
      expect(timeToX(1000, 1000, 1000, 500, 50)).toBe(300);
    });
  });

  describe('getY', () => {
    it('maps minY to bottom of plot and maxY to top of plot', () => {
      const minY = 0;
      const maxY = 100;
      const plotHeight = 200;
      const paddingTop = 20;

      // In SVG: top is smaller Y, bottom is larger Y
      expect(getY(100, minY, maxY, plotHeight, paddingTop)).toBe(20); // Top
      expect(getY(0, minY, maxY, plotHeight, paddingTop)).toBe(220); // Bottom
      expect(getY(50, minY, maxY, plotHeight, paddingTop)).toBe(120); // Middle
    });

    it('handles minY === maxY edge case', () => {
      expect(getY(50, 50, 50, 200, 20)).toBe(120);
    });
  });

  describe('findClosestPointIndex', () => {
    it('finds exact matches and closest timestamps in O(log N)', () => {
      const times = [1000, 2000, 3000, 4000, 5000];

      expect(findClosestPointIndex(times, 1000)).toBe(0);
      expect(findClosestPointIndex(times, 3000)).toBe(2);
      expect(findClosestPointIndex(times, 5000)).toBe(4);
      expect(findClosestPointIndex(times, 2400)).toBe(1);
      expect(findClosestPointIndex(times, 2600)).toBe(2);
      expect(findClosestPointIndex(times, 500)).toBe(0);
      expect(findClosestPointIndex(times, 10000)).toBe(4);
    });

    it('handles empty and single-element arrays', () => {
      expect(findClosestPointIndex([], 1000)).toBe(0);
      expect(findClosestPointIndex([1000], 500)).toBe(0);
    });

    it('handles arrays with null or NaN entries gracefully', () => {
      const times = [1000, null, 3000, null, 5000];
      expect(findClosestPointIndex(times, 3100)).toBe(2);
    });
  });

  describe('findClosestIndexByX', () => {
    it('finds closest index given coordinate accessor function', () => {
      const count = 5;
      const getX = (idx: number) => 50 + idx * 100; // 50, 150, 250, 350, 450

      expect(findClosestIndexByX(count, getX, 50)).toBe(0);
      expect(findClosestIndexByX(count, getX, 240)).toBe(2);
      expect(findClosestIndexByX(count, getX, 400)).toBe(3);
    });
  });

  describe('getOutages', () => {
    it('detects offline gaps exceeding threshold', () => {
      const gapThresholdMs = 300_000; // 5 mins
      const times = [
        1000,
        1000 + 60_000,
        1000 + 120_000,
        // Gap of 10 mins
        1000 + 720_000,
        1000 + 780_000,
      ];

      const outages = getOutages(times, 1000, 1000 + 800_000, gapThresholdMs);
      expect(outages).toHaveLength(1);
      expect(outages[0]).toEqual({
        start: 1000 + 120_000,
        end: 1000 + 720_000,
      });
    });

    it('detects initial gap if first sample starts after minTimeMs + threshold', () => {
      const gapThresholdMs = 300_000;
      const minTimeMs = 0;
      const times = [600_000, 660_000];

      const outages = getOutages(times, minTimeMs, 700_000, gapThresholdMs);
      expect(outages.length).toBeGreaterThanOrEqual(1);
      expect(outages[0]).toEqual({
        start: 0,
        end: 600_000,
      });
    });
  });

  describe('buildPathSegments', () => {
    it('builds continuous line path and area path for valid points', () => {
      const points: TelemetryHistoryPoint[] = [
        { timestamp: '2026-09-01T10:00:00Z', temp: 20 },
        { timestamp: '2026-09-01T10:01:00Z', temp: 25 },
        { timestamp: '2026-09-01T10:02:00Z', temp: 30 },
      ];
      const pointTimes = [1000, 2000, 3000];
      const getXCoord = (i: number) => i * 100;
      const getYCoord = (v: number) => 100 - v;

      const result = buildPathSegments(
        points,
        (p) => p.temp,
        getXCoord,
        getYCoord,
        200,
        pointTimes,
        300_000
      );

      expect(result.linePath).toContain('M 0.0 80.0 L 100.0 75.0 L 200.0 70.0');
      expect(result.areaPath).toContain('M 0.0 80.0 L 100.0 75.0 L 200.0 70.0 L 200.0 200.0 L 0.0 200.0 Z');
      expect(result.isolated).toHaveLength(0);
    });

    it('identifies isolated points separated by gaps or missing data', () => {
      const points: TelemetryHistoryPoint[] = [
        { timestamp: '2026-09-01T10:00:00Z', temp: 20 },
        // Missing temp
        { timestamp: '2026-09-01T10:01:00Z', temp: undefined },
        // Isolated point
        { timestamp: '2026-09-01T10:02:00Z', temp: 30 },
        // Gap
        { timestamp: '2026-09-01T10:20:00Z', temp: 22 },
        { timestamp: '2026-09-01T10:21:00Z', temp: 24 },
      ];
      const pointTimes = [1000, 2000, 3000, 20000, 21000];
      const getXCoord = (i: number) => i * 100;
      const getYCoord = (v: number) => 100 - v;

      const result = buildPathSegments(
        points,
        (p) => p.temp,
        getXCoord,
        getYCoord,
        200,
        pointTimes,
        5000
      );

      // Point 0 was isolated by missing point 1, Point 2 was isolated by gap after point 2
      expect(result.isolated.length).toBeGreaterThan(0);
    });

    it('renders continuous line segments and 0 isolated points for downsampled points with adaptive gapThresholdMs', () => {
      // Downsampled points every 10 minutes (600,000 ms) for 7d/30d windows
      const intervalMs = 600_000;
      const baseTime = 1_700_000_000_000;
      const points: TelemetryHistoryPoint[] = Array.from({ length: 10 }, (_, i) => ({
        timestamp: new Date(baseTime + i * intervalMs).toISOString(),
        temp: 24 + (i % 3),
      }));
      const pointTimes = points.map((_, i) => baseTime + i * intervalMs);
      const getXCoord = (i: number) => i * 50;
      const getYCoord = (v: number) => 100 - v;

      // Adaptive gap threshold (e.g. median interval * 10 = 6,000,000 ms)
      const adaptiveGapThresholdMs = intervalMs * 10;

      const result = buildPathSegments(
        points,
        (p) => p.temp,
        getXCoord,
        getYCoord,
        200,
        pointTimes,
        adaptiveGapThresholdMs
      );

      expect(result.linePath.startsWith('M')).toBe(true);
      expect(result.isolated).toHaveLength(0);
      const lCount = (result.linePath.match(/ L /g) || []).length;
      expect(lCount).toBe(9);
    });
  });

  describe('computeYScale', () => {
    it('computes nice min/max bounds and 5 ticks including threshold values', () => {
      const values = [22, 25, 28];
      const result = computeYScale(values, 20, 35, [30, 35], 0.1, 6);

      expect(result.minY).toBeLessThanOrEqual(20);
      expect(result.maxY).toBeGreaterThanOrEqual(37);
      expect(result.yTicks).toHaveLength(5);
    });

    it('clamps min and max bounds when clampMin and clampMax are provided', () => {
      const values = [95, 98];
      const result = computeYScale(values, 30, 80, [], 0.12, 10, 0, 100);

      expect(result.minY).toBeGreaterThanOrEqual(0);
      expect(result.maxY).toBeLessThanOrEqual(100);
      expect(result.yTicks).toHaveLength(5);
    });
  });

  describe('PRESET_SCALES and getPresetScale', () => {
    it('provides correct fixed ranges and ticks for temp', () => {
      const scale = getPresetScale('temp');
      expect(scale).toEqual({
        minY: 15,
        maxY: 40,
        yTicks: [15, 20, 25, 30, 35, 40],
      });
      expect(PRESET_SCALES.temp).toEqual(scale);
    });

    it('provides correct fixed ranges and ticks for humid', () => {
      const scale = getPresetScale('humid');
      expect(scale).toEqual({
        minY: 0,
        maxY: 100,
        yTicks: [0, 25, 50, 75, 100],
      });
      expect(PRESET_SCALES.humid).toEqual(scale);
    });

    it('provides correct fixed ranges and ticks for pln', () => {
      const scale = getPresetScale('pln');
      expect(scale).toEqual({
        minY: 0,
        maxY: 260,
        yTicks: [0, 65, 130, 195, 260],
      });
      expect(PRESET_SCALES.pln).toEqual(scale);
    });

    it('provides correct fixed ranges and ticks for genset', () => {
      const scale = getPresetScale('genset');
      expect(scale).toEqual({
        minY: 0,
        maxY: 260,
        yTicks: [0, 65, 130, 195, 260],
      });
      expect(PRESET_SCALES.genset).toEqual(scale);
    });

    it('provides correct fixed ranges and ticks for battery', () => {
      const scale = getPresetScale('battery');
      expect(scale).toEqual({
        minY: 10,
        maxY: 15,
        yTicks: [10, 11, 12, 13, 14, 15],
      });
      expect(PRESET_SCALES.battery).toEqual(scale);
    });
  });
});

