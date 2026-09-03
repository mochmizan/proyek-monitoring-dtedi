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
});
