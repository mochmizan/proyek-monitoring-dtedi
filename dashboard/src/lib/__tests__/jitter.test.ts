import { describe, expect, it } from 'vitest';
import { getJitteredInterval } from '../jitter';

describe('getJitteredInterval', () => {
  it('returns 0 for non-positive base intervals', () => {
    expect(getJitteredInterval(0)).toBe(0);
    expect(getJitteredInterval(-1000)).toBe(0);
  });

  it('bounds default jitter within +/- 15% range', () => {
    const baseMs = 6000;
    const min = Math.floor(baseMs * 0.85); // 5100
    const max = Math.ceil(baseMs * 1.15);  // 6900

    for (let i = 0; i < 200; i++) {
      const val = getJitteredInterval(baseMs);
      expect(Number.isInteger(val)).toBe(true);
      expect(val).toBeGreaterThanOrEqual(min);
      expect(val).toBeLessThanOrEqual(max);
    }
  });

  it('supports custom jitter factors', () => {
    const baseMs = 15000;
    const factor = 0.2;
    const min = Math.floor(baseMs * 0.8);  // 12000
    const max = Math.ceil(baseMs * 1.2);  // 18000

    for (let i = 0; i < 200; i++) {
      const val = getJitteredInterval(baseMs, factor);
      expect(val).toBeGreaterThanOrEqual(min);
      expect(val).toBeLessThanOrEqual(max);
    }
  });

  it('produces variable distribution (standard deviation > 0) across iterations', () => {
    const baseMs = 10000;
    const iterations = 1000;
    const values: number[] = [];

    for (let i = 0; i < iterations; i++) {
      values.push(getJitteredInterval(baseMs));
    }

    const mean = values.reduce((sum, v) => sum + v, 0) / iterations;
    const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / iterations;
    const stdDev = Math.sqrt(variance);

    expect(stdDev).toBeGreaterThan(0);
    // Values should be distributed roughly around baseMs
    expect(mean).toBeGreaterThan(baseMs * 0.95);
    expect(mean).toBeLessThan(baseMs * 1.05);
  });
});
