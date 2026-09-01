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

  describe('ATS Two-Panel Stacked History Chart', () => {
    it('renders two stacked panels for ATS (AC Voltage and DC Battery)', () => {
      const setTimeRange = vi.fn();
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={setTimeRange}
          warningThresholdVal={11.8}
          criticalThresholdVal={11.2}
        />
      );

      // Verify two-panel container
      expect(screen.getByTestId('ats-two-panel-container')).toBeInTheDocument();

      // Panel 1: AC Voltage
      expect(screen.getByTestId('ats-panel-ac')).toBeInTheDocument();
      expect(screen.getByText('AC Grid & Genset Voltage (V)')).toBeInTheDocument();

      // Panel 2: DC Battery Voltage
      expect(screen.getByTestId('ats-panel-battery')).toBeInTheDocument();
      expect(screen.getByText('Starter Battery Voltage (AKI)')).toBeInTheDocument();

      // Verify battery threshold lines
      expect(screen.getByTestId('threshold-warning')).toBeInTheDocument();
      expect(screen.getByText('11.8V Warning')).toBeInTheDocument();
      expect(screen.getByTestId('threshold-critical')).toBeInTheDocument();
      expect(screen.getByText('11.2V Critical')).toBeInTheDocument();

      // Verify ATS summary cards
      expect(screen.getByText('PLN Voltage')).toBeInTheDocument();
      expect(screen.getByText('Genset Voltage')).toBeInTheDocument();
      expect(screen.getByText('Battery (AKI)')).toBeInTheDocument();
      expect(screen.getByText('Controller State')).toBeInTheDocument();
    });

    it('toggles ATS series visibility on legend pill click', () => {
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

      // Toggle PLN Off
      const plnBtn = screen.getByTestId('toggle-pln');
      expect(plnBtn).toHaveAttribute('aria-pressed', 'true');
      fireEvent.click(plnBtn);
      expect(plnBtn).toHaveAttribute('aria-pressed', 'false');
      expect(screen.queryByTestId('path-pln')).not.toBeInTheDocument();

      // Toggle Genset Off
      const gensetBtn = screen.getByTestId('toggle-genset');
      expect(gensetBtn).toHaveAttribute('aria-pressed', 'true');
      fireEvent.click(gensetBtn);
      expect(gensetBtn).toHaveAttribute('aria-pressed', 'false');
      expect(screen.queryByTestId('path-genset')).not.toBeInTheDocument();

      // Toggle Battery AKI Off
      const akiBtn = screen.getByTestId('toggle-aki');
      expect(akiBtn).toHaveAttribute('aria-pressed', 'true');
      fireEvent.click(akiBtn);
      expect(akiBtn).toHaveAttribute('aria-pressed', 'false');
      expect(screen.queryByTestId('path-aki')).not.toBeInTheDocument();

      // Re-enable PLN
      fireEvent.click(plnBtn);
      expect(plnBtn).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByTestId('path-pln')).toBeInTheDocument();
    });

    it('synchronizes hover crosshairs and unified tooltip across both panels', () => {
      const { container } = render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
        />
      );

      const acSvg = container.querySelector('[data-testid="ats-panel-ac"] svg');
      expect(acSvg).toBeInTheDocument();

      // Simulate mousemove on Panel 1 SVG
      fireEvent.mouseMove(acSvg!, { clientX: 200, clientY: 50 });

      // Check crosshair on both AC panel and Battery panel
      expect(screen.getByTestId('crosshair-ac')).toBeInTheDocument();
      expect(screen.getByTestId('crosshair-dc')).toBeInTheDocument();

      // Check unified floating tooltip content
      const tooltip = screen.getByTestId('ats-hover-tooltip');
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveTextContent('PLN:');
      expect(tooltip).toHaveTextContent('Battery:');
      expect(tooltip).toHaveTextContent('WIB');

      // Simulate mouseleave -> crosshairs and tooltip hidden
      fireEvent.mouseLeave(acSvg!);
      expect(screen.queryByTestId('crosshair-ac')).not.toBeInTheDocument();
      expect(screen.queryByTestId('crosshair-dc')).not.toBeInTheDocument();
      expect(screen.queryByTestId('ats-hover-tooltip')).not.toBeInTheDocument();
    });
  });

  describe('TS / Non-ATS Single-Panel History Chart', () => {
    it('renders single panel for TS with temperature & humidity', () => {
      render(
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
      expect(screen.getByTestId('path-temp')).toBeInTheDocument();
      expect(screen.getByTestId('path-humid')).toBeInTheDocument();
      expect(screen.getByText('Warn (30°C)')).toBeInTheDocument();
      expect(screen.getByText('Crit (35°C)')).toBeInTheDocument();
    });

    it('toggles TS series visibility on legend pill click', () => {
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

      // Toggle Temperature Off
      fireEvent.click(tempBtn);
      expect(screen.queryByTestId('path-temp')).not.toBeInTheDocument();
      expect(screen.getByTestId('path-humid')).toBeInTheDocument();

      // Toggle Humidity Off
      fireEvent.click(humidBtn);
      expect(screen.queryByTestId('path-humid')).not.toBeInTheDocument();
    });
  });

  describe('Header Controls, Range Tabs, Last Updated & Refresh', () => {
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

      const btn6h = screen.getByRole('button', { name: '6h' });
      const btn7d = screen.getByRole('button', { name: '7d' });

      fireEvent.click(btn6h);
      expect(setTimeRange).toHaveBeenCalledWith('6h');

      fireEvent.click(btn7d);
      expect(setTimeRange).toHaveBeenCalledWith('7d');
    });

    it('displays Last Updated indicator when dataUpdatedAt is provided', () => {
      const updatedAt = new Date('2026-09-01T12:30:45Z').getTime();
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
          dataUpdatedAt={updatedAt}
        />
      );

      const lastUpdated = screen.getByTestId('history-last-updated');
      expect(lastUpdated).toBeInTheDocument();
      expect(lastUpdated).toHaveTextContent('Last updated:');
      expect(lastUpdated).toHaveTextContent('WIB');
    });

    it('calls onRefresh when Refresh button is clicked', () => {
      const onRefresh = vi.fn();
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
          onRefresh={onRefresh}
          isFetching={false}
        />
      );

      const refreshBtn = screen.getByTestId('history-refresh-btn');
      expect(refreshBtn).not.toBeDisabled();
      fireEvent.click(refreshBtn);
      expect(onRefresh).toHaveBeenCalledTimes(1);
    });

    it('disables Refresh button when isFetching is true', () => {
      const onRefresh = vi.fn();
      render(
        <HistoryChart
          points={atsSamplePoints}
          devType="ATS"
          timeRange="24h"
          setTimeRange={vi.fn()}
          onRefresh={onRefresh}
          isFetching={true}
        />
      );

      const refreshBtn = screen.getByTestId('history-refresh-btn');
      expect(refreshBtn).toBeDisabled();
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
  });
});
