import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RoomCard, RoomCardSkeleton } from '../RoomCard';
import type { RoomResponse, DeviceResponse, RoomSparklinePoint } from '../../types/api';

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, to, className }: any) => (
    <a href={typeof to === 'string' ? to : '#'} className={className}>
      {children}
    </a>
  ),
}));

const baseRoom: RoomResponse = {
  id: 'room-test-1',
  name: 'Main Server Room',
  device_count: 2,
  created_at: '2026-09-01T00:00:00Z',
};

describe('RoomCard Component', () => {
  describe('SECTION A: TS / AC sensors', () => {
    it('computes Math.max across multiple TS and AC device readings', () => {
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ts-1',
          dev_name: 'TS Sensor 1',
          dev_type: 'TS',
          is_active: true,
          latest_reading: { temp: 24.2, humid: 55.0 },
        },
        {
          dev_id: 'dev-ac-1',
          dev_name: 'AC Unit 1',
          dev_type: 'AC',
          is_active: true,
          latest_reading: { temp: 28.6, humid: 62.0 },
        },
      ];

      const sparklinePoints: RoomSparklinePoint[] = [
        { timestamp: '2026-09-03T10:00:00Z', temp: 26.0, humid: 55.0 },
        { timestamp: '2026-09-03T11:00:00Z', temp: 28.6, humid: 62.0 },
      ];

      render(
        <RoomCard
          room={baseRoom}
          devices={devices}
          sparklinePoints={sparklinePoints}
        />
      );

      // Math.max(24.2, 28.6) = 28.6
      expect(screen.getByText('28.6')).toBeInTheDocument();
      // Math.max(55.0, 62.0) = 62
      expect(screen.getByText('62%')).toBeInTheDocument();
      // Sparkline SVG rendered
      expect(document.querySelector('svg polyline')).toBeInTheDocument();
    });

    it('renders placeholder dashes when TS device has null readings', () => {
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ts-null',
          dev_name: 'TS Offline',
          dev_type: 'TS',
          is_active: true,
          latest_reading: { temp: null, humid: null },
        },
      ];

      render(<RoomCard room={baseRoom} devices={devices} />);

      expect(screen.getByText('—')).toBeInTheDocument();
      expect(screen.getByText('Humidity —')).toBeInTheDocument();
    });
  });

  describe('SECTION B: ATS power monitoring', () => {
    it('renders ATS PLN state badge and omits normal voltage (> 11.8V)', () => {
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ats-1',
          dev_name: 'ATS Unit 1',
          dev_type: 'ATS',
          is_active: true,
          latest_reading: { state: 'PLN', battery: 12.6 },
        },
      ];

      render(<RoomCard room={baseRoom} devices={devices} />);

      expect(screen.getByText('ATS Power')).toBeInTheDocument();
      expect(screen.getByText('PLN')).toBeInTheDocument();
      // Normal battery voltage (> 11.8V) must be omitted
      expect(screen.queryByText(/Aki/i)).not.toBeInTheDocument();
    });

    it('displays warning badge when battery is <= 11.8V and critical badge when <= 11.2V', () => {
      const devicesWarning: DeviceResponse[] = [
        {
          dev_id: 'dev-ats-warn',
          dev_type: 'ATS',
          is_active: true,
          latest_reading: { state: 'PLN', aki: 11.5 },
        },
      ];

      const { rerender } = render(<RoomCard room={baseRoom} devices={devicesWarning} />);
      expect(screen.getByText('Aki 11.5V')).toBeInTheDocument();

      const devicesCritical: DeviceResponse[] = [
        {
          dev_id: 'dev-ats-crit',
          dev_type: 'ATS',
          is_active: true,
          latest_reading: { state: 'EMERGENCY_GENSET', battery: 11.0 },
        },
      ];

      rerender(<RoomCard room={baseRoom} devices={devicesCritical} />);
      expect(screen.getByText('EMERGENCY_GENSET')).toBeInTheDocument();
      expect(screen.getByText('Aki 11.0V')).toBeInTheDocument();
    });

    it('does not display device connection status ONLINE as ATS power state when latest_reading is missing', () => {
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ats-missing-telemetry',
          dev_name: 'ATS Unit 2',
          dev_type: 'ATS',
          status: 'online',
          is_active: true,
          latest_reading: null,
        },
      ];

      render(<RoomCard room={baseRoom} devices={devices} />);

      expect(screen.getByText('ATS Power')).toBeInTheDocument();
      expect(screen.queryByText('ONLINE')).not.toBeInTheDocument();
      expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    });

    it('renders ATS PLN_ON state with emerald PLN badge styling', () => {
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ats-pln-on',
          dev_name: 'ATS Unit PLN',
          dev_type: 'ATS',
          is_active: true,
          latest_reading: { state: 'PLN_ON', aki: 12.5 },
        },
      ];

      render(<RoomCard room={baseRoom} devices={devices} />);

      const badge = screen.getByText('PLN_ON');
      expect(badge).toBeInTheDocument();
      expect(badge.className).toContain('text-emerald-400');
    });
  });

  describe('SECTION A + B: Stacked layout', () => {
    it('renders both Section A and Section B when both sensor types are present', () => {
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ts-1',
          dev_type: 'TS',
          is_active: true,
          latest_reading: { temp: 22.5, humid: 48.0 },
        },
        {
          dev_id: 'dev-ats-1',
          dev_type: 'ATS',
          is_active: true,
          latest_reading: { state: 'PLN', battery: 11.4 },
        },
      ];

      render(<RoomCard room={baseRoom} devices={devices} />);

      // Section A elements
      expect(screen.getByText('22.5')).toBeInTheDocument();
      expect(screen.getByText('48%')).toBeInTheDocument();

      // Section B elements
      expect(screen.getByText('ATS Power')).toBeInTheDocument();
      expect(screen.getByText('PLN')).toBeInTheDocument();
      expect(screen.getByText('Aki 11.4V')).toBeInTheDocument();

      // Placeholder not rendered
      expect(screen.queryByText('No sensors paired')).not.toBeInTheDocument();
    });
  });

  describe('SECTION C: Fallback placeholder', () => {
    it('renders "No sensors paired" when no TS, AC, or ATS sensors exist', () => {
      render(<RoomCard room={baseRoom} devices={[]} />);
      expect(screen.getByText('No sensors paired')).toBeInTheDocument();
      expect(screen.queryByText('ATS Power')).not.toBeInTheDocument();
      expect(screen.queryByText(/°C/i)).not.toBeInTheDocument();
    });
  });

  describe('RoomCardSkeleton', () => {
    it('renders skeleton markup with pulse effect', () => {
      const { container } = render(<RoomCardSkeleton />);
      expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
    });
  });

  describe('Timestamp parsing and Freshness Prioritization', () => {
    it('normalizes naive timestamp without timezone as UTC and renders correct freshness', () => {
      vi.useFakeTimers();
      const now = Date.UTC(2026, 8, 3, 12, 10, 0);
      vi.setSystemTime(now);

      // Naive ISO string without Z or offset (10s before now in UTC)
      const naiveTs = '2026-09-03T12:09:50';
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ts-1',
          dev_type: 'TS',
          is_active: true,
          latest_reading: {
            temp: 22.0,
            humid: 50.0,
            timestamp: naiveTs,
          },
        },
      ];

      render(<RoomCard room={baseRoom} devices={devices} />);

      // Must be parsed as UTC (10s ago), not local browser time
      expect(screen.getByText('Updated 10s ago')).toBeInTheDocument();
      vi.useRealTimers();
    });

    it('prioritizes device telemetry timestamp over sparkline bucket start timestamp', () => {
      vi.useFakeTimers();
      const now = Date.UTC(2026, 8, 3, 12, 10, 0);
      vi.setSystemTime(now);

      // Device reading is fresh (10s ago)
      const freshDeviceTs = new Date(now - 10000).toISOString();
      const devices: DeviceResponse[] = [
        {
          dev_id: 'dev-ts-1',
          dev_type: 'TS',
          is_active: true,
          latest_reading: {
            temp: 22.0,
            humid: 50.0,
            timestamp: freshDeviceTs,
          },
        },
      ];

      // Sparkline bucket is from 15 minutes ago
      const bucketStartTs = new Date(now - 15 * 60 * 1000).toISOString();
      const sparklinePoints: RoomSparklinePoint[] = [
        { timestamp: bucketStartTs, temp: 22.0, humid: 50.0 },
      ];

      render(
        <RoomCard
          room={baseRoom}
          devices={devices}
          sparklinePoints={sparklinePoints}
        />
      );

      // Freshness should reflect 10s ago, NOT 15m ago (900s ago)
      expect(screen.getByText('Updated 10s ago')).toBeInTheDocument();
      vi.useRealTimers();
    });

    it('falls back to sparkline timestamp when devices have no readings or timestamps', () => {
      vi.useFakeTimers();
      const now = Date.UTC(2026, 8, 3, 12, 10, 0);
      vi.setSystemTime(now);

      const bucketStartTs = new Date(now - 30000).toISOString();
      const sparklinePoints: RoomSparklinePoint[] = [
        { timestamp: bucketStartTs, temp: 22.0, humid: 50.0 },
      ];

      render(
        <RoomCard
          room={baseRoom}
          devices={[]}
          sparklinePoints={sparklinePoints}
        />
      );

      expect(screen.getByText('Updated 30s ago')).toBeInTheDocument();
      vi.useRealTimers();
    });
  });
});
