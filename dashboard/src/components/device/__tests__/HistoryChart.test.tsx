import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { HistoryChart } from '../HistoryChart';
import type { TelemetryHistoryPoint } from '../../../types/api';

describe('HistoryChart Component', () => {
  const atsSamplePoints: TelemetryHistoryPoint[] = [
    {
      timestamp: '2026-09-01T10:00:00Z',
      pln: 220.5,
      genset: 0.0,
      aki: 12.8,
      state: 'PLN_ONLINE',
    },
    {
      timestamp: '2026-09-01T10:02:00Z',
      pln: 219.8,
      genset: 0.0,
      aki: 12.7,
      state: 'PLN_ONLINE',
    },
    {
      timestamp: '2026-09-01T10:04:00Z',
      pln: 221.0,
      genset: 0.0,
      aki: 12.6,
      state: 'STANDBY',
    },
  ];

  const tsSamplePoints: TelemetryHistoryPoint[] = [
    {
      timestamp: '2026-09-01T10:00:00Z',
      temp: 24.5,
      humid: 55.0,
    },
    {
      timestamp: '2026-09-01T10:02:00Z',
      temp: 25.0,
      humid: 54.2,
    },
  ];

  describe('ATS Three-Panel Stacked History Chart', () => {
    it('renders three stacked panels for ATS (PLN, Genset, and DC Battery)', () => {
      const setTimeRange = vi.fn();
      const { container } = render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={setTimeRange}
          warningThresholdVal={11.8}
          criticalThresholdVal={11.2}
        />
      );

      // Verify three-panel container
      expect(screen.getByTestId('ats-three-panel-container')).toBeInTheDocument();

      // Panel 1: PLN Voltage
      expect(screen.getByTestId('ats-panel-pln')).toBeInTheDocument();
      expect(screen.getByText('Tegangan PLN (Grid)')).toBeInTheDocument();
      expect(screen.getByText('210V Nominal')).toBeInTheDocument();
      expect(screen.getByText('190V Batas Bawah')).toBeInTheDocument();

      // Panel 2: Genset Voltage
      expect(screen.getByTestId('ats-panel-genset')).toBeInTheDocument();
      expect(screen.getByText('Tegangan Genset (Generator)')).toBeInTheDocument();
      expect(screen.getByText('210V Siap Beban')).toBeInTheDocument();

      // Panel 3: DC Battery Voltage
      expect(screen.getByTestId('ats-panel-battery')).toBeInTheDocument();
      expect(screen.getByText('Tegangan DC Baterai Starter')).toBeInTheDocument();

      // Verify time axis is enabled on all 3 panels
      expect(container.querySelectorAll('.panel-time-axis')).toHaveLength(3);

      // Verify battery threshold pills in header
      expect(screen.getByText('Warn (11.8V)')).toBeInTheDocument();
      expect(screen.getByText('Crit (11.2V)')).toBeInTheDocument();

      // Verify ATS summary cards
      expect(screen.getByText('PLN Voltage')).toBeInTheDocument();
      expect(screen.getByText('Genset Voltage')).toBeInTheDocument();
      expect(screen.getByText('Battery (AKI)')).toBeInTheDocument();
      expect(screen.getByText('Controller State')).toBeInTheDocument();
    });

    it('renders threshold guide lines on canvas when voltage values cross or approach thresholds', () => {
      const atsThresholdPoints: TelemetryHistoryPoint[] = [
        {
          timestamp: '2026-09-01T10:00:00Z',
          pln: 185.0,
          genset: 205.0,
          aki: 11.0,
          state: 'GENSET_ONLINE',
        },
        {
          timestamp: '2026-09-01T10:02:00Z',
          pln: 195.0,
          genset: 215.0,
          aki: 12.0,
          state: 'GENSET_ONLINE',
        },
      ];

      render(
        <HistoryChart
          points={atsThresholdPoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
          warningThresholdVal={11.8}
          criticalThresholdVal={11.2}
        />
      );

      // In range: PLN 185-195V puts 190V threshold in canvas domain
      expect(screen.getByTestId('threshold-low')).toBeInTheDocument();
      // Genset 205-215V puts 210V threshold in canvas domain
      expect(screen.getByTestId('threshold-genset-ready')).toBeInTheDocument();
      // AKI 11.0-12.0V puts 11.8V and 11.2V thresholds in canvas domain
      expect(screen.getByTestId('threshold-warning')).toBeInTheDocument();
      expect(screen.getByTestId('threshold-critical')).toBeInTheDocument();
    });

    it('toggles ATS auto-scale on panel header button click', () => {
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
        />
      );

      // Initially, PLN, Genset, and AKI paths are present
      expect(screen.getByTestId('path-pln')).toBeInTheDocument();
      expect(screen.getByTestId('path-genset')).toBeInTheDocument();
      expect(screen.getByTestId('path-aki')).toBeInTheDocument();

      // Toggle PLN Auto Scale
      const plnBtn = screen.getByTestId('toggle-pln');
      expect(plnBtn).toHaveAttribute('aria-pressed', 'true');
      expect(plnBtn).toHaveTextContent('✓ Auto Scale');
      fireEvent.click(plnBtn);
      expect(plnBtn).toHaveAttribute('aria-pressed', 'false');
      expect(plnBtn).toHaveTextContent('Auto Scale');
      // Path remains visible
      expect(screen.getByTestId('path-pln')).toBeInTheDocument();

      // Toggle Genset Auto Scale
      const gensetBtn = screen.getByTestId('toggle-genset');
      expect(gensetBtn).toHaveAttribute('aria-pressed', 'true');
      expect(gensetBtn).toHaveTextContent('✓ Auto Scale');
      fireEvent.click(gensetBtn);
      expect(gensetBtn).toHaveAttribute('aria-pressed', 'false');
      expect(gensetBtn).toHaveTextContent('Auto Scale');
      expect(screen.getByTestId('path-genset')).toBeInTheDocument();

      // Toggle Battery AKI Auto Scale
      const akiBtn = screen.getByTestId('toggle-aki');
      expect(akiBtn).toHaveAttribute('aria-pressed', 'true');
      expect(akiBtn).toHaveTextContent('✓ Auto Scale');
      fireEvent.click(akiBtn);
      expect(akiBtn).toHaveAttribute('aria-pressed', 'false');
      expect(akiBtn).toHaveTextContent('Auto Scale');
      expect(screen.getByTestId('path-aki')).toBeInTheDocument();

      // Re-enable PLN Auto Scale
      fireEvent.click(plnBtn);
      expect(plnBtn).toHaveAttribute('aria-pressed', 'true');
      expect(plnBtn).toHaveTextContent('✓ Auto Scale');
      expect(screen.getByTestId('path-pln')).toBeInTheDocument();
    });

    it('synchronizes hover crosshairs and unified tooltip across all 3 panels', () => {
      const { container } = render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
        />
      );

      const plnSvg = container.querySelector('[data-testid="ats-panel-pln"] svg');
      expect(plnSvg).toBeInTheDocument();

      // Simulate mousemove on Panel 1 SVG
      fireEvent.mouseMove(plnSvg!, { clientX: 200, clientY: 50 });

      // Check crosshair on PLN, Genset, and Battery panels
      expect(screen.getByTestId('crosshair-pln')).toBeInTheDocument();
      expect(screen.getByTestId('crosshair-genset')).toBeInTheDocument();
      expect(screen.getByTestId('crosshair-battery')).toBeInTheDocument();

      // Check unified floating tooltip content
      const tooltip = screen.getByTestId('ats-hover-tooltip');
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveTextContent('PLN:');
      expect(tooltip).toHaveTextContent('Genset:');
      expect(tooltip).toHaveTextContent('Battery:');
      expect(tooltip).toHaveTextContent('WIB');

      // Simulate mouseleave -> crosshairs and tooltip hidden
      fireEvent.mouseLeave(plnSvg!);
      expect(screen.queryByTestId('crosshair-pln')).not.toBeInTheDocument();
      expect(screen.queryByTestId('crosshair-genset')).not.toBeInTheDocument();
      expect(screen.queryByTestId('crosshair-battery')).not.toBeInTheDocument();
      expect(screen.queryByTestId('ats-hover-tooltip')).not.toBeInTheDocument();
    });
  });

  describe('TS / Non-ATS Multi-Panel History Chart', () => {
    it('renders stacked panels for TS with temperature & humidity', () => {
      const { container } = render(
        <HistoryChart
          points={tsSamplePoints}
          devType="TS"
          timeRange="6h"
          setTimeRange={vi.fn()}
          warningThresholdVal={30}
          criticalThresholdVal={35}
        />
      );

      expect(screen.getByTestId('ts-single-panel-container')).toBeInTheDocument();
      expect(screen.getByTestId('ts-panel-temp')).toBeInTheDocument();
      expect(screen.getByTestId('ts-panel-humid')).toBeInTheDocument();
      expect(screen.getByTestId('path-temp')).toBeInTheDocument();
      expect(screen.getByTestId('path-humid')).toBeInTheDocument();
      expect(screen.getByText('Warn: 30°C')).toBeInTheDocument();
      expect(screen.getByText('Crit: 35°C')).toBeInTheDocument();

      // Verify time axis is enabled on all TS panels
      expect(container.querySelectorAll('.panel-time-axis')).toHaveLength(2);
    });

    it('renders threshold guide lines on canvas when temperature approaches or crosses thresholds', () => {
      const tsHighPoints: TelemetryHistoryPoint[] = [
        {
          timestamp: '2026-09-01T10:00:00Z',
          temp: 29.0,
          humid: 55.0,
        },
        {
          timestamp: '2026-09-01T10:02:00Z',
          temp: 36.0,
          humid: 54.2,
        },
      ];

      render(
        <HistoryChart
          points={tsHighPoints}
          devType="TS"
          timeRange="6h"
          setTimeRange={vi.fn()}
          warningThresholdVal={30}
          criticalThresholdVal={35}
        />
      );

      expect(screen.getByTestId('threshold-warning')).toBeInTheDocument();
      expect(screen.getByTestId('threshold-critical')).toBeInTheDocument();
    });

    it('toggles TS auto-scale on panel header button click', () => {
      render(
        <HistoryChart
          points={tsSamplePoints}
          devType="TS"
          timeRange="6h"
          setTimeRange={vi.fn()}
        />
      );

      const tempBtn = screen.getByTestId('toggle-temp');
      const humidBtn = screen.getByTestId('toggle-humid');

      expect(screen.getByTestId('path-temp')).toBeInTheDocument();
      expect(screen.getByTestId('path-humid')).toBeInTheDocument();

      // Initially both have auto scale active
      expect(tempBtn).toHaveAttribute('aria-pressed', 'true');
      expect(tempBtn).toHaveTextContent('✓ Auto Scale');
      expect(humidBtn).toHaveAttribute('aria-pressed', 'true');
      expect(humidBtn).toHaveTextContent('✓ Auto Scale');

      // Toggle Temperature Auto Scale Off
      fireEvent.click(tempBtn);
      expect(tempBtn).toHaveAttribute('aria-pressed', 'false');
      expect(tempBtn).toHaveTextContent('Auto Scale');
      // Paths remain visible
      expect(screen.getByTestId('path-temp')).toBeInTheDocument();
      expect(screen.getByTestId('path-humid')).toBeInTheDocument();

      // Toggle Humidity Auto Scale Off
      fireEvent.click(humidBtn);
      expect(humidBtn).toHaveAttribute('aria-pressed', 'false');
      expect(humidBtn).toHaveTextContent('Auto Scale');
      expect(screen.getByTestId('path-humid')).toBeInTheDocument();
    });

    it('synchronizes hover crosshairs and unified tooltip across TS panels', () => {
      const { container } = render(
        <HistoryChart
          points={tsSamplePoints}
          devType="TS"
          timeRange="6h"
          setTimeRange={vi.fn()}
        />
      );

      const tempSvg = container.querySelector('[data-testid="ts-panel-temp"] svg');
      expect(tempSvg).toBeInTheDocument();

      // Simulate mousemove on Temperature SVG
      fireEvent.mouseMove(tempSvg!, { clientX: 200, clientY: 50 });

      // Check crosshair on both panels
      expect(screen.getByTestId('crosshair-ts')).toBeInTheDocument();
      expect(screen.getByTestId('crosshair-humid')).toBeInTheDocument();

      // Check unified floating tooltip content
      const tooltip = screen.getByTestId('ts-hover-tooltip');
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveTextContent('Temp:');
      expect(tooltip).toHaveTextContent('Humidity:');
      expect(tooltip).toHaveTextContent('WIB');

      // Simulate mouseleave
      fireEvent.mouseLeave(tempSvg!);
      expect(screen.queryByTestId('crosshair-ts')).not.toBeInTheDocument();
      expect(screen.queryByTestId('crosshair-humid')).not.toBeInTheDocument();
      expect(screen.queryByTestId('ts-hover-tooltip')).not.toBeInTheDocument();
    });
  });

  describe('Header Controls & Range Tabs', () => {
    it('handles time range tab clicks', () => {
      const setTimeRange = vi.fn();
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={setTimeRange}
        />
      );

      const btn1h = screen.getByRole('button', { name: '1h' });
      const btn6h = screen.getByRole('button', { name: '6h' });
      const btn7d = screen.getByRole('button', { name: '7d' });

      fireEvent.click(btn1h);
      expect(setTimeRange).toHaveBeenCalledWith('1h');

      fireEvent.click(btn6h);
      expect(setTimeRange).toHaveBeenCalledWith('6h');

      fireEvent.click(btn7d);
      expect(setTimeRange).toHaveBeenCalledWith('7d');
    });
  });

  describe('Empty State & Gap Outages', () => {
    it('renders collecting telemetry placeholder when points array is empty', () => {
      render(
        <HistoryChart
          points={[]}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
        />
      );

      expect(screen.getByText('Collecting telemetry data...')).toBeInTheDocument();
      expect(screen.getByText(/No historical telemetry records found for device/)).toBeInTheDocument();
    });

    it('renders outage shading rect for data with large gap (> 5m)', () => {
      const pointsWithGap: TelemetryHistoryPoint[] = [
        {
          timestamp: '2026-09-01T10:00:00Z',
          pln: 220,
          genset: 0,
          aki: 12.5,
        },
        // 30 min gap
        {
          timestamp: '2026-09-01T10:30:00Z',
          pln: 221,
          genset: 0,
          aki: 12.4,
        },
      ];

      const { container } = render(
        <HistoryChart
          points={pointsWithGap}
          devType="ATS"
          timeRange="6h"
          setTimeRange={vi.fn()}
        />
      );

      // Outage titles should be in the SVG elements
      const outageTitles = container.querySelectorAll('title');
      const outageText = Array.from(outageTitles).map((t) => t.textContent);
      expect(outageText.some((text) => text?.includes('hub offline - no samples'))).toBe(true);
    });

    it('renders ATS summary cards with latestReading live metrics even when points are empty', () => {
      const latestReading = {
        pln: 224.2,
        genset: 0.0,
        aki: 12.7,
        state: 'PLN_ONLINE',
      };

      render(
        <HistoryChart
          points={[]}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
          latestReading={latestReading}
        />
      );

      expect(screen.getByText('PLN Voltage')).toBeInTheDocument();
      expect(screen.getByText('224.2 V')).toBeInTheDocument();
      expect(screen.getByText('Genset Voltage')).toBeInTheDocument();
      expect(screen.getByText('0.0 V')).toBeInTheDocument();
      expect(screen.getByText('Battery (AKI)')).toBeInTheDocument();
      expect(screen.getByText('12.7 V')).toBeInTheDocument();
      expect(screen.getByText('Controller State')).toBeInTheDocument();
      expect(screen.getByText('PLN_ONLINE')).toBeInTheDocument();
      expect(screen.getByText('Live reading')).toBeInTheDocument();
    });

    it('displays syncing indicator when isFetching is true', () => {
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
          isFetching={true}
        />
      );

      expect(screen.getByText('Syncing')).toBeInTheDocument();
    });
  });
});

