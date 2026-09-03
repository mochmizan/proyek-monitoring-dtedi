import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  parseToDate,
  formatWIBDateTime,
  formatWIBDate,
  formatWIBTime,
  computeStartTimeFromRange,
} from '../dateUtils';

describe('dateUtils', () => {
  describe('parseToDate', () => {
    it('returns invalid Date for null, undefined, or empty string', () => {
      expect(isNaN(parseToDate(null).getTime())).toBe(true);
      expect(isNaN(parseToDate(undefined).getTime())).toBe(true);
      expect(isNaN(parseToDate('').getTime())).toBe(true);
    });

    it('returns Date directly if Date instance is passed', () => {
      const d = new Date('2026-09-03T12:00:00Z');
      expect(parseToDate(d)).toBe(d);
    });

    it('handles numeric epoch timestamp', () => {
      const epoch = 1756900000000;
      expect(parseToDate(epoch).getTime()).toBe(epoch);
    });

    it('appends Z when timezone is omitted', () => {
      const withoutZ = '2026-09-03T12:00:00';
      const parsed = parseToDate(withoutZ);
      expect(parsed.toISOString()).toBe('2026-09-03T12:00:00.000Z');
    });

    it('preserves existing Z or offset', () => {
      const withZ = '2026-09-03T12:00:00Z';
      expect(parseToDate(withZ).toISOString()).toBe('2026-09-03T12:00:00.000Z');

      const withOffset = '2026-09-03T19:00:00+07:00';
      expect(parseToDate(withOffset).toISOString()).toBe('2026-09-03T12:00:00.000Z');
    });
  });

  describe('formatWIBDateTime', () => {
    it('returns dash for empty/invalid inputs', () => {
      expect(formatWIBDateTime(null)).toBe('—');
      expect(formatWIBDateTime(undefined)).toBe('—');
      expect(formatWIBDateTime('')).toBe('—');
      expect(formatWIBDateTime('not-a-date')).toBe('—');
    });

    it('formats UTC ISO timestamp to WIB (UTC+7)', () => {
      // 12:00 UTC is 19:00 WIB
      const res = formatWIBDateTime('2026-09-03T12:30:45Z');
      expect(res).toContain('19');
      expect(res).toContain('30');
      expect(res).toContain('45');
      expect(res).toContain('WIB');
      expect(res).toContain('2026');
    });
  });

  describe('formatWIBDate', () => {
    it('returns dash for empty/invalid inputs', () => {
      expect(formatWIBDate(null)).toBe('—');
      expect(formatWIBDate(undefined)).toBe('—');
    });

    it('formats date component in Asia/Jakarta', () => {
      const res = formatWIBDate('2026-09-03T12:00:00Z');
      expect(res).toContain('2026');
    });
  });

  describe('formatWIBTime', () => {
    it('returns empty string for empty/invalid inputs', () => {
      expect(formatWIBTime(null)).toBe('');
      expect(formatWIBTime(undefined)).toBe('');
      expect(formatWIBTime('')).toBe('');
      expect(formatWIBTime('invalid')).toBe('');
    });

    it('formats time to 24h WIB format', () => {
      const res = formatWIBTime('2026-09-03T05:15:30Z');
      expect(res).toBe('12:15:30 WIB');
    });
  });

  describe('computeStartTimeFromRange', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-09-03T12:00:00.000Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('computes correct ISO boundary for 6h', () => {
      expect(computeStartTimeFromRange('6h')).toBe('2026-09-03T06:00:00.000Z');
    });

    it('computes correct ISO boundary for 24h', () => {
      expect(computeStartTimeFromRange('24h')).toBe('2026-09-02T12:00:00.000Z');
    });

    it('computes correct ISO boundary for 7d', () => {
      expect(computeStartTimeFromRange('7d')).toBe('2026-08-27T12:00:00.000Z');
    });

    it('computes correct ISO boundary for 30d', () => {
      expect(computeStartTimeFromRange('30d')).toBe('2026-08-04T12:00:00.000Z');
    });

    it('returns undefined for all or unknown', () => {
      expect(computeStartTimeFromRange('all')).toBeUndefined();
      expect(computeStartTimeFromRange('')).toBeUndefined();
      expect(computeStartTimeFromRange(undefined)).toBeUndefined();
    });
  });
});
