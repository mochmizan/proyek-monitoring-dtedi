import type { AlertResponse } from '../types/api';

/**
 * Checks if the alert event represents a presence, connectivity, or system status alert
 * that has no scalar measurement unit.
 */
export function isStatusOrPresenceAlert(alert: Pick<AlertResponse, 'metric' | 'message'>): boolean {
  const metric = (alert.metric || '').toLowerCase();
  const msg = (alert.message || '').toLowerCase();

  if (
    metric === 'connectivity' ||
    metric === 'presence' ||
    metric === 'status' ||
    metric === 'connection' ||
    metric === 'system'
  ) {
    return true;
  }

  if (
    msg.includes('offline') ||
    msg.includes('online') ||
    msg.includes('disconnected') ||
    msg.includes('connected') ||
    msg.includes('no signal')
  ) {
    return true;
  }

  return false;
}

export function formatAlertReading(alert: Pick<AlertResponse, 'metric' | 'message' | 'value'>): string {
  if (isStatusOrPresenceAlert(alert)) {
    return '—';
  }

  const metric = (alert.metric || '').toLowerCase();
  if (metric === 'emergency') {
    return 'Triggered';
  }

  if (alert.value === null || alert.value === undefined) {
    return '—';
  }

  const num = Number(alert.value);

  if (metric === 'battery' || metric === 'voltage' || metric === 'pln' || metric === 'genset' || metric === 'aki') {
    return isNaN(num) ? `${alert.value} V` : `${num.toFixed(2)} V`;
  }

  if (metric === 'humidity' || metric === 'humid') {
    return isNaN(num) ? `${alert.value}%` : `${num.toFixed(1)}%`;
  }

  const msg = (alert.message || '').toLowerCase();
  if (msg.includes('volt') || msg.includes('battery') || msg.includes('aki')) {
    return isNaN(num) ? `${alert.value} V` : `${num.toFixed(2)} V`;
  }

  if (msg.includes('humid') || msg.includes('kelembaban')) {
    return isNaN(num) ? `${alert.value}%` : `${num.toFixed(1)}%`;
  }

  if (metric === 'temperature' || metric === 'temp' || msg.includes('temp') || msg.includes('suhu')) {
    return `${alert.value}°C`;
  }

  if (metric && metric !== 'temperature' && metric !== 'temp') {
    return `${alert.value}`;
  }

  return `${alert.value}°C`;
}

export function formatAlertThreshold(alert: Pick<AlertResponse, 'metric' | 'message' | 'threshold'>): string {
  if (isStatusOrPresenceAlert(alert)) {
    return '—';
  }

  const metric = (alert.metric || '').toLowerCase();
  if (metric === 'emergency') {
    return '—';
  }

  if (alert.threshold === null || alert.threshold === undefined) {
    return '—';
  }

  const num = Number(alert.threshold);

  if (metric === 'battery' || metric === 'voltage' || metric === 'pln' || metric === 'genset' || metric === 'aki') {
    return isNaN(num) ? `${alert.threshold} V` : `${num.toFixed(2)} V`;
  }

  if (metric === 'humidity' || metric === 'humid') {
    return isNaN(num) ? `${alert.threshold}%` : `${num.toFixed(1)}%`;
  }

  const msg = (alert.message || '').toLowerCase();
  if (msg.includes('volt') || msg.includes('battery') || msg.includes('aki')) {
    return isNaN(num) ? `${alert.threshold} V` : `${num.toFixed(2)} V`;
  }

  if (msg.includes('humid') || msg.includes('kelembaban')) {
    return isNaN(num) ? `${alert.threshold}%` : `${num.toFixed(1)}%`;
  }

  if (metric === 'temperature' || metric === 'temp' || msg.includes('temp') || msg.includes('suhu')) {
    return `${alert.threshold}°C`;
  }

  if (metric && metric !== 'temperature' && metric !== 'temp') {
    return `${alert.threshold}`;
  }

  return `${alert.threshold}°C`;
}
