import { useState } from 'react';
import { TrendingUp, Activity } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { TelemetryHistoryPoint } from '../../types/api';
import {
  MultiPanelChartContainer,
  computeYScale,
  getPresetScale,
  type PanelConfig,
  type TimeRange,
} from './chart';

export interface HistoryChartProps {
  points: TelemetryHistoryPoint[];
  devType: string;
  timeRange: TimeRange;
  setTimeRange: (r: TimeRange) => void;
  warningThresholdVal?: number | null;
  criticalThresholdVal?: number | null;
  latestReading?: Record<string, any> | null;
  isFetching?: boolean;
  onRefresh?: () => void;
  dataUpdatedAt?: number | Date | string | null;
  lastUpdated?: number | Date | string | null;
}

export type TelemetryChartProps = HistoryChartProps;

export function HistoryChart({
  points,
  devType,
  timeRange,
  setTimeRange,
  warningThresholdVal,
  criticalThresholdVal,
  latestReading,
  isFetching,
}: HistoryChartProps) {
  // Auto-scale toggles for ATS
  const [autoScalePln, setAutoScalePln] = useState(true);
  const [autoScaleGenset, setAutoScaleGenset] = useState(true);
  const [autoScaleAki, setAutoScaleAki] = useState(true);

  // Auto-scale toggles for TS
  const [autoScaleTemp, setAutoScaleTemp] = useState(true);
  const [autoScaleHumid, setAutoScaleHumid] = useState(true);

  const isATS = devType === 'ATS';
  const isTS = devType === 'TS' || devType === 'AC' || devType === 'ACC';

  // Value arrays
  const tempValues = points.map((p) => p.temp).filter((v): v is number => typeof v === 'number');
  const humidValues = points.map((p) => p.humid).filter((v): v is number => typeof v === 'number');
  const plnValues = points.map((p) => p.pln).filter((v): v is number => typeof v === 'number');
  const gensetValues = points.map((p) => p.genset).filter((v): v is number => typeof v === 'number');
  const akiValues = points.map((p) => p.aki).filter((v): v is number => typeof v === 'number');

  // Aggregates for TS (combining latest reading with historical extremes/averages)
  const currentTemp =
    typeof latestReading?.temp === 'number'
      ? latestReading.temp
      : tempValues.length > 0
      ? tempValues[tempValues.length - 1]
      : null;
  const minTemp = tempValues.length > 0 ? Math.min(...tempValues) : null;
  const maxTemp = tempValues.length > 0 ? Math.max(...tempValues) : null;
  const avgTemp = tempValues.length > 0 ? tempValues.reduce((a, b) => a + b, 0) / tempValues.length : null;
  const currentHumid =
    typeof latestReading?.humid === 'number'
      ? latestReading.humid
      : humidValues.length > 0
      ? humidValues[humidValues.length - 1]
      : null;
  const minHumid = humidValues.length > 0 ? Math.min(...humidValues) : null;
  const maxHumid = humidValues.length > 0 ? Math.max(...humidValues) : null;
  const avgHumid = humidValues.length > 0 ? humidValues.reduce((a, b) => a + b, 0) / humidValues.length : null;

  // Aggregates for ATS
  const currentPln =
    typeof latestReading?.pln === 'number'
      ? latestReading.pln
      : plnValues.length > 0
      ? plnValues[plnValues.length - 1]
      : null;
  const avgPln = plnValues.length > 0 ? plnValues.reduce((a, b) => a + b, 0) / plnValues.length : null;
  const currentGenset =
    typeof latestReading?.genset === 'number'
      ? latestReading.genset
      : gensetValues.length > 0
      ? gensetValues[gensetValues.length - 1]
      : null;
  const maxGenset = gensetValues.length > 0 ? Math.max(...gensetValues) : null;
  const rawAki = latestReading?.aki ?? latestReading?.battery;
  const currentAki =
    typeof rawAki === 'number'
      ? rawAki
      : typeof rawAki === 'string' && !isNaN(parseFloat(rawAki))
      ? parseFloat(rawAki)
      : akiValues.length > 0
      ? akiValues[akiValues.length - 1]
      : null;
  const avgAki = akiValues.length > 0 ? akiValues.reduce((a, b) => a + b, 0) / akiValues.length : null;
  const currentState =
    (latestReading?.state || latestReading?.STATE) ??
    (points.length > 0 ? points[points.length - 1].state : null);

  const stateStr = String(currentState || 'STANDBY').toUpperCase();
  const isEmergency = stateStr.includes('EMERGENCY') || stateStr.includes('ALARM');
  const isPln = !isEmergency && (stateStr === 'PLN' || stateStr.includes('PLN'));
  const isGenset = !isEmergency && (stateStr === 'GENSET' || stateStr.includes('GENSET'));
  const stateColor = isEmergency
    ? 'text-red-400'
    : isPln
    ? 'text-emerald-400'
    : isGenset
    ? 'text-amber-400'
    : 'text-zinc-200';


  // Toggle handlers
  const handleToggleSeries = (seriesId: string) => {
    switch (seriesId) {
      case 'pln':
        setAutoScalePln((v) => !v);
        break;
      case 'genset':
        setAutoScaleGenset((v) => !v);
        break;
      case 'aki':
      case 'battery':
        setAutoScaleAki((v) => !v);
        break;
      case 'temp':
        setAutoScaleTemp((v) => !v);
        break;
      case 'humid':
        setAutoScaleHumid((v) => !v);
        break;
    }
  };

  // --- Panels Definition ---
  let panels: PanelConfig[] = [];

  if (isATS) {
    const warnBatteryVal = warningThresholdVal ?? 11.8;
    const critBatteryVal = criticalThresholdVal ?? 11.2;

    const plnScale = autoScalePln
      ? computeYScale(plnValues, 180, 240, [], 0.12, 20)
      : getPresetScale('pln');
    const gensetScale = autoScaleGenset
      ? computeYScale(gensetValues, 0, 240, [], 0.12, 30, 0)
      : getPresetScale('genset');
    const batteryScale = autoScaleAki
      ? computeYScale(akiValues, 10.0, 14.5, [], 0.12, 2.0)
      : getPresetScale('battery');

    panels = [
      {
        id: 'pln',
        title: 'Tegangan PLN (Grid)',
        unit: 'V',
        height: 160,
        minY: plnScale.minY,
        maxY: plnScale.maxY,
        yTicks: plnScale.yTicks,
        testId: 'ats-panel-pln',
        crosshairTestId: 'crosshair-pln',
        showTimeAxis: true,
        thresholds: [
          {
            value: 210,
            label: '210V Nominal',
            badgeLabel: '210V Nominal',
            color: '#10b981',
            testId: 'threshold-nominal',
          },
          {
            value: 190,
            label: '190V Batas Bawah',
            badgeLabel: '190V Batas Bawah',
            color: '#f59e0b',
            testId: 'threshold-low',
            type: 'warning',
          },
        ],
        series: [
          {
            id: 'pln',
            label: 'PLN Main',
            tooltipLabel: 'PLN:',
            color: '#10b981',
            unit: 'V',
            visible: true,
            active: autoScalePln,
            testId: 'path-pln',
            toggleTestId: 'toggle-pln',
            getValue: (p) => p.pln,
          },
        ],
      },
      {
        id: 'genset',
        title: 'Tegangan Genset (Generator)',
        unit: 'V',
        height: 160,
        minY: gensetScale.minY,
        maxY: gensetScale.maxY,
        yTicks: gensetScale.yTicks,
        testId: 'ats-panel-genset',
        crosshairTestId: 'crosshair-genset',
        showTimeAxis: true,
        thresholds: [
          {
            value: 210,
            label: '210V Siap Beban',
            badgeLabel: '210V Siap Beban',
            color: '#10b981',
            testId: 'threshold-genset-ready',
          },
        ],
        series: [
          {
            id: 'genset',
            label: 'Genset Voltage',
            tooltipLabel: 'Genset:',
            color: '#f59e0b',
            unit: 'V',
            visible: true,
            active: autoScaleGenset,
            testId: 'path-genset',
            toggleTestId: 'toggle-genset',
            getValue: (p) => p.genset,
          },
        ],
      },
      {
        id: 'battery',
        title: 'Tegangan DC Baterai Starter',
        unit: 'V',
        height: 160,
        minY: batteryScale.minY,
        maxY: batteryScale.maxY,
        yTicks: batteryScale.yTicks,
        testId: 'ats-panel-battery',
        crosshairTestId: 'crosshair-battery',
        showTimeAxis: true,
        thresholds: [
          {
            value: warnBatteryVal,
            label: `${warnBatteryVal}V Warning`,
            badgeLabel: `Warn (${warnBatteryVal}V)`,
            color: '#f59e0b',
            testId: 'threshold-warning',
            type: 'warning',
          },
          {
            value: critBatteryVal,
            label: `${critBatteryVal}V Critical`,
            badgeLabel: `Crit (${critBatteryVal}V)`,
            color: '#ef4444',
            testId: 'threshold-critical',
            type: 'critical',
          },
        ],
        series: [
          {
            id: 'aki',
            label: 'Battery AKI',
            tooltipLabel: 'Battery:',
            color: '#818cf8',
            unit: 'V',
            visible: true,
            active: autoScaleAki,
            testId: 'path-aki',
            toggleTestId: 'toggle-aki',
            getValue: (p) => p.aki,
          },
        ],
      },
    ];
  } else {
    // TS / AC Multi-Panel Configuration
    // Panel 1: Temperature with gradient fill & thresholds
    const tempScale = autoScaleTemp
      ? computeYScale(tempValues, 20, 35, [], 0.12, 6)
      : getPresetScale('temp');

    const tempThresholds = [];
    if (warningThresholdVal !== null && warningThresholdVal !== undefined) {
      tempThresholds.push({
        value: warningThresholdVal,
        label: `Warn (${warningThresholdVal}°C)`,
        badgeLabel: `Warn: ${warningThresholdVal}°C`,
        color: '#f59e0b',
        testId: 'threshold-warning',
        type: 'warning' as const,
      });
    }
    if (criticalThresholdVal !== null && criticalThresholdVal !== undefined) {
      tempThresholds.push({
        value: criticalThresholdVal,
        label: `Crit (${criticalThresholdVal}°C)`,
        badgeLabel: `Crit: ${criticalThresholdVal}°C`,
        color: '#ef4444',
        testId: 'threshold-critical',
        type: 'critical' as const,
      });
    }

    // Panel 2: Humidity with dedicated scale
    const humidScale = autoScaleHumid
      ? computeYScale(humidValues, 30, 80, [], 0.12, 10, 0, 100)
      : getPresetScale('humid');

    panels = [
      {
        id: 'temp',
        title: 'Temperature (°C)',
        unit: '°C',
        height: 180,
        minY: tempScale.minY,
        maxY: tempScale.maxY,
        yTicks: tempScale.yTicks,
        testId: 'ts-panel-temp',
        crosshairTestId: 'crosshair-ts',
        showTimeAxis: true,
        thresholds: tempThresholds,
        series: [
          {
            id: 'temp',
            label: 'Temperature (°C)',
            tooltipLabel: 'Temp:',
            color: '#6366f1',
            unit: '°C',
            isArea: true,
            gradientId: 'tempGradient',
            visible: true,
            active: autoScaleTemp,
            testId: 'path-temp',
            toggleTestId: 'toggle-temp',
            getValue: (p) => p.temp,
          },
        ],
      },
      {
        id: 'humid',
        title: 'Relative Humidity (%RH)',
        unit: '%',
        height: 160,
        minY: humidScale.minY,
        maxY: humidScale.maxY,
        yTicks: humidScale.yTicks,
        testId: 'ts-panel-humid',
        crosshairTestId: 'crosshair-humid',
        showTimeAxis: true,
        series: [
          {
            id: 'humid',
            label: 'Humidity (%)',
            tooltipLabel: 'Humidity:',
            color: '#10b981',
            unit: '%',
            visible: true,
            active: autoScaleHumid,
            testId: 'path-humid',
            toggleTestId: 'toggle-humid',
            getValue: (p) => p.humid,
          },
        ],
      },
    ];
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      {/* Header Controls: Title, Subtitle, and Time Range Selector Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            <span>Telemetry History & Trends</span>
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">Real-time telemetry stream across selected monitoring timeframe</p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          {isFetching && (
            <span className="text-[11px] text-zinc-500 flex items-center gap-1 font-mono">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Syncing
            </span>
          )}
          <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800">
            {(['6h', '24h', '7d', '30d'] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setTimeRange(r)}
                className={cn(
                  "px-3 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer",
                  timeRange === r ? "bg-indigo-600 text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
                )}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Summary Stat Cards */}
      {(points.length > 0 || latestReading) && (
        <>
          {isTS || (!isTS && !isATS) ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-500" /> Current Temp
                </span>
                <p className="text-lg font-mono font-bold text-zinc-100 mt-1">
                  {currentTemp !== null ? `${currentTemp.toFixed(1)}°C` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {currentHumid !== null ? `Humidity: ${currentHumid.toFixed(1)}%` : '—'}
                </span>
              </div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500">Min Temp</span>
                <p className="text-lg font-mono font-bold text-emerald-400 mt-1">
                  {minTemp !== null ? `${minTemp.toFixed(1)}°C` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {minHumid !== null ? `Min Hum: ${minHumid.toFixed(1)}%` : '—'}
                </span>
              </div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500">Max Temp</span>
                <p className="text-lg font-mono font-bold text-red-400 mt-1">
                  {maxTemp !== null ? `${maxTemp.toFixed(1)}°C` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {maxHumid !== null ? `Max Hum: ${maxHumid.toFixed(1)}%` : '—'}
                </span>
              </div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500">Average Temp</span>
                <p className="text-lg font-mono font-bold text-indigo-300 mt-1">
                  {avgTemp !== null ? `${avgTemp.toFixed(1)}°C` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {avgHumid !== null ? `Avg Hum: ${avgHumid.toFixed(1)}%` : '—'}
                </span>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" /> PLN Voltage
                </span>
                <p className="text-lg font-mono font-bold text-emerald-400 mt-1">
                  {currentPln !== null ? `${currentPln.toFixed(1)} V` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {avgPln !== null ? `Avg: ${avgPln.toFixed(1)}V` : '—'}
                </span>
              </div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-amber-400" /> Genset Voltage
                </span>
                <p className="text-lg font-mono font-bold text-amber-400 mt-1">
                  {currentGenset !== null ? `${currentGenset.toFixed(1)} V` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {maxGenset !== null ? `Max: ${maxGenset.toFixed(1)}V` : '—'}
                </span>
              </div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-indigo-400" /> Battery (AKI)
                </span>
                <p className="text-lg font-mono font-bold text-indigo-400 mt-1">
                  {currentAki !== null ? `${currentAki.toFixed(1)} V` : '—'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {avgAki !== null ? `Avg: ${avgAki.toFixed(1)}V` : '—'}
                </span>
              </div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60">
                <span className="text-[10px] uppercase font-semibold text-zinc-500">Controller State</span>
                <p className={cn("text-sm font-mono font-bold mt-1.5 truncate", stateColor)}>
                  {currentState || 'STANDBY'}
                </p>
                <span className="text-[10px] text-zinc-500">
                  {points.length > 0 ? `${points.length} samples` : 'Live reading'}
                </span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Main Multi-Panel Chart Area */}
      {points.length === 0 ? (
        <div className="h-56 flex flex-col items-center justify-center text-center p-6 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/40">
          <Activity className="h-8 w-8 text-zinc-600 mb-2 animate-pulse" />
          <p className="text-sm font-medium text-zinc-300">Collecting telemetry data...</p>
          <p className="text-xs text-zinc-500 mt-1">
            No historical telemetry records found for device within the {timeRange} window.
          </p>
        </div>
      ) : (
        <MultiPanelChartContainer
          panels={panels}
          points={points}
          timeRange={timeRange}
          devType={devType}
          onToggleSeries={handleToggleSeries}
          containerTestId={isATS ? 'ats-three-panel-container' : 'ts-single-panel-container'}
          tooltipTestId={isATS ? 'ats-hover-tooltip' : 'ts-hover-tooltip'}
        />
      )}
    </div>
  );
}

export default HistoryChart;
