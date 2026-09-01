import { useState } from 'react';
import { TrendingUp, Activity, RefreshCw } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { TelemetryHistoryPoint } from '../../types/api';
import { parseToDate, formatAxisTime, formatTooltipTime, getGapThresholdMs, getOutages } from '../../lib/chartUtils';
import { formatWIBTime } from '../../lib/dateUtils';

export interface TelemetryChartProps {
  points: TelemetryHistoryPoint[];
  devType: string;
  timeRange: '6h' | '24h' | '7d' | '30d';
  setTimeRange: (r: '6h' | '24h' | '7d' | '30d') => void;
  warningThresholdVal?: number | null;
  criticalThresholdVal?: number | null;
  isFetching?: boolean;
  onRefresh?: () => void;
  dataUpdatedAt?: number | Date | string | null;
}

interface SeriesPaths {
  linePath: string;
  areaPath: string;
  isolated: { x: number; y: number }[];
}

export function HistoryChart({
  points,
  devType,
  timeRange,
  setTimeRange,
  warningThresholdVal,
  criticalThresholdVal,
  isFetching = false,
  onRefresh,
  dataUpdatedAt,
}: TelemetryChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  // Series visibility toggles for ATS
  const [showPln, setShowPln] = useState(true);
  const [showGenset, setShowGenset] = useState(true);
  const [showAki, setShowAki] = useState(true);

  // Series visibility toggles for TS
  const [showTemp, setShowTemp] = useState(true);
  const [showHumid, setShowHumid] = useState(true);

  const isATS = devType === 'ATS';
  const isTS = devType === 'TS' || devType === 'AC' || devType === 'ACC';

  // Value arrays
  const tempValues = points.map((p) => p.temp).filter((v): v is number => typeof v === 'number');
  const humidValues = points.map((p) => p.humid).filter((v): v is number => typeof v === 'number');
  const plnValues = points.map((p) => p.pln).filter((v): v is number => typeof v === 'number');
  const gensetValues = points.map((p) => p.genset).filter((v): v is number => typeof v === 'number');
  const akiValues = points.map((p) => p.aki).filter((v): v is number => typeof v === 'number');

  // Aggregates for TS
  const currentTemp = tempValues.length > 0 ? tempValues[tempValues.length - 1] : null;
  const minTemp = tempValues.length > 0 ? Math.min(...tempValues) : null;
  const maxTemp = tempValues.length > 0 ? Math.max(...tempValues) : null;
  const avgTemp = tempValues.length > 0 ? tempValues.reduce((a, b) => a + b, 0) / tempValues.length : null;
  const currentHumid = humidValues.length > 0 ? humidValues[humidValues.length - 1] : null;
  const minHumid = humidValues.length > 0 ? Math.min(...humidValues) : null;
  const maxHumid = humidValues.length > 0 ? Math.max(...humidValues) : null;
  const avgHumid = humidValues.length > 0 ? humidValues.reduce((a, b) => a + b, 0) / humidValues.length : null;

  // Aggregates for ATS
  const currentPln = plnValues.length > 0 ? plnValues[plnValues.length - 1] : null;
  const avgPln = plnValues.length > 0 ? plnValues.reduce((a, b) => a + b, 0) / plnValues.length : null;
  const currentGenset = gensetValues.length > 0 ? gensetValues[gensetValues.length - 1] : null;
  const maxGenset = gensetValues.length > 0 ? Math.max(...gensetValues) : null;
  const currentAki = akiValues.length > 0 ? akiValues[akiValues.length - 1] : null;
  const avgAki = akiValues.length > 0 ? akiValues.reduce((a, b) => a + b, 0) / akiValues.length : null;
  const currentState = points.length > 0 ? points[points.length - 1].state : null;

  // Time calculations (Synchronized X-axis across all panels)
  const width = 800;
  const padding = { top: 20, right: 35, bottom: 25, left: 45 };
  const plotWidth = width - padding.left - padding.right;

  const windowHours = timeRange === '6h' ? 6 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 * 24 : 30 * 24;
  const windowMs = windowHours * 3600 * 1000;
  const latestPointTime = points.length > 0 && points[points.length - 1].timestamp
    ? parseToDate(points[points.length - 1].timestamp).getTime()
    : Date.now();
  const maxTimeMs = !isNaN(latestPointTime) ? latestPointTime : Date.now();
  const minTimeMs = maxTimeMs - windowMs;

  const timeToX = (tMs: number) => {
    const ratio = Math.max(0, Math.min(1, (tMs - minTimeMs) / (maxTimeMs - minTimeMs)));
    return padding.left + ratio * plotWidth;
  };

  const getX = (index: number) => {
    const pt = points[index];
    const t = pt && pt.timestamp ? parseToDate(pt.timestamp).getTime() : NaN;
    if (isNaN(t)) {
      if (points.length <= 1) return padding.left + plotWidth / 2;
      return padding.left + (index / (points.length - 1)) * plotWidth;
    }
    return timeToX(t);
  };

  const pointTimes: (number | null)[] = points.map((p) => {
    const t = p.timestamp ? parseToDate(p.timestamp).getTime() : NaN;
    return isNaN(t) ? null : t;
  });
  const gapThresholdMs = getGapThresholdMs(pointTimes);
  const outages = getOutages(pointTimes, minTimeMs, gapThresholdMs);
  const xTimeTicks = [0, 1, 2, 3, 4].map((i) => new Date(minTimeMs + (i / 4) * (maxTimeMs - minTimeMs)));

  // Reusable Line Builder with gap detection
  const createLineBuilder = (getYCoord: (v: number) => number, plotBottomY: number) => {
    return (getValue: (p: TelemetryHistoryPoint) => number | null | undefined): SeriesPaths => {
      const segments: string[] = [];
      const areas: string[] = [];
      const isolated: { x: number; y: number }[] = [];
      let current: { x: number; y: number }[] = [];

      const flush = () => {
        if (current.length >= 2) {
          const seg = current.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ');
          segments.push(seg);
          areas.push(
            `${seg} L ${current[current.length - 1].x.toFixed(1)} ${plotBottomY.toFixed(1)} L ${current[0].x.toFixed(1)} ${plotBottomY.toFixed(1)} Z`
          );
        } else if (current.length === 1) {
          isolated.push({ x: current[0].x, y: current[0].y });
        }
        current = [];
      };

      let lastT: number | null = null;
      points.forEach((p, idx) => {
        const v = getValue(p);
        if (typeof v !== 'number' || isNaN(v)) {
          flush();
          return;
        }
        const t = pointTimes[idx];
        if (t !== null && lastT !== null && t - lastT > gapThresholdMs) {
          flush();
        }
        current.push({ x: getX(idx), y: getYCoord(v) });
        lastT = t;
      });
      flush();
      return { linePath: segments.join(' '), areaPath: areas.join(' '), isolated };
    };
  };

  // --- TS Layout Calculations ---
  const height_TS = 260;
  const padding_TS = { top: 25, right: 35, bottom: 35, left: 45 };
  const plotHeight_TS = height_TS - padding_TS.top - padding_TS.bottom;

  let rawMinY_TS = tempValues.length > 0 ? Math.min(...tempValues) : 20;
  let rawMaxY_TS = tempValues.length > 0 ? Math.max(...tempValues) : 35;
  if (humidValues.length > 0) {
    rawMinY_TS = Math.min(rawMinY_TS, ...humidValues);
    rawMaxY_TS = Math.max(rawMaxY_TS, ...humidValues);
  }
  if (warningThresholdVal !== null && warningThresholdVal !== undefined) {
    rawMaxY_TS = Math.max(rawMaxY_TS, warningThresholdVal + 2);
    rawMinY_TS = Math.min(rawMinY_TS, warningThresholdVal - 2);
  }
  if (criticalThresholdVal !== null && criticalThresholdVal !== undefined) {
    rawMaxY_TS = Math.max(rawMaxY_TS, criticalThresholdVal + 2);
    rawMinY_TS = Math.min(rawMinY_TS, criticalThresholdVal - 2);
  }
  const span_TS = Math.max(rawMaxY_TS - rawMinY_TS, 6);
  const minY_TS = Math.floor(rawMinY_TS - span_TS * 0.1);
  const maxY_TS = Math.ceil(rawMaxY_TS + span_TS * 0.1);

  const getY_TS = (val: number) => {
    if (maxY_TS === minY_TS) return padding_TS.top + plotHeight_TS / 2;
    return padding_TS.top + plotHeight_TS - ((val - minY_TS) / (maxY_TS - minY_TS)) * plotHeight_TS;
  };
  const yTicks_TS = [0, 1, 2, 3, 4].map((i) => minY_TS + (i / 4) * (maxY_TS - minY_TS));
  const lineBuilder_TS = createLineBuilder(getY_TS, padding_TS.top + plotHeight_TS);
  const tempLine = lineBuilder_TS((p) => p.temp);
  const humidLine = lineBuilder_TS((p) => p.humid);

  // --- ATS Panel 1: AC Voltage (PLN & Genset) Calculations ---
  const height_AC = 200;
  const padding_AC = { top: 20, right: 35, bottom: 25, left: 45 };
  const plotHeight_AC = height_AC - padding_AC.top - padding_AC.bottom;

  const allAcValues = [...plnValues, ...gensetValues];
  const rawMaxAC = allAcValues.length > 0 ? Math.max(...allAcValues, 250) : 250;
  const minY_AC = 0;
  const maxY_AC = Math.max(260, Math.ceil(rawMaxAC * 1.05));

  const getY_AC = (val: number) => {
    if (maxY_AC === minY_AC) return padding_AC.top + plotHeight_AC / 2;
    return padding_AC.top + plotHeight_AC - ((val - minY_AC) / (maxY_AC - minY_AC)) * plotHeight_AC;
  };
  const yTicks_AC = [0, 1, 2, 3, 4].map((i) => minY_AC + (i / 4) * (maxY_AC - minY_AC));
  const lineBuilder_AC = createLineBuilder(getY_AC, padding_AC.top + plotHeight_AC);
  const plnLine = lineBuilder_AC((p) => p.pln);
  const gensetLine = lineBuilder_AC((p) => p.genset);

  // --- ATS Panel 2: DC Battery Voltage (AKI) Calculations ---
  const height_DC = 160;
  const padding_DC = { top: 20, right: 35, bottom: 25, left: 45 };
  const plotHeight_DC = height_DC - padding_DC.top - padding_DC.bottom;

  const rawMinAki = akiValues.length > 0 ? Math.min(...akiValues) : 11.0;
  const rawMaxAki = akiValues.length > 0 ? Math.max(...akiValues) : 14.0;
  const minY_DC = Math.min(9.5, Math.floor((rawMinAki - 0.5) * 10) / 10);
  const maxY_DC = Math.max(15.0, Math.ceil((rawMaxAki + 0.5) * 10) / 10);

  const getY_DC = (val: number) => {
    if (maxY_DC === minY_DC) return padding_DC.top + plotHeight_DC / 2;
    return padding_DC.top + plotHeight_DC - ((val - minY_DC) / (maxY_DC - minY_DC)) * plotHeight_DC;
  };
  const yTicks_DC = [0, 1, 2, 3, 4].map((i) => minY_DC + (i / 4) * (maxY_DC - minY_DC));
  const lineBuilder_DC = createLineBuilder(getY_DC, padding_DC.top + plotHeight_DC);
  const akiLine = lineBuilder_DC((p) => p.aki);

  // ATS DC Battery threshold values
  const warnBatteryVal = warningThresholdVal ?? 11.8;
  const critBatteryVal = criticalThresholdVal ?? 11.2;

  // Shared hover handlers
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (points.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const svgX = (mouseX / rect.width) * width;
    let closestIdx = 0;
    let minDiff = Infinity;
    points.forEach((_, idx) => {
      const x = getX(idx);
      const diff = Math.abs(x - svgX);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = idx;
      }
    });
    setHoverIndex(closestIdx);
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  const formattedUpdatedAt = dataUpdatedAt ? formatWIBTime(dataUpdatedAt) : '';

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      {/* Header Controls: Title, Last Updated, Refresh, and Range Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            <span>Telemetry History & Trends</span>
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">Real-time telemetry stream across selected monitoring timeframe</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 self-start sm:self-auto">
          {formattedUpdatedAt && (
            <span className="text-[11px] text-zinc-400 font-mono" data-testid="history-last-updated">
              Last updated: {formattedUpdatedAt}
            </span>
          )}

          {onRefresh && (
            <button
              type="button"
              onClick={() => onRefresh()}
              disabled={isFetching}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border transition-all cursor-pointer",
                "bg-zinc-950 hover:bg-zinc-800 border-zinc-800 text-zinc-300 disabled:opacity-50"
              )}
              aria-label="Refresh telemetry data"
              data-testid="history-refresh-btn"
            >
              <RefreshCw className={cn("h-3 w-3 text-indigo-400", isFetching && "animate-spin")} />
              <span>Refresh</span>
            </button>
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
      {points.length > 0 && (
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
                <p className="text-sm font-mono font-bold text-zinc-200 mt-1.5 truncate">
                  {currentState || 'STANDBY'}
                </p>
                <span className="text-[10px] text-zinc-500">{points.length} samples</span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Main Chart Area */}
      {points.length === 0 ? (
        <div className="h-56 flex flex-col items-center justify-center text-center p-6 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/40">
          <Activity className="h-8 w-8 text-zinc-600 mb-2 animate-pulse" />
          <p className="text-sm font-medium text-zinc-300">Collecting telemetry data...</p>
          <p className="text-xs text-zinc-500 mt-1">
            No historical telemetry records found for device within the {timeRange} window.
          </p>
        </div>
      ) : isATS ? (
        /* ATS Two-Panel Stacked History Chart */
        <div className="relative select-none space-y-6" data-testid="ats-two-panel-container">
          {/* Synchronized Hover Floating Tooltip */}
          {hoverIndex !== null && points[hoverIndex] && (
            <div
              className="absolute pointer-events-none z-30 bg-zinc-900/95 backdrop-blur-md border border-zinc-700 shadow-xl rounded-lg p-3 text-xs text-zinc-200"
              style={{
                left: `${(getX(hoverIndex) / width) * 100}%`,
                top: '0px',
                transform: hoverIndex > points.length / 2 ? 'translateX(-105%)' : 'translateX(5%)',
              }}
              data-testid="ats-hover-tooltip"
            >
              <div className="text-[10px] text-zinc-400 font-mono pb-1 border-b border-zinc-800 mb-2 flex items-center gap-1.5">
                <Activity className="h-3 w-3 text-indigo-400" />
                <span>{formatTooltipTime(points[hoverIndex].timestamp)}</span>
              </div>
              <div className="space-y-1.5 min-w-[140px]">
                {showPln && typeof points[hoverIndex].pln === 'number' && (
                  <div className="flex items-center justify-between gap-4 font-mono">
                    <span className="text-emerald-400 font-sans text-[11px] flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full bg-emerald-400" /> PLN:
                    </span>
                    <span className="font-bold text-zinc-100">{points[hoverIndex].pln?.toFixed(1)} V</span>
                  </div>
                )}
                {showGenset && typeof points[hoverIndex].genset === 'number' && (
                  <div className="flex items-center justify-between gap-4 font-mono">
                    <span className="text-amber-400 font-sans text-[11px] flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full bg-amber-400" /> Genset:
                    </span>
                    <span className="font-bold text-zinc-100">{points[hoverIndex].genset?.toFixed(1)} V</span>
                  </div>
                )}
                {showAki && typeof points[hoverIndex].aki === 'number' && (
                  <div className="flex items-center justify-between gap-4 font-mono">
                    <span className="text-indigo-400 font-sans text-[11px] flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full bg-indigo-400" /> Battery:
                    </span>
                    <span className="font-bold text-zinc-100">{points[hoverIndex].aki?.toFixed(1)} V</span>
                  </div>
                )}
                {points[hoverIndex].state && (
                  <div className="flex items-center justify-between gap-4 font-mono pt-1 border-t border-zinc-800/60">
                    <span className="text-zinc-400 font-sans text-[10px]">State:</span>
                    <span className="font-semibold text-zinc-200 text-[10px]">{points[hoverIndex].state}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Panel 1 (Top) — AC Voltage (V) */}
          <div className="bg-zinc-950/50 border border-zinc-800/80 rounded-lg p-4 space-y-3" data-testid="ats-panel-ac">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                AC Grid & Genset Voltage (V)
              </span>
              {/* Legend Pills with Interactive Series Toggles */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowPln(!showPln)}
                  aria-pressed={showPln}
                  data-testid="toggle-pln"
                  className={cn(
                    "px-2.5 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer inline-flex items-center gap-1.5",
                    showPln
                      ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                      : "bg-zinc-950/60 border-zinc-800 text-zinc-500 line-through opacity-60"
                  )}
                >
                  <span className={cn("h-2 w-2 rounded-full", showPln ? "bg-emerald-400" : "bg-zinc-600")} />
                  <span>{showPln ? '✓ ' : ''}PLN Main</span>
                </button>
                <button
                  type="button"
                  onClick={() => setShowGenset(!showGenset)}
                  aria-pressed={showGenset}
                  data-testid="toggle-genset"
                  className={cn(
                    "px-2.5 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer inline-flex items-center gap-1.5",
                    showGenset
                      ? "bg-amber-500/15 border-amber-500/30 text-amber-400"
                      : "bg-zinc-950/60 border-zinc-800 text-zinc-500 line-through opacity-60"
                  )}
                >
                  <span className={cn("h-2 w-2 rounded-full", showGenset ? "bg-amber-400" : "bg-zinc-600")} />
                  <span>{showGenset ? '✓ ' : ''}Genset Voltage</span>
                </button>
              </div>
            </div>

            <div className="relative">
              <svg
                viewBox={`0 0 ${width} ${height_AC}`}
                className="w-full h-auto overflow-visible cursor-crosshair"
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
              >
                {/* Horizontal Y Grid Lines & Labels */}
                {yTicks_AC.map((t, idx) => {
                  const yPos = getY_AC(t);
                  return (
                    <g key={`ac-y-${idx}`}>
                      <line
                        x1={padding_AC.left}
                        x2={width - padding_AC.right}
                        y1={yPos}
                        y2={yPos}
                        stroke="#27272a"
                        strokeWidth="1"
                        strokeDasharray="2 2"
                      />
                      <text
                        x={padding_AC.left - 8}
                        y={yPos + 3.5}
                        textAnchor="end"
                        className="text-[10px] fill-zinc-500 font-mono"
                      >
                        {t.toFixed(0)}V
                      </text>
                    </g>
                  );
                })}

                {/* Outage Shading */}
                {outages.map((o, i) => {
                  const x1 = Math.max(padding_AC.left, timeToX(o.start));
                  const x2 = Math.min(width - padding_AC.right, timeToX(o.end));
                  if (x2 - x1 < 2) return null;
                  const outageMinutes = Math.round((o.end - o.start) / 60000);
                  return (
                    <g key={`outage-ac-${i}`}>
                      <title>hub offline - no samples ({outageMinutes} min gap)</title>
                      <rect
                        x={x1}
                        y={padding_AC.top}
                        width={x2 - x1}
                        height={plotHeight_AC}
                        fill="#52525b"
                        opacity="0.18"
                      />
                      {x2 - x1 > 60 && (
                        <text
                          x={(x1 + x2) / 2}
                          y={padding_AC.top + 12}
                          textAnchor="middle"
                          className="text-[9px] fill-zinc-400 font-mono"
                        >
                          hub offline - no samples
                        </text>
                      )}
                      {x2 - x1 > 24 && x2 - x1 <= 60 && (
                        <text
                          x={(x1 + x2) / 2}
                          y={padding_AC.top + 12}
                          textAnchor="middle"
                          className="text-[9px] fill-zinc-400 font-mono"
                        >
                          offline
                        </text>
                      )}
                    </g>
                  );
                })}

                {/* Series Lines & Isolated Points */}
                {showPln && plnLine.linePath && (
                  <path
                    d={plnLine.linePath}
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    data-testid="path-pln"
                  />
                )}
                {showGenset && gensetLine.linePath && (
                  <path
                    d={gensetLine.linePath}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    data-testid="path-genset"
                  />
                )}
                {showPln &&
                  plnLine.isolated.map((d, i) => (
                    <circle key={`iso-p-${i}`} cx={d.x} cy={d.y} r={3} fill="#10b981" />
                  ))}
                {showGenset &&
                  gensetLine.isolated.map((d, i) => (
                    <circle key={`iso-g-${i}`} cx={d.x} cy={d.y} r={3} fill="#f59e0b" />
                  ))}

                {/* Bottom X Time Ticks */}
                {xTimeTicks.map((tickDate, idx) => {
                  const xPos = padding_AC.left + (idx / 4) * plotWidth;
                  return (
                    <text
                      key={`ac-x-${idx}`}
                      x={xPos}
                      y={height_AC - 6}
                      textAnchor="middle"
                      className="text-[10px] fill-zinc-500 font-mono"
                    >
                      {formatAxisTime(tickDate.toISOString(), timeRange)}
                    </text>
                  );
                })}

                {/* Hover Vertical Crosshair & Point Dots */}
                {hoverIndex !== null && points[hoverIndex] && (
                  <g data-testid="crosshair-ac">
                    <line
                      x1={getX(hoverIndex)}
                      x2={getX(hoverIndex)}
                      y1={padding_AC.top}
                      y2={padding_AC.top + plotHeight_AC}
                      stroke="#a1a1aa"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                    />
                    {showPln && typeof points[hoverIndex].pln === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY_AC(points[hoverIndex].pln!)}
                        r="4.5"
                        fill="#10b981"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                    {showGenset && typeof points[hoverIndex].genset === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY_AC(points[hoverIndex].genset!)}
                        r="4.5"
                        fill="#f59e0b"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                  </g>
                )}
              </svg>
            </div>
          </div>

          {/* Panel 2 (Bottom) — DC Battery Voltage (V) */}
          <div className="bg-zinc-950/50 border border-zinc-800/80 rounded-lg p-4 space-y-3" data-testid="ats-panel-battery">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                Starter Battery Voltage (AKI)
              </span>
              {/* Legend Pill & Threshold Tags */}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setShowAki(!showAki)}
                  aria-pressed={showAki}
                  data-testid="toggle-aki"
                  className={cn(
                    "px-2.5 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer inline-flex items-center gap-1.5",
                    showAki
                      ? "bg-indigo-500/15 border-indigo-500/30 text-indigo-400"
                      : "bg-zinc-950/60 border-zinc-800 text-zinc-500 line-through opacity-60"
                  )}
                >
                  <span className={cn("h-2 w-2 rounded-full", showAki ? "bg-indigo-400" : "bg-zinc-600")} />
                  <span>{showAki ? '✓ ' : ''}Battery AKI</span>
                </button>
                <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-400">
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    <span className="h-1 w-2 border-b border-dashed border-amber-400" />
                    Warn ({warnBatteryVal}V)
                  </span>
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                    <span className="h-1 w-2 border-b border-dashed border-red-400" />
                    Crit ({critBatteryVal}V)
                  </span>
                </div>
              </div>
            </div>

            <div className="relative">
              <svg
                viewBox={`0 0 ${width} ${height_DC}`}
                className="w-full h-auto overflow-visible cursor-crosshair"
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
              >
                {/* Horizontal Y Grid Lines & Labels */}
                {yTicks_DC.map((t, idx) => {
                  const yPos = getY_DC(t);
                  return (
                    <g key={`dc-y-${idx}`}>
                      <line
                        x1={padding_DC.left}
                        x2={width - padding_DC.right}
                        y1={yPos}
                        y2={yPos}
                        stroke="#27272a"
                        strokeWidth="1"
                        strokeDasharray="2 2"
                      />
                      <text
                        x={padding_DC.left - 8}
                        y={yPos + 3.5}
                        textAnchor="end"
                        className="text-[10px] fill-zinc-500 font-mono"
                      >
                        {t.toFixed(1)}V
                      </text>
                    </g>
                  );
                })}

                {/* Horizontal Battery Threshold Guides */}
                {warnBatteryVal >= minY_DC && warnBatteryVal <= maxY_DC && (
                  <g data-testid="threshold-warning">
                    <line
                      x1={padding_DC.left}
                      x2={width - padding_DC.right}
                      y1={getY_DC(warnBatteryVal)}
                      y2={getY_DC(warnBatteryVal)}
                      stroke="#f59e0b"
                      strokeWidth="1.5"
                      strokeDasharray="4 4"
                      opacity="0.85"
                    />
                    <text
                      x={width - padding_DC.right}
                      y={getY_DC(warnBatteryVal) - 4}
                      textAnchor="end"
                      className="text-[9px] fill-amber-400 font-mono font-medium"
                    >
                      11.8V Warning
                    </text>
                  </g>
                )}

                {critBatteryVal >= minY_DC && critBatteryVal <= maxY_DC && (
                  <g data-testid="threshold-critical">
                    <line
                      x1={padding_DC.left}
                      x2={width - padding_DC.right}
                      y1={getY_DC(critBatteryVal)}
                      y2={getY_DC(critBatteryVal)}
                      stroke="#ef4444"
                      strokeWidth="1.5"
                      strokeDasharray="4 4"
                      opacity="0.85"
                    />
                    <text
                      x={width - padding_DC.right}
                      y={getY_DC(critBatteryVal) - 4}
                      textAnchor="end"
                      className="text-[9px] fill-red-400 font-mono font-medium"
                    >
                      11.2V Critical
                    </text>
                  </g>
                )}

                {/* Outage Shading */}
                {outages.map((o, i) => {
                  const x1 = Math.max(padding_DC.left, timeToX(o.start));
                  const x2 = Math.min(width - padding_DC.right, timeToX(o.end));
                  if (x2 - x1 < 2) return null;
                  const outageMinutes = Math.round((o.end - o.start) / 60000);
                  return (
                    <g key={`outage-dc-${i}`}>
                      <title>hub offline - no samples ({outageMinutes} min gap)</title>
                      <rect
                        x={x1}
                        y={padding_DC.top}
                        width={x2 - x1}
                        height={plotHeight_DC}
                        fill="#52525b"
                        opacity="0.18"
                      />
                      {x2 - x1 > 60 && (
                        <text
                          x={(x1 + x2) / 2}
                          y={padding_DC.top + 12}
                          textAnchor="middle"
                          className="text-[9px] fill-zinc-400 font-mono"
                        >
                          hub offline - no samples
                        </text>
                      )}
                      {x2 - x1 > 24 && x2 - x1 <= 60 && (
                        <text
                          x={(x1 + x2) / 2}
                          y={padding_DC.top + 12}
                          textAnchor="middle"
                          className="text-[9px] fill-zinc-400 font-mono"
                        >
                          offline
                        </text>
                      )}
                    </g>
                  );
                })}

                {/* Battery AKI Line & Isolated Points */}
                {showAki && akiLine.linePath && (
                  <path
                    d={akiLine.linePath}
                    fill="none"
                    stroke="#818cf8"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    data-testid="path-aki"
                  />
                )}
                {showAki &&
                  akiLine.isolated.map((d, i) => (
                    <circle key={`iso-a-${i}`} cx={d.x} cy={d.y} r={3} fill="#818cf8" />
                  ))}

                {/* Bottom X Time Ticks */}
                {xTimeTicks.map((tickDate, idx) => {
                  const xPos = padding_DC.left + (idx / 4) * plotWidth;
                  return (
                    <text
                      key={`dc-x-${idx}`}
                      x={xPos}
                      y={height_DC - 6}
                      textAnchor="middle"
                      className="text-[10px] fill-zinc-500 font-mono"
                    >
                      {formatAxisTime(tickDate.toISOString(), timeRange)}
                    </text>
                  );
                })}

                {/* Hover Vertical Crosshair & Point Dot */}
                {hoverIndex !== null && points[hoverIndex] && (
                  <g data-testid="crosshair-dc">
                    <line
                      x1={getX(hoverIndex)}
                      x2={getX(hoverIndex)}
                      y1={padding_DC.top}
                      y2={padding_DC.top + plotHeight_DC}
                      stroke="#a1a1aa"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                    />
                    {showAki && typeof points[hoverIndex].aki === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY_DC(points[hoverIndex].aki!)}
                        r="4.5"
                        fill="#818cf8"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                  </g>
                )}
              </svg>
            </div>
          </div>
        </div>
      ) : (
        /* TS / Temperature Single Panel History Chart */
        <div className="space-y-4" data-testid="ts-single-panel-container">
          <div className="flex flex-wrap items-center justify-between gap-4 text-xs pt-1 border-t border-zinc-800/60">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowTemp(!showTemp)}
                aria-pressed={showTemp}
                data-testid="toggle-temp"
                className={cn(
                  "px-2.5 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer inline-flex items-center gap-1.5",
                  showTemp
                    ? "bg-indigo-500/15 border-indigo-500/30 text-indigo-400"
                    : "bg-zinc-950/60 border-zinc-800 text-zinc-500 line-through opacity-60"
                )}
              >
                <span className={cn("h-2 w-2 rounded-full", showTemp ? "bg-indigo-500" : "bg-zinc-600")} />
                <span>{showTemp ? '✓ ' : ''}Temperature (°C)</span>
              </button>
              <button
                type="button"
                onClick={() => setShowHumid(!showHumid)}
                aria-pressed={showHumid}
                data-testid="toggle-humid"
                className={cn(
                  "px-2.5 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer inline-flex items-center gap-1.5",
                  showHumid
                    ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                    : "bg-zinc-950/60 border-zinc-800 text-zinc-500 line-through opacity-60"
                )}
              >
                <span className={cn("h-2 w-2 rounded-full", showHumid ? "bg-emerald-400" : "bg-zinc-600")} />
                <span>{showHumid ? '✓ ' : ''}Humidity (%)</span>
              </button>
            </div>

            {(warningThresholdVal !== null && warningThresholdVal !== undefined) ||
            (criticalThresholdVal !== null && criticalThresholdVal !== undefined) ? (
              <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-400">
                {warningThresholdVal !== null && warningThresholdVal !== undefined && (
                  <div className="flex items-center gap-1.5">
                    <span className="h-0.5 w-3 bg-amber-400 border-b border-dashed border-amber-400" />
                    <span className="text-amber-400/90">Warn: {warningThresholdVal}°C</span>
                  </div>
                )}
                {criticalThresholdVal !== null && criticalThresholdVal !== undefined && (
                  <div className="flex items-center gap-1.5">
                    <span className="h-0.5 w-3 bg-red-400 border-b border-dashed border-red-400" />
                    <span className="text-red-400/90">Crit: {criticalThresholdVal}°C</span>
                  </div>
                )}
              </div>
            ) : null}
          </div>

          <div className="relative select-none">
            <svg
              viewBox={`0 0 ${width} ${height_TS}`}
              className="w-full h-auto overflow-visible cursor-crosshair"
              onMouseMove={handleMouseMove}
              onMouseLeave={handleMouseLeave}
            >
              <defs>
                <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {yTicks_TS.map((t, idx) => {
                const yPos = getY_TS(t);
                return (
                  <g key={`ts-y-${idx}`}>
                    <line
                      x1={padding_TS.left}
                      x2={width - padding_TS.right}
                      y1={yPos}
                      y2={yPos}
                      stroke="#27272a"
                      strokeWidth="1"
                      strokeDasharray="2 2"
                    />
                    <text
                      x={padding_TS.left - 8}
                      y={yPos + 3.5}
                      textAnchor="end"
                      className="text-[10px] fill-zinc-500 font-mono"
                    >
                      {t.toFixed(0)}
                    </text>
                  </g>
                );
              })}

              {warningThresholdVal !== null &&
                warningThresholdVal !== undefined &&
                warningThresholdVal >= minY_TS &&
                warningThresholdVal <= maxY_TS && (
                  <g>
                    <line
                      x1={padding_TS.left}
                      x2={width - padding_TS.right}
                      y1={getY_TS(warningThresholdVal)}
                      y2={getY_TS(warningThresholdVal)}
                      stroke="#f59e0b"
                      strokeWidth="1.5"
                      strokeDasharray="4 4"
                      opacity="0.85"
                    />
                    <text
                      x={width - padding_TS.right}
                      y={getY_TS(warningThresholdVal) - 4}
                      textAnchor="end"
                      className="text-[9px] fill-amber-400 font-mono font-medium"
                    >
                      Warn ({warningThresholdVal}°C)
                    </text>
                  </g>
                )}

              {criticalThresholdVal !== null &&
                criticalThresholdVal !== undefined &&
                criticalThresholdVal >= minY_TS &&
                criticalThresholdVal <= maxY_TS && (
                  <g>
                    <line
                      x1={padding_TS.left}
                      x2={width - padding_TS.right}
                      y1={getY_TS(criticalThresholdVal)}
                      y2={getY_TS(criticalThresholdVal)}
                      stroke="#ef4444"
                      strokeWidth="1.5"
                      strokeDasharray="4 4"
                      opacity="0.85"
                    />
                    <text
                      x={width - padding_TS.right}
                      y={getY_TS(criticalThresholdVal) - 4}
                      textAnchor="end"
                      className="text-[9px] fill-red-400 font-mono font-medium"
                    >
                      Crit ({criticalThresholdVal}°C)
                    </text>
                  </g>
                )}

              {outages.map((o, i) => {
                const x1 = Math.max(padding_TS.left, timeToX(o.start));
                const x2 = Math.min(width - padding_TS.right, timeToX(o.end));
                if (x2 - x1 < 2) return null;
                const outageMinutes = Math.round((o.end - o.start) / 60000);
                return (
                  <g key={`outage-ts-${i}`}>
                    <title>hub offline - no samples ({outageMinutes} min gap)</title>
                    <rect
                      x={x1}
                      y={padding_TS.top}
                      width={x2 - x1}
                      height={plotHeight_TS}
                      fill="#52525b"
                      opacity="0.18"
                    />
                    {x2 - x1 > 60 && (
                      <text
                        x={(x1 + x2) / 2}
                        y={padding_TS.top + 12}
                        textAnchor="middle"
                        className="text-[9px] fill-zinc-400 font-mono"
                      >
                        hub offline - no samples
                      </text>
                    )}
                    {x2 - x1 > 24 && x2 - x1 <= 60 && (
                      <text
                        x={(x1 + x2) / 2}
                        y={padding_TS.top + 12}
                        textAnchor="middle"
                        className="text-[9px] fill-zinc-400 font-mono"
                      >
                        offline
                      </text>
                    )}
                  </g>
                );
              })}

              {showTemp && tempLine.areaPath && <path d={tempLine.areaPath} fill="url(#tempGradient)" />}
              {showHumid && humidLine.linePath && (
                <path
                  d={humidLine.linePath}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  data-testid="path-humid"
                />
              )}
              {showTemp && tempLine.linePath && (
                <path
                  d={tempLine.linePath}
                  fill="none"
                  stroke="#6366f1"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  data-testid="path-temp"
                />
              )}
              {showTemp &&
                tempLine.isolated.map((d, i) => (
                  <circle key={`iso-t-${i}`} cx={d.x} cy={d.y} r={3} fill="#6366f1" />
                ))}
              {showHumid &&
                humidLine.isolated.map((d, i) => (
                  <circle key={`iso-h-${i}`} cx={d.x} cy={d.y} r={3} fill="#10b981" />
                ))}

              {xTimeTicks.map((tickDate, idx) => {
                const xPos = padding_TS.left + (idx / 4) * plotWidth;
                return (
                  <text
                    key={`ts-x-${idx}`}
                    x={xPos}
                    y={height_TS - 8}
                    textAnchor="middle"
                    className="text-[10px] fill-zinc-500 font-mono"
                  >
                    {formatAxisTime(tickDate.toISOString(), timeRange)}
                  </text>
                );
              })}

              {hoverIndex !== null && points[hoverIndex] && (
                <g data-testid="crosshair-ts">
                  <line
                    x1={getX(hoverIndex)}
                    x2={getX(hoverIndex)}
                    y1={padding_TS.top}
                    y2={padding_TS.top + plotHeight_TS}
                    stroke="#a1a1aa"
                    strokeWidth="1"
                    strokeDasharray="3 3"
                  />
                  {showTemp && typeof points[hoverIndex].temp === 'number' && (
                    <circle
                      cx={getX(hoverIndex)}
                      cy={getY_TS(points[hoverIndex].temp!)}
                      r="5"
                      fill="#6366f1"
                      stroke="#ffffff"
                      strokeWidth="2"
                    />
                  )}
                  {showHumid && typeof points[hoverIndex].humid === 'number' && (
                    <circle
                      cx={getX(hoverIndex)}
                      cy={getY_TS(points[hoverIndex].humid!)}
                      r="5"
                      fill="#10b981"
                      stroke="#ffffff"
                      strokeWidth="2"
                    />
                  )}
                </g>
              )}
            </svg>

            {hoverIndex !== null && points[hoverIndex] && (
              <div
                className="absolute pointer-events-none z-20 bg-zinc-900/95 backdrop-blur-md border border-zinc-700 shadow-xl rounded-lg p-2.5 text-xs text-zinc-200"
                style={{
                  left: `${(getX(hoverIndex) / width) * 100}%`,
                  top: '10px',
                  transform: hoverIndex > points.length / 2 ? 'translateX(-105%)' : 'translateX(5%)',
                }}
                data-testid="ts-hover-tooltip"
              >
                <div className="text-[10px] text-zinc-400 font-mono pb-1 border-b border-zinc-800 mb-1.5 flex items-center gap-1.5">
                  <Activity className="h-3 w-3 text-indigo-400" />
                  <span>{formatTooltipTime(points[hoverIndex].timestamp)}</span>
                </div>
                <div className="space-y-1">
                  {showTemp && typeof points[hoverIndex].temp === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-indigo-400 font-sans text-[11px] flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-indigo-500" /> Temp:
                      </span>
                      <span className="font-bold text-zinc-100">{points[hoverIndex].temp?.toFixed(1)} °C</span>
                    </div>
                  )}
                  {showHumid && typeof points[hoverIndex].humid === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-emerald-400 font-sans text-[11px] flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-emerald-400" /> Humidity:
                      </span>
                      <span className="font-bold text-zinc-100">{points[hoverIndex].humid?.toFixed(1)} %</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default HistoryChart;
