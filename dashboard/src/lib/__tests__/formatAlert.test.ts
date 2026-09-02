import { describe, it, expect } from 'vitest';
import { formatAlertReading, formatAlertThreshold, isStatusOrPresenceAlert } from '../formatAlert';

describe('formatAlert Utility', () => {
  it('detects status and presence alerts correctly', () => {
    expect(isStatusOrPresenceAlert({ metric: 'connectivity', message: 'Device went OFFLINE' })).toBe(true);
    expect(isStatusOrPresenceAlert({ metric: 'presence', message: null })).toBe(true);
    expect(isStatusOrPresenceAlert({ metric: null, message: "Device 'TS-01' went OFFLINE" })).toBe(true);
    expect(isStatusOrPresenceAlert({ metric: 'temperature', message: 'High Temp Alert' })).toBe(false);
  });

  it('formats presence/connectivity alerts as dash rather than °C', () => {
    const offlineAlert = {
      metric: 'connectivity',
      message: "Device 'Node-01' went OFFLINE (No signal for > 25s).",
      value: 0.0,
      threshold: 1.0,
    };
    expect(formatAlertReading(offlineAlert)).toBe('—');
    expect(formatAlertThreshold(offlineAlert)).toBe('—');

    const legacyOfflineAlert = {
      metric: null,
      message: "Device 'ATS-01' in 'Server Room' went OFFLINE",
      value: 0,
      threshold: 1,
    };
    expect(formatAlertReading(legacyOfflineAlert)).toBe('—');
    expect(formatAlertThreshold(legacyOfflineAlert)).toBe('—');
  });

  it('formats battery voltage alerts with V unit', () => {
    const batteryAlert = {
      metric: 'battery',
      message: 'Starter Battery Undervoltage',
      value: 11.2,
      threshold: 11.8,
    };
    expect(formatAlertReading(batteryAlert)).toBe('11.20 V');
    expect(formatAlertThreshold(batteryAlert)).toBe('11.80 V');
  });

  it('formats temperature alerts with °C unit', () => {
    const tempAlert = {
      metric: 'temperature',
      message: 'Critical Temperature Exceeded',
      value: 33.5,
      threshold: 32,
    };
    expect(formatAlertReading(tempAlert)).toBe('33.5°C');
    expect(formatAlertThreshold(tempAlert)).toBe('32°C');
  });

  it('formats humidity alerts with % unit', () => {
    const humidAlert = {
      metric: 'humidity',
      message: 'High humidity',
      value: 85,
      threshold: 80,
    };
    expect(formatAlertReading(humidAlert)).toBe('85.0%');
    expect(formatAlertThreshold(humidAlert)).toBe('80.0%');
  });

  it('formats emergency alerts with Triggered and dash threshold', () => {
    const emergAlert = {
      metric: 'emergency',
      message: 'ATS Emergency Shutdown',
      value: 1,
      threshold: 0,
    };
    expect(formatAlertReading(emergAlert)).toBe('Triggered');
    expect(formatAlertThreshold(emergAlert)).toBe('—');
  });
});
