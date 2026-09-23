/**
 * dateUtils.ts — Centralized date parsing, formatting, and time boundary utilities.
 * Ensures consistent Asia/Jakarta (WIB) representation across all dashboard components.
 */

const TZ_OFFSET_RE = /Z|[+-]\d{2}(?::?\d{2})?$/i;

/**
 * Safely parses any date input into a Date instance.
 * Appends defensive 'Z' if an ISO-like timestamp lacks a timezone indicator.
 */
export function parseToDate(val: string | number | Date | null | undefined): Date {
  if (val === null || val === undefined || val === '') {
    return new Date(NaN);
  }
  if (val instanceof Date) {
    return val;
  }
  if (typeof val === 'number') {
    return new Date(val);
  }
  if (typeof val === 'string') {
    let normalized = val.trim();
    if (!TZ_OFFSET_RE.test(normalized)) {
      normalized += 'Z';
    }
    return new Date(normalized);
  }
  return new Date(NaN);
}

/**
 * Format a timestamp into Indonesia Western Time (WIB) date and time.
 * Returns '—' if the timestamp is null, undefined, or invalid.
 */
export function formatWIBDateTime(date: string | number | Date | null | undefined): string {
  if (date === null || date === undefined || date === '' || date === 0) return '—';
  const d = parseToDate(date);
  if (isNaN(d.getTime())) return '—';

  return d.toLocaleString('id-ID', {
    timeZone: 'Asia/Jakarta',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }) + ' WIB';
}

/**
 * Format a timestamp into Indonesia Western Time (WIB) date only.
 * Returns '—' if the timestamp is null, undefined, or invalid.
 */
export function formatWIBDate(date: string | number | Date | null | undefined): string {
  if (date === null || date === undefined || date === '' || date === 0) return '—';
  const d = parseToDate(date);
  if (isNaN(d.getTime())) return '—';

  return d.toLocaleDateString('id-ID', {
    timeZone: 'Asia/Jakarta',
  });
}

/**
 * Format a timestamp into Indonesia Western Time (WIB) time only.
 * Example output: "19:58:13 WIB". Returns empty string if invalid.
 */
export function formatWIBTime(date: Date | string | number | null | undefined): string {
  if (date === null || date === undefined || date === '' || date === 0) return '';
  const d = parseToDate(date);
  if (isNaN(d.getTime())) return '';

  const timeStr = d.toLocaleTimeString('en-GB', {
    timeZone: 'Asia/Jakarta',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  return `${timeStr} WIB`;
}

/**
 * Converts a time range token ('1h', '6h', '24h', '7d', '30d') to an ISO UTC string boundary.
 * Returns undefined for 'all' or unrecognized range tokens.
 */
export function computeStartTimeFromRange(range?: string): string | undefined {
  if (!range) return undefined;
  const now = Date.now();
  switch (range) {
    case '1h':
      return new Date(now - 1 * 3600 * 1000).toISOString();
    case '6h':
      return new Date(now - 6 * 3600 * 1000).toISOString();
    case '24h':
      return new Date(now - 24 * 3600 * 1000).toISOString();
    case '7d':
      return new Date(now - 7 * 24 * 3600 * 1000).toISOString();
    case '30d':
      return new Date(now - 30 * 24 * 3600 * 1000).toISOString();
    default:
      return undefined;
  }
}
