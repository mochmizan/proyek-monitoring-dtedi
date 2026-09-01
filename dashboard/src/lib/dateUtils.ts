/**
 * Format a Date, ISO timestamp, or millisecond epoch into Indonesia Western Time (WIB / Asia/Jakarta).
 * Example output: "19:58:13 WIB"
 */
export function formatWIBTime(date: Date | string | number | null | undefined): string {
  if (date === null || date === undefined || date === '' || date === 0) return '';
  const d = typeof date === 'string' || typeof date === 'number' ? new Date(date) : date;
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
