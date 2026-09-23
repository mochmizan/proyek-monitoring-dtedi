import { describe, it, expect } from 'vitest';
import {
  getGapThresholdMinutes,
  getGapThresholdMs,
  getMedianIntervalMs,
  getOutages,
  formatAxisTime,
  formatTooltipTime,
  parseToDate,
  GAP_FLOOR_MS,
} from './chartUtils';
import { GAP_FLOOR_BY_TYPE_MIN, CADENCE_BY_TYPE, GAP_FLOOR_MIN } from './constants';

describe('chartUtils type-aware gap thresholds & cadence harmonization', () => {
  describe('constants verification', () => {
    it('defines expected GAP_FLOOR_BY_TYPE_MIN values', () => {
      expect(GAP_FLOOR_BY_TYPE_MIN).toEqual({
        ATS: 3,
        AC: 6,
        ACC: 6,
        TS: 15,
        DEFAULT: 3,
      });
      expect(GAP_FLOOR_MIN).toBe(5);
    });

    it('defines expected CADENCE_BY_TYPE metadata for UI presentation', () => {
      expect(CADENCE_BY_TYPE.TS).toEqual({ label: '5m RBE', intervalSec: 300 });
      expect(CADENCE_BY_TYPE.ATS).toEqual({ label: '1m RBE', intervalSec: 60 });
      expect(CADENCE_BY_TYPE.AC).toEqual({ label: '2m RBE', intervalSec: 120 });
      expect(CADENCE_BY_TYPE.ACC).toEqual({ label: '2m RBE', intervalSec: 120 });
      expect(CADENCE_BY_TYPE.DEFAULT).toEqual({ label: '1m RBE', intervalSec: 60 });
    });
  });

  describe('getGapThresholdMinutes', () => {
    it('asserts TS gets 15m gap floor on standard/unspecified ranges', () => {
      expect(getGapThresholdMinutes('TS')).toBe(15);
      expect(getGapThresholdMinutes('ts')).toBe(15);
      expect(getGapThresholdMinutes('TS', 360)).toBe(15);
    });

    it('asserts ATS gets 3m gap floor on standard/unspecified ranges', () => {
      expect(getGapThresholdMinutes('ATS')).toBe(3);
      expect(getGapThresholdMinutes('ats')).toBe(3);
      expect(getGapThresholdMinutes('ATS', 360)).toBe(3);
    });

    it('asserts AC and ACC get 6m gap floor on standard/unspecified ranges', () => {
      expect(getGapThresholdMinutes('AC')).toBe(6);
      expect(getGapThresholdMinutes('ac')).toBe(6);
      expect(getGapThresholdMinutes('ACC')).toBe(6);
      expect(getGapThresholdMinutes('acc')).toBe(6);
      expect(getGapThresholdMinutes('AC', 360)).toBe(6);
    });

    it('asserts default fallback for unknown/undefined types', () => {
      expect(getGapThresholdMinutes(undefined)).toBe(3);
      expect(getGapThresholdMinutes('')).toBe(3);
      expect(getGapThresholdMinutes('UNKNOWN_DEVICE')).toBe(3);
      expect(getGapThresholdMinutes('ROUTER')).toBe(3);
    });

    it('asserts dynamic gap scaling for longer historical ranges (24h, 7d, 30d)', () => {
      // 24h = 1440 minutes -> 1440 / 60 = 24 minutes
      expect(getGapThresholdMinutes('ATS', 1440)).toBe(24);
      expect(getGapThresholdMinutes('AC', 1440)).toBe(24);
      expect(getGapThresholdMinutes('TS', 1440)).toBe(24);

      // 7d = 10080 minutes -> 10080 / 60 = 168 minutes
      expect(getGapThresholdMinutes('ATS', 10080)).toBe(168);
      expect(getGapThresholdMinutes('AC', 10080)).toBe(168);
      expect(getGapThresholdMinutes('TS', 10080)).toBe(168);

      // 30d = 43200 minutes -> 43200 / 60 = 720 minutes (12h)
      expect(getGapThresholdMinutes('TS', 43200)).toBe(720);

      // Threshold monotonically increases with window size for any device
      const thresh6h = getGapThresholdMinutes('ATS', 360);
      const thresh24h = getGapThresholdMinutes('ATS', 1440);
      const thresh7d = getGapThresholdMinutes('ATS', 10080);
      const thresh30d = getGapThresholdMinutes('ATS', 43200);

      expect(thresh6h).toBe(3);
      expect(thresh24h).toBeGreaterThan(thresh6h);
      expect(thresh7d).toBeGreaterThan(thresh24h);
      expect(thresh30d).toBeGreaterThan(thresh7d);
    });

    it('preserves base floor when dynamic floor is smaller than device floor', () => {
      // For a 6h window (360 min), TS base floor is 15m, which dominates
      expect(getGapThresholdMinutes('TS', 360)).toBe(15);
      expect(getGapThresholdMinutes('AC', 360)).toBe(6);
      expect(getGapThresholdMinutes('ATS', 360)).toBe(3);
    });
  });

  describe('getGapThresholdMs', () => {
    it('returns ms threshold derived from getGapThresholdMinutes when points are sparse', () => {
      const sparsePoints = [1000, 2000]; // Less than 8 points -> median is null
      expect(getGapThresholdMs(sparsePoints, 'TS')).toBe(15 * 60 * 1000);
      expect(getGapThresholdMs(sparsePoints, 'ATS')).toBe(3 * 60 * 1000);
      expect(getGapThresholdMs(sparsePoints, 'AC')).toBe(6 * 60 * 1000);
      expect(getGapThresholdMs(sparsePoints)).toBe(3 * 60 * 1000);
    });

    it('adapts when point interval median is high but never drops below type floor', () => {
      // 10 points spaced by 30 seconds (30,000 ms)
      const fastPoints = Array.from({ length: 10 }, (_, i) => i * 30_000);
      // median * 10 = 300,000 ms (5 min)
      // TS floor = 15m (900,000 ms) -> floor dominates
      expect(getGapThresholdMs(fastPoints, 'TS')).toBe(15 * 60 * 1000);

      // ATS floor = 3m (180,000 ms) -> median * 10 (300,000 ms) dominates
      expect(getGapThresholdMs(fastPoints, 'ATS')).toBe(300_000);
    });
  });

  describe('getMedianIntervalMs & GAP_FLOOR_MS', () => {
    it('verifies GAP_FLOOR_MS equals 5 minutes', () => {
      expect(GAP_FLOOR_MS).toBe(5 * 60 * 1000);
    });

    it('returns null when valid intervals count is under 8 samples', () => {
      expect(getMedianIntervalMs([1000, 2000, 3000])).toBeNull();
    });

    it('computes correct median interval when 8 or more valid samples exist', () => {
      const times = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000];
      expect(getMedianIntervalMs(times)).toBe(1000);
    });
  });

  describe('Outage detection correctness with relaxed cadences', () => {
    it('does NOT flag TS 5m or 10m deadband gaps as outages with 15m floor', () => {
      const baseMs = 1_700_000_000_000;
      // Normal TS reporting: 5m heartbeat, then 10m deadband skipped heartbeat, then 5m heartbeat
      const pointTimes = [
        baseMs,
        baseMs + 5 * 60 * 1000,
        baseMs + 15 * 60 * 1000, // 10m gap after previous point
        baseMs + 20 * 60 * 1000, // 5m gap
      ];

      const thresholdMs = getGapThresholdMs(pointTimes, 'TS', 360);
      expect(thresholdMs).toBe(15 * 60 * 1000);

      const outages = getOutages(pointTimes, baseMs, thresholdMs);
      expect(outages).toHaveLength(0);
    });

    it('DOES flag TS outages when a gap exceeds the 15m floor', () => {
      const baseMs = 1_700_000_000_000;
      const pointTimes = [
        baseMs,
        baseMs + 5 * 60 * 1000,
        // 20-minute gap (dropout / lost power)
        baseMs + 25 * 60 * 1000,
        baseMs + 30 * 60 * 1000,
      ];

      const thresholdMs = getGapThresholdMs(pointTimes, 'TS', 360);
      const outages = getOutages(pointTimes, baseMs, thresholdMs);

      expect(outages).toHaveLength(1);
      expect(outages[0]).toEqual({
        start: baseMs + 5 * 60 * 1000,
        end: baseMs + 25 * 60 * 1000,
      });
    });

    it('asserts ATS 3m floor correctly permits 1m and 2m intervals, flagging 5m dropouts', () => {
      const baseMs = 1_700_000_000_000;
      const normalTimes = [
        baseMs,
        baseMs + 60_000,       // 1m
        baseMs + 180_000,      // 2m
        baseMs + 240_000,      // 1m
      ];

      const atsThresh = getGapThresholdMs(normalTimes, 'ATS', 360);
      expect(atsThresh).toBe(3 * 60 * 1000);
      expect(getOutages(normalTimes, baseMs, atsThresh)).toHaveLength(0);

      // With 5m outage
      const dropoutTimes = [
        baseMs,
        baseMs + 60_000,
        baseMs + 60_000 + 5 * 60 * 1000, // 5m gap
        baseMs + 60_000 + 6 * 60 * 1000,
      ];
      const outages = getOutages(dropoutTimes, baseMs, atsThresh);
      expect(outages).toHaveLength(1);
      expect(outages[0]).toEqual({
        start: baseMs + 60_000,
        end: baseMs + 60_000 + 5 * 60 * 1000,
      });
    });

    it('asserts AC 6m floor permits 2m and 4m intervals, flagging 8m dropouts', () => {
      const baseMs = 1_700_000_000_000;
      const acTimes = [
        baseMs,
        baseMs + 2 * 60 * 1000,
        baseMs + 6 * 60 * 1000, // 4m gap
        baseMs + 8 * 60 * 1000,
      ];
      const acThresh = getGapThresholdMs(acTimes, 'AC', 360);
      expect(acThresh).toBe(6 * 60 * 1000);
      expect(getOutages(acTimes, baseMs, acThresh)).toHaveLength(0);

      const acDropout = [
        baseMs,
        baseMs + 2 * 60 * 1000,
        baseMs + 10 * 60 * 1000, // 8m gap
      ];
      const outages = getOutages(acDropout, baseMs, acThresh);
      expect(outages).toHaveLength(1);
      expect(outages[0]).toEqual({
        start: baseMs + 2 * 60 * 1000,
        end: baseMs + 10 * 60 * 1000,
      });
    });
  });

  describe('formatAxisTime & formatTooltipTime & parseToDate', () => {
    it('correctly parses ISO strings with parseToDate', () => {
      const d = parseToDate('2026-09-17T12:00:00Z');
      expect(d).toBeInstanceOf(Date);
      expect(d.getTime()).toBe(new Date('2026-09-17T12:00:00Z').getTime());
    });

    it('formats axis time for 1h, 6h, and 24h ranges', () => {
      const formatted1h = formatAxisTime('2026-09-17T05:30:00Z', '1h');
      expect(formatted1h).toMatch(/\d{2}[.:]\d{2}/);

      const formatted = formatAxisTime('2026-09-17T05:30:00Z', '6h');
      // In Asia/Jakarta (UTC+7) with id-ID locale, 05:30 UTC is formatted as 12.30 or 12:30
      expect(formatted).toMatch(/\d{2}[.:]\d{2}/);
    });

    it('formats tooltip time with WIB suffix', () => {
      const formatted = formatTooltipTime('2026-09-17T05:30:00Z');
      expect(formatted).toContain('WIB');
    });

    it('returns raw string for invalid dates', () => {
      expect(formatAxisTime('invalid-date', '6h')).toBe('invalid-date');
      expect(formatTooltipTime('invalid-date')).toBe('invalid-date');
    });
  });
});
