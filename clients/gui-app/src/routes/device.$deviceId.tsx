import { createFileRoute, useRouter } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  ArrowLeft, 
  Settings as SettingsIcon, 
  CheckCircle, 
  AlertTriangle, 
  Thermometer,
  Zap,
  Wind,
  ShieldAlert,
  Loader2,
  RefreshCw,
  TrendingUp,
  Activity,
} from 'lucide-react';
import { useState, useEffect } from 'react';
import { cn } from '../lib/utils';
import { queryKeys } from '../lib/queryKeys';
import { 
  fetchDevices, 
  fetchRooms, 
  fetchAlerts, 
  fetchCurrentUser, 
  updateThresholds, 
  sendDeviceCommand,
  fetchDeviceHistory
} from '../lib/api';
import type { ATSCommand, ThresholdUpdateRequest, TelemetryHistoryPoint, DeviceCommand } from '../types/api';

export const Route = createFileRoute('/device/$deviceId')({
  component: DeviceDetailPage,
});

function parseToDate(isoStr: string): Date {
  let normalized = String(isoStr).trim();
  if (!normalized.endsWith('Z') && !normalized.endsWith('z') && !/[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized += 'Z';
  }
  return new Date(normalized);
}

// Helper for formatting time labels on axes and tooltips in Jakarta time (WIB, UTC+7)
function formatAxisTime(isoStr: string, range: string): string {
  const d = parseToDate(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  if (range === '6h' || range === '24h') {
    return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Jakarta' });
  }
  return d.toLocaleString('id-ID', { 
    month: 'numeric', 
    day: 'numeric', 
    hour: '2-digit', 
    minute: '2-digit', 
    hour12: false, 
    timeZone: 'Asia/Jakarta' 
  }).replace(',', '');
}

function formatTooltipTime(isoStr: string): string {
  const d = parseToDate(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleString('id-ID', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Jakarta'
  }) + ' WIB';
}

interface TelemetryChartProps {
  points: TelemetryHistoryPoint[];
  devType: string;
  timeRange: '6h' | '24h' | '7d' | '30d';
  setTimeRange: (r: '6h' | '24h' | '7d' | '30d') => void;
  warningThresholdVal: number | null;
  criticalThresholdVal: number | null;
}

function TelemetryChart({
  points,
  devType,
  timeRange,
  setTimeRange,
  warningThresholdVal,
  criticalThresholdVal
}: TelemetryChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const isTS = devType === 'TS' || devType === 'AC' || devType === 'ACC';
  const isATS = devType === 'ATS';

  // Extract metric series for stats and scaling
  const tempValues = points.map((p) => p.temp).filter((v): v is number => typeof v === 'number');
  const humidValues = points.map((p) => p.humid).filter((v): v is number => typeof v === 'number');
  const plnValues = points.map((p) => p.pln).filter((v): v is number => typeof v === 'number');
  const gensetValues = points.map((p) => p.genset).filter((v): v is number => typeof v === 'number');
  const akiValues = points.map((p) => p.aki).filter((v): v is number => typeof v === 'number');

  // Summary stats
  const currentTemp = tempValues.length > 0 ? tempValues[tempValues.length - 1] : null;
  const minTemp = tempValues.length > 0 ? Math.min(...tempValues) : null;
  const maxTemp = tempValues.length > 0 ? Math.max(...tempValues) : null;
  const avgTemp = tempValues.length > 0 ? tempValues.reduce((a, b) => a + b, 0) / tempValues.length : null;

  const currentHumid = humidValues.length > 0 ? humidValues[humidValues.length - 1] : null;
  const minHumid = humidValues.length > 0 ? Math.min(...humidValues) : null;
  const maxHumid = humidValues.length > 0 ? Math.max(...humidValues) : null;
  const avgHumid = humidValues.length > 0 ? humidValues.reduce((a, b) => a + b, 0) / humidValues.length : null;

  const currentPln = plnValues.length > 0 ? plnValues[plnValues.length - 1] : null;
  const avgPln = plnValues.length > 0 ? plnValues.reduce((a, b) => a + b, 0) / plnValues.length : null;
  const currentGenset = gensetValues.length > 0 ? gensetValues[gensetValues.length - 1] : null;
  const maxGenset = gensetValues.length > 0 ? Math.max(...gensetValues) : null;
  const currentAki = akiValues.length > 0 ? akiValues[akiValues.length - 1] : null;
  const avgAki = akiValues.length > 0 ? akiValues.reduce((a, b) => a + b, 0) / akiValues.length : null;
  const currentState = points.length > 0 ? points[points.length - 1].state : null;

  // Chart dimensions & margins
  const width = 800;
  const height = 260;
  const padding = { top: 25, right: 35, bottom: 35, left: 45 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  // Compute Y Min and Max
  let minY = 0;
  let maxY = 100;

  if (isTS || (!isTS && !isATS)) {
    let rawMinY = tempValues.length > 0 ? Math.min(...tempValues) : 20;
    let rawMaxY = tempValues.length > 0 ? Math.max(...tempValues) : 35;
    if (humidValues.length > 0) {
      rawMinY = Math.min(rawMinY, ...humidValues);
      rawMaxY = Math.max(rawMaxY, ...humidValues);
    }
    if (warningThresholdVal !== null && warningThresholdVal !== undefined) {
      rawMaxY = Math.max(rawMaxY, warningThresholdVal + 2);
      rawMinY = Math.min(rawMinY, warningThresholdVal - 2);
    }
    if (criticalThresholdVal !== null && criticalThresholdVal !== undefined) {
      rawMaxY = Math.max(rawMaxY, criticalThresholdVal + 2);
      rawMinY = Math.min(rawMinY, criticalThresholdVal - 2);
    }
    const span = Math.max(rawMaxY - rawMinY, 6);
    minY = Math.floor(rawMinY - span * 0.1);
    maxY = Math.ceil(rawMaxY + span * 0.1);
  } else if (isATS) {
    const allAts = [...plnValues, ...gensetValues];
    const rawMaxY = allAts.length > 0 ? Math.max(...allAts, 250) : 250;
    minY = 0;
    maxY = Math.ceil(rawMaxY * 1.05);
  }

  const getY = (val: number) => {
    if (maxY === minY) return padding.top + plotHeight / 2;
    return padding.top + plotHeight - ((val - minY) / (maxY - minY)) * plotHeight;
  };

  // Calculate time bounds for selected window
  const windowHours = timeRange === '6h' ? 6 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 * 24 : 30 * 24;
  const windowMs = windowHours * 3600 * 1000;

  // Determine latest timestamp or fallback to current time
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

  // Production-grade gap handling: break lines at outages, shade offline spans
  const GAP_FLOOR_MS = 5 * 60 * 1000;
  const pointTimes: (number | null)[] = points.map((p) => {
    const t = p.timestamp ? parseToDate(p.timestamp).getTime() : NaN;
    return isNaN(t) ? null : t;
  });
  const validIntervals: number[] = [];
  for (let i = 1; i < pointTimes.length; i++) {
    const a = pointTimes[i - 1];
    const b = pointTimes[i];
    if (a !== null && b !== null) {
      const d = b - a;
      if (d > 0 && d < GAP_FLOOR_MS * 20) validIntervals.push(d);
    }
  }
  let gapThresholdMs = GAP_FLOOR_MS;
  if (validIntervals.length >= 8) {
    validIntervals.sort((a, b) => a - b);
    gapThresholdMs = Math.max(GAP_FLOOR_MS, validIntervals[Math.floor(validIntervals.length / 2)] * 10);
  }
  const outages = (() => {
    const list: { start: number; end: number }[] = [];
    for (let i = 1; i < pointTimes.length; i++) {
      const a = pointTimes[i - 1];
      const b = pointTimes[i];
      if (a !== null && b !== null && b - a > gapThresholdMs) list.push({ start: a, end: b });
    }
    const firstValid = pointTimes.find((t) => t !== null) as number | undefined;
    if (firstValid !== undefined && firstValid - minTimeMs > gapThresholdMs) {
      list.unshift({ start: minTimeMs, end: firstValid });
    }
    return list;
  })();

  interface SeriesPaths {
    linePath: string;
    areaPath: string;
    isolated: { x: number; y: number }[];
  }
  const buildLine = (getValue: (p: TelemetryHistoryPoint) => number | null | undefined): SeriesPaths => {
    const segments: string[] = [];
    const areas: string[] = [];
    const isolated: { x: number; y: number }[] = [];
    let current: { x: number; y: number }[] = [];
    const bottomY = padding.top + plotHeight;
    const flush = () => {
      if (current.length >= 2) {
        const seg = current.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ');
        segments.push(seg);
        areas.push(
          `${seg} L ${current[current.length - 1].x.toFixed(1)} ${bottomY.toFixed(1)} L ${current[0].x.toFixed(1)} ${bottomY.toFixed(1)} Z`
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
      if (t !== null && lastT !== null && t - lastT > gapThresholdMs) flush();
      current.push({ x: getX(idx), y: getY(v) });
      lastT = t;
    });
    flush();
    return { linePath: segments.join(' '), areaPath: areas.join(' '), isolated };
  };

  const tempLine = buildLine((p) => p.temp);
  const humidLine = buildLine((p) => p.humid);
  const plnLine = buildLine((p) => p.pln);
  const gensetLine = buildLine((p) => p.genset);
  const akiLine = buildLine((p) => p.aki);
  const tempLinePath = tempLine.linePath;
  const tempAreaPath = tempLine.areaPath;
  const humidLinePath = humidLine.linePath;
  const plnLinePath = plnLine.linePath;
  const gensetLinePath = gensetLine.linePath;
  const akiLinePath = akiLine.linePath;

  // Y-axis 5 ticks
  const yTicks = [0, 1, 2, 3, 4].map((i) => minY + (i / 4) * (maxY - minY));

  // X-axis 5 evenly spaced time ticks across the active monitoring timeframe
  const xTimeTicks = [0, 1, 2, 3, 4].map((i) => new Date(minTimeMs + (i / 4) * (maxTimeMs - minTimeMs)));

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

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      {/* Header with Title & Range Selectors */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            <span>Telemetry History & Trends</span>
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            Real-time telemetry stream across selected monitoring timeframe
          </p>
        </div>

        {/* Range Selector Pills */}
        <div className="flex items-center gap-1.5 bg-zinc-950 p-1 rounded-lg border border-zinc-800 self-start sm:self-auto">
          {(['6h', '24h', '7d', '30d'] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setTimeRange(r)}
              className={cn(
                "px-3 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer",
                timeRange === r
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
              )}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Stats Banner */}
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
                <span className="text-[10px] text-zinc-500">
                  {points.length} samples
                </span>
              </div>
            </div>
          )}
        </>
      )}

      {/* Legend */}
      {points.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 text-xs pt-1 border-t border-zinc-800/60">
          <div className="flex items-center gap-4">
            {isTS || (!isTS && !isATS) ? (
              <>
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-indigo-500" />
                  <span className="text-zinc-300 font-medium">Temperature (°C)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  <span className="text-zinc-300 font-medium">Humidity (%)</span>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
                  <span className="text-zinc-300 font-medium">PLN Main (V)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                  <span className="text-zinc-300 font-medium">Genset (V)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-indigo-400" />
                  <span className="text-zinc-300 font-medium">Battery AKI (V)</span>
                </div>
              </>
            )}
          </div>

          {(isTS || (!isTS && !isATS)) && (warningThresholdVal || criticalThresholdVal) && (
            <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-400">
              {warningThresholdVal && (
                <div className="flex items-center gap-1.5">
                  <span className="h-0.5 w-3 bg-amber-400 border-b border-dashed border-amber-400" />
                  <span className="text-amber-400/90">Warn: {warningThresholdVal}°C</span>
                </div>
              )}
              {criticalThresholdVal && (
                <div className="flex items-center gap-1.5">
                  <span className="h-0.5 w-3 bg-red-400 border-b border-dashed border-red-400" />
                  <span className="text-red-400/90">Crit: {criticalThresholdVal}°C</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* SVG Interactive Chart / Empty State */}
      {points.length === 0 ? (
        <div className="h-56 flex flex-col items-center justify-center text-center p-6 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/40">
          <Activity className="h-8 w-8 text-zinc-600 mb-2 animate-pulse" />
          <p className="text-sm font-medium text-zinc-300">Collecting telemetry data...</p>
          <p className="text-xs text-zinc-500 mt-1">
            No historical telemetry records found for device within the {timeRange} window.
          </p>
        </div>
      ) : (
        <div className="relative select-none">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-auto overflow-visible cursor-crosshair"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoverIndex(null)}
          >
            <defs>
              <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6366f1" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Background Grid Lines & Y-Axis Labels */}
            {yTicks.map((t, idx) => {
              const yPos = getY(t);
              return (
                <g key={idx}>
                  <line
                    x1={padding.left}
                    x2={width - padding.right}
                    y1={yPos}
                    y2={yPos}
                    stroke="#27272a"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                  />
                  <text
                    x={padding.left - 8}
                    y={yPos + 3.5}
                    textAnchor="end"
                    className="text-[10px] fill-zinc-500 font-mono"
                  >
                    {t.toFixed(0)}
                  </text>
                </g>
              );
            })}

            {/* Horizontal Threshold Reference Lines (Amber / Red) */}
            {(isTS || (!isTS && !isATS)) && warningThresholdVal !== null && warningThresholdVal >= minY && warningThresholdVal <= maxY && (
              <g>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={getY(warningThresholdVal)}
                  y2={getY(warningThresholdVal)}
                  stroke="#f59e0b"
                  strokeWidth="1.5"
                  strokeDasharray="4 4"
                  opacity="0.85"
                />
                <text
                  x={width - padding.right}
                  y={getY(warningThresholdVal) - 4}
                  textAnchor="end"
                  className="text-[9px] fill-amber-400 font-mono font-medium"
                >
                  Warn ({warningThresholdVal}°C)
                </text>
              </g>
            )}

            {(isTS || (!isTS && !isATS)) && criticalThresholdVal !== null && criticalThresholdVal >= minY && criticalThresholdVal <= maxY && (
              <g>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={getY(criticalThresholdVal)}
                  y2={getY(criticalThresholdVal)}
                  stroke="#ef4444"
                  strokeWidth="1.5"
                  strokeDasharray="4 4"
                  opacity="0.85"
                />
                <text
                  x={width - padding.right}
                  y={getY(criticalThresholdVal) - 4}
                  textAnchor="end"
                  className="text-[9px] fill-red-400 font-mono font-medium"
                >
                  Crit ({criticalThresholdVal}°C)
                </text>
              </g>
            )}

            {/* Offline Shading (gaps beyond threshold) */}
            {outages.map((o, i) => {
              const x1 = Math.max(padding.left, timeToX(o.start));
              const x2 = Math.min(width - padding.right, timeToX(o.end));
              if (x2 - x1 < 2) return null;
              return (
                <g key={`outage-${i}`}>
                  <rect
                    x={x1}
                    y={padding.top}
                    width={x2 - x1}
                    height={plotHeight}
                    fill="#52525b"
                    opacity="0.25"
                  />
                  {x2 - x1 > 44 && (
                    <text
                      x={(x1 + x2) / 2}
                      y={padding.top + 12}
                      textAnchor="middle"
                      className="text-[9px] fill-zinc-500 font-mono"
                    >
                      offline
                    </text>
                  )}
                </g>
              );
            })}

            {/* Curves & Area Fills */}
            {isTS || (!isTS && !isATS) ? (
              <>
                {tempAreaPath && <path d={tempAreaPath} fill="url(#tempGradient)" />}
                {humidLinePath && (
                  <path
                    d={humidLinePath}
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
                {tempLinePath && (
                  <path
                    d={tempLinePath}
                    fill="none"
                    stroke="#6366f1"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
                {tempLine.isolated.map((d, i) => (
                  <circle key={`iso-t-${i}`} cx={d.x} cy={d.y} r={3} fill="#6366f1" />
                ))}
                {humidLine.isolated.map((d, i) => (
                  <circle key={`iso-h-${i}`} cx={d.x} cy={d.y} r={3} fill="#10b981" />
                ))}
              </>
            ) : (
              <>
                {plnLinePath && (
                  <path
                    d={plnLinePath}
                    fill="none"
                    stroke="#10b981"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
                {gensetLinePath && (
                  <path
                    d={gensetLinePath}
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
                {akiLinePath && (
                  <path
                    d={akiLinePath}
                    fill="none"
                    stroke="#6366f1"
                    strokeWidth="2"
                    strokeDasharray="3 3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
                {plnLine.isolated.map((d, i) => (
                  <circle key={`iso-p-${i}`} cx={d.x} cy={d.y} r={3} fill="#10b981" />
                ))}
                {gensetLine.isolated.map((d, i) => (
                  <circle key={`iso-g-${i}`} cx={d.x} cy={d.y} r={3} fill="#f59e0b" />
                ))}
                {akiLine.isolated.map((d, i) => (
                  <circle key={`iso-a-${i}`} cx={d.x} cy={d.y} r={3} fill="#6366f1" />
                ))}
              </>
            )}

            {/* X-Axis Ticks & Labels */}
            {xTimeTicks.map((tickDate, idx) => {
              const xPos = padding.left + (idx / 4) * plotWidth;
              return (
                <text
                  key={idx}
                  x={xPos}
                  y={height - 8}
                  textAnchor="middle"
                  className="text-[10px] fill-zinc-500 font-mono"
                >
                  {formatAxisTime(tickDate.toISOString(), timeRange)}
                </text>
              );
            })}

            {/* Interactive Hover Indicator: Crosshair & Highlight Dots */}
            {hoverIndex !== null && points[hoverIndex] && (
              <g>
                <line
                  x1={getX(hoverIndex)}
                  x2={getX(hoverIndex)}
                  y1={padding.top}
                  y2={padding.top + plotHeight}
                  stroke="#a1a1aa"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />

                {(isTS || (!isTS && !isATS)) && (
                  <>
                    {typeof points[hoverIndex].temp === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY(points[hoverIndex].temp!)}
                        r="5"
                        fill="#6366f1"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                    {typeof points[hoverIndex].humid === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY(points[hoverIndex].humid!)}
                        r="5"
                        fill="#10b981"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                  </>
                )}

                {isATS && (
                  <>
                    {typeof points[hoverIndex].pln === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY(points[hoverIndex].pln!)}
                        r="5"
                        fill="#10b981"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                    {typeof points[hoverIndex].genset === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY(points[hoverIndex].genset!)}
                        r="5"
                        fill="#f59e0b"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                    {typeof points[hoverIndex].aki === 'number' && (
                      <circle
                        cx={getX(hoverIndex)}
                        cy={getY(points[hoverIndex].aki!)}
                        r="4"
                        fill="#6366f1"
                        stroke="#ffffff"
                        strokeWidth="2"
                      />
                    )}
                  </>
                )}
              </g>
            )}
          </svg>

          {/* Floating Tooltip Box */}
          {hoverIndex !== null && points[hoverIndex] && (
            <div
              className="absolute pointer-events-none z-20 bg-zinc-900/95 backdrop-blur-md border border-zinc-700 shadow-xl rounded-lg p-2.5 text-xs text-zinc-200"
              style={{
                left: `${(getX(hoverIndex) / width) * 100}%`,
                top: '10px',
                transform: hoverIndex > points.length / 2 ? 'translateX(-105%)' : 'translateX(5%)',
              }}
            >
              <div className="text-[10px] text-zinc-400 font-mono pb-1 border-b border-zinc-800 mb-1.5 flex items-center gap-1.5">
                <Activity className="h-3 w-3 text-indigo-400" />
                <span>{formatTooltipTime(points[hoverIndex].timestamp)}</span>
              </div>

              {(isTS || (!isTS && !isATS)) && (
                <div className="space-y-1">
                  {typeof points[hoverIndex].temp === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-indigo-400 font-sans text-[11px] flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-indigo-500" /> Temp:
                      </span>
                      <span className="font-bold text-zinc-100">{points[hoverIndex].temp?.toFixed(1)} °C</span>
                    </div>
                  )}
                  {typeof points[hoverIndex].humid === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-emerald-400 font-sans text-[11px] flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-emerald-400" /> Humidity:
                      </span>
                      <span className="font-bold text-zinc-100">{points[hoverIndex].humid?.toFixed(1)} %</span>
                    </div>
                  )}
                </div>
              )}

              {isATS && (
                <div className="space-y-1">
                  {typeof points[hoverIndex].pln === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-emerald-400 font-sans text-[11px]">PLN:</span>
                      <span className="font-bold text-zinc-100">{points[hoverIndex].pln?.toFixed(1)} V</span>
                    </div>
                  )}
                  {typeof points[hoverIndex].genset === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-amber-400 font-sans text-[11px]">Genset:</span>
                      <span className="font-bold text-zinc-100">{points[hoverIndex].genset?.toFixed(1)} V</span>
                    </div>
                  )}
                  {typeof points[hoverIndex].aki === 'number' && (
                    <div className="flex items-center justify-between gap-4 font-mono">
                      <span className="text-indigo-400 font-sans text-[11px]">Battery:</span>
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
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DeviceDetailPage() {
  const { deviceId } = Route.useParams();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [timeRange, setTimeRange] = useState<'6h' | '24h' | '7d' | '30d'>('24h');

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchCurrentUser,
  });

  const { data: devices = [], isFetching: isFetchingDevices } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const { data: deviceAlertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ device: deviceId }),
    queryFn: () => fetchAlerts({ device: deviceId }),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const { data: historyData } = useQuery({
    queryKey: queryKeys.devices.history(deviceId, timeRange),
    queryFn: () => fetchDeviceHistory(deviceId, timeRange),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const device = devices.find((d) => d.dev_id === deviceId);
  const room = device ? rooms.find((r) => r.id === device.room_id) : null;

  // Threshold Config Form States
  const [warningThreshold, setWarningThreshold] = useState<string>('30');
  const [criticalThreshold, setCriticalThreshold] = useState<string>('35');
  const [hysteresis, setHysteresis] = useState<string>('0.5');
  const [debounceSeconds, setDebounceSeconds] = useState<string>('60');
  const [configSuccess, setConfigSuccess] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  // Initialize threshold inputs from server data
  useEffect(() => {
    if (device?.threshold_config) {
      setWarningThreshold(device.threshold_config.warning.toString());
      setCriticalThreshold(device.threshold_config.critical.toString());
      setHysteresis(device.threshold_config.hysteresis.toString());
      setDebounceSeconds(device.threshold_config.debounce_seconds.toString());
    }
  }, [device]);

  // Command Controls Form States
  const [commandPayload, setCommandPayload] = useState<ATSCommand>({});
  const [acTarget, setAcTarget] = useState<'AC1' | 'AC2'>('AC1');
  const [acAction, setAcAction] = useState<'ON' | 'OFF' | 'SET_TEMP'>('ON');
  const [acTemp, setAcTemp] = useState<number>(24);
  const [cmdSuccess, setCmdSuccess] = useState<string | null>(null);
  const [cmdError, setCmdError] = useState<string | null>(null);

  const role = currentUser?.role || 'viewer';
  const isAdmin = role === 'admin';
  const canControl = role === 'admin' || role === 'operator';

  // Thresholds Mutation
  const thresholdMutation = useMutation({
    mutationFn: (payload: ThresholdUpdateRequest) => updateThresholds(deviceId, payload),
    onSuccess: () => {
      setConfigSuccess('Thresholds updated successfully');
      setConfigError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setConfigSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setConfigError(err.message || 'Failed to update threshold configuration');
      setConfigSuccess(null);
    },
  });

  // Command Mutation
  const commandMutation = useMutation({
    mutationFn: (payload: DeviceCommand) => sendDeviceCommand(deviceId, payload),
    onSuccess: () => {
      setCmdSuccess('Command queued successfully for edge delivery');
      setCmdError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setCmdSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setCmdError(err.message || 'Failed to dispatch command');
      setCmdSuccess(null);
    },
  });

  const handleThresholdSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setConfigError(null);
    setConfigSuccess(null);

    const warn = parseFloat(warningThreshold);
    const crit = parseFloat(criticalThreshold);
    const hyst = parseFloat(hysteresis);
    const deb = parseInt(debounceSeconds, 10);

    if (isNaN(warn) || isNaN(crit)) {
      setConfigError('Warning and Critical thresholds must be valid numbers');
      return;
    }

    if (warn > crit) {
      setConfigError('Warning threshold cannot exceed critical threshold');
      return;
    }

    thresholdMutation.mutate({
      warning: warn,
      critical: crit,
      hysteresis: isNaN(hyst) ? 0.5 : hyst,
      debounce_seconds: isNaN(deb) ? 60 : deb,
    });
  };

  const handleCommandSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCmdError(null);
    setCmdSuccess(null);

    if (device?.dev_type === 'AC' || device?.dev_type === 'ACC') {
      if (acAction === 'SET_TEMP' && (acTemp < 16 || acTemp > 30)) {
        setCmdError('Temperature must be between 16°C and 30°C');
        return;
      }
      commandMutation.mutate({
        target: acTarget,
        action: acAction,
        ...(acAction === 'SET_TEMP' ? { temp: acTemp } : {}),
      });
      return;
    }

    if (!commandPayload.mode && !commandPayload.start_genset && !commandPayload.reset) {
      setCmdError('Select at least one command action to send');
      return;
    }

    commandMutation.mutate(commandPayload);
  };

  if (!device) {
    return (
      <div className="space-y-6">
        <button 
          onClick={() => router.navigate({ to: '/' })}
          className="flex items-center gap-2 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Dashboard</span>
        </button>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center">
          <p className="text-zinc-400">Device '{deviceId}' not found.</p>
        </div>
      </div>
    );
  }

  const isTS = device.dev_type === 'TS';
  const isATS = device.dev_type === 'ATS';
  const isAC = device.dev_type === 'AC' || device.dev_type === 'ACC';
  const alerts = deviceAlertsData?.alerts || [];
  const historyPoints = historyData?.points || [];

  return (
    <div className="space-y-8">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => router.navigate({ to: '/' })}
            className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-md text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-zinc-100">{device.dev_name || device.dev_id}</h1>
              {(() => {
                const isOnline = device.status === 'online';
                const isPending = !device.is_active || device.status === 'pending';
                return (
                  <span className={cn(
                    "px-2.5 py-0.5 rounded-full text-xs font-semibold border inline-flex items-center gap-1.5",
                    isPending
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      : isOnline
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-zinc-800/80 text-zinc-400 border-zinc-700/50"
                  )}>
                    <span className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      isPending 
                        ? "bg-amber-400" 
                        : isOnline 
                          ? "bg-emerald-400 animate-pulse" 
                          : "bg-zinc-500"
                    )} />
                    {isPending ? 'Pending Approval' : isOnline ? 'Online' : 'Offline'}
                  </span>
                );
              })()}
            </div>
            <p className="text-xs text-zinc-500 mt-1 font-mono">
              MAC / ID: {device.dev_id} · Type: {device.dev_type || 'Generic'} · Room: {room?.name || 'Unassigned'}
            </p>
          </div>
        </div>

        {isFetchingDevices && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-zinc-900 px-3 py-1.5 rounded-full border border-zinc-800">
            <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />
            <span>3s Polling</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left 2 Cols: Telemetry Trends, Details & Command Panel */}
        <div className="lg:col-span-2 space-y-6">
          {/* Interactive Telemetry History & Trends Chart */}
          <TelemetryChart
            points={historyPoints}
            devType={device.dev_type || 'TS'}
            timeRange={timeRange}
            setTimeRange={setTimeRange}
            warningThresholdVal={device.threshold_config ? device.threshold_config.warning : null}
            criticalThresholdVal={device.threshold_config ? device.threshold_config.critical : null}
          />

          {/* Metadata Card */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              {isTS && <Thermometer className="h-4 w-4 text-indigo-400" />}
              {isATS && <Zap className="h-4 w-4 text-amber-400" />}
              {isAC && <Wind className="h-4 w-4 text-emerald-400" />}
              <span>Node Information</span>
            </h3>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-2 text-sm">
              <div className="bg-zinc-950 p-3 rounded border border-zinc-850">
                <span className="text-[10px] text-zinc-500 uppercase font-semibold">Gateway Hub</span>
                <p className="font-mono font-medium text-zinc-200 mt-0.5">{device.hub_id || 'Direct'}</p>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-850">
                <span className="text-[10px] text-zinc-500 uppercase font-semibold">Room Assignment</span>
                <p className="font-medium text-zinc-200 mt-0.5">{room?.name || 'Unpaired'}</p>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-850">
                <span className="text-[10px] text-zinc-500 uppercase font-semibold">Registered Date</span>
                <p className="text-xs text-zinc-300 mt-0.5">
                  {device.created_at ? new Date(device.created_at).toLocaleDateString() : '—'}
                </p>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-850">
                <span className="text-[10px] text-zinc-500 uppercase font-semibold">Map Coordinate</span>
                <p className="font-mono text-xs text-zinc-300 mt-0.5">
                  {device.marker_x !== null && device.marker_y !== null 
                    ? `(${device.marker_x}%, ${device.marker_y}%)` 
                    : 'Unplaced'}
                </p>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-850">
                <span className="text-[10px] text-zinc-500 uppercase font-semibold">Warning Level</span>
                <p className="font-mono font-medium text-amber-400 mt-0.5">
                  {device.threshold_config ? `${device.threshold_config.warning}°C` : 'Default'}
                </p>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-850">
                <span className="text-[10px] text-zinc-500 uppercase font-semibold">Critical Level</span>
                <p className="font-mono font-medium text-red-400 mt-0.5">
                  {device.threshold_config ? `${device.threshold_config.critical}°C` : 'Default'}
                </p>
              </div>
            </div>
          </div>

          {/* ATS / AC Command Panel */}
          {(isATS || isAC) && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                {isAC ? <Wind className="h-4 w-4 text-emerald-400" /> : <Zap className="h-4 w-4 text-indigo-400" />}
                <span>{isAC ? 'Air Conditioner Control Panel' : 'ATS Generator Command Dispatch'}</span>
              </h3>

              {!canControl && (
                <div className="bg-zinc-950 border border-zinc-850 rounded p-4 text-zinc-500 text-xs">
                  Your current role ({role}) does not have permission to issue hardware commands.
                </div>
              )}

              {canControl && isAC && (
                <form onSubmit={handleCommandSubmit} className="space-y-5 pt-2">
                  {cmdError && (
                    <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                      <span>{cmdError}</span>
                    </div>
                  )}

                  {cmdSuccess && (
                    <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 flex-shrink-0" />
                      <span>{cmdSuccess}</span>
                    </div>
                  )}

                  {/* Target Unit Selector */}
                  <div>
                    <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Target Air Conditioner Unit
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        type="button"
                        onClick={() => setAcTarget('AC1')}
                        className={cn(
                          "py-2.5 px-4 rounded border text-xs font-medium cursor-pointer transition-all flex items-center justify-center gap-2",
                          acTarget === 'AC1'
                            ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold"
                            : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        <Wind className="h-3.5 w-3.5" />
                        <span>Unit AC 1</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setAcTarget('AC2')}
                        className={cn(
                          "py-2.5 px-4 rounded border text-xs font-medium cursor-pointer transition-all flex items-center justify-center gap-2",
                          acTarget === 'AC2'
                            ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold"
                            : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        <Wind className="h-3.5 w-3.5" />
                        <span>Unit AC 2</span>
                      </button>
                    </div>
                  </div>

                  {/* AC Action Mode */}
                  <div>
                    <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                      Control Action
                    </label>
                    <div className="grid grid-cols-3 gap-3">
                      <button
                        type="button"
                        onClick={() => setAcAction('ON')}
                        className={cn(
                          "py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all",
                          acAction === 'ON'
                            ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 font-semibold"
                            : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        Power ON
                      </button>
                      <button
                        type="button"
                        onClick={() => setAcAction('OFF')}
                        className={cn(
                          "py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all",
                          acAction === 'OFF'
                            ? "bg-red-500/20 border-red-500 text-red-300 font-semibold"
                            : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        Power OFF
                      </button>
                      <button
                        type="button"
                        onClick={() => setAcAction('SET_TEMP')}
                        className={cn(
                          "py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all",
                          acAction === 'SET_TEMP'
                            ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold"
                            : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        Set Temp
                      </button>
                    </div>
                  </div>

                  {/* Temperature Slider & Quick Presets */}
                  {acAction === 'SET_TEMP' && (
                    <div className="space-y-3 bg-zinc-950 p-4 rounded border border-zinc-850">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                          Target Temperature (°C)
                        </label>
                        <span className="text-lg font-bold font-mono text-indigo-400">
                          {acTemp} °C
                        </span>
                      </div>
                      <input
                        type="range"
                        min="16"
                        max="30"
                        step="1"
                        value={acTemp}
                        onChange={(e) => setAcTemp(parseInt(e.target.value, 10))}
                        className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                      />
                      <div className="flex items-center justify-between gap-1.5 pt-1">
                        {[18, 20, 22, 24, 26].map((tempVal) => (
                          <button
                            key={tempVal}
                            type="button"
                            onClick={() => setAcTemp(tempVal)}
                            className={cn(
                              "px-2.5 py-1 rounded text-xs font-mono transition-colors cursor-pointer border",
                              acTemp === tempVal
                                ? "bg-indigo-600 border-indigo-500 text-white font-bold"
                                : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                            )}
                          >
                            {tempVal}°C
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex justify-end pt-2">
                    <button
                      type="submit"
                      disabled={commandMutation.isPending}
                      className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer flex items-center gap-2 transition-all shadow-lg shadow-indigo-600/20"
                    >
                      {commandMutation.isPending ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Sending IR Command...</span>
                        </>
                      ) : (
                        <>
                          <Wind className="h-3.5 w-3.5" />
                          <span>Send AC IR Command</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {canControl && isATS && (
                <form onSubmit={handleCommandSubmit} className="space-y-4 pt-2">
                  {cmdError && (
                    <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                      <span>{cmdError}</span>
                    </div>
                  )}

                  {cmdSuccess && (
                    <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 flex-shrink-0" />
                      <span>{cmdSuccess}</span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                        Operating Mode
                      </label>
                      <select
                        value={commandPayload.mode || ''}
                        onChange={(e) => setCommandPayload({
                          ...commandPayload,
                          mode: (e.target.value as 'auto' | 'manual') || undefined
                        })}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500"
                      >
                        <option value="">Select Mode...</option>
                        <option value="auto">Auto Mode</option>
                        <option value="manual">Manual Mode</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                        Genset Start / Stop
                      </label>
                      <select
                        value={commandPayload.start_genset || ''}
                        onChange={(e) => setCommandPayload({
                          ...commandPayload,
                          start_genset: (e.target.value as 'on' | 'off') || undefined
                        })}
                        className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500"
                      >
                        <option value="">Select Genset Action...</option>
                        <option value="on">Start Genset (ON)</option>
                        <option value="off">Stop Genset (OFF)</option>
                      </select>
                    </div>
                  </div>

                  {isAdmin && (
                    <div className="pt-2">
                      <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={commandPayload.reset === 'rst'}
                          onChange={(e) => setCommandPayload({
                            ...commandPayload,
                            reset: e.target.checked ? 'rst' : undefined
                          })}
                          className="rounded border-zinc-700 bg-zinc-950 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span>Issue controller reboot / reset (`rst`)</span>
                      </label>
                    </div>
                  )}

                  <div className="flex justify-end pt-2">
                    <button
                      type="submit"
                      disabled={commandMutation.isPending}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium cursor-pointer flex items-center gap-2"
                    >
                      {commandMutation.isPending ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Dispatching...</span>
                        </>
                      ) : (
                        <span>Send Command</span>
                      )}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Alert History for Device */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-indigo-400" />
              <span>Device Alert Log</span>
            </h3>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800">
                  <tr>
                    <th className="px-4 py-3">Severity</th>
                    <th className="px-4 py-3">Metric / Message</th>
                    <th className="px-4 py-3">Value</th>
                    <th className="px-4 py-3">Timestamp</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {alerts.map((a) => (
                    <tr key={a.event_id} className="hover:bg-zinc-850/50">
                      <td className="px-4 py-3">
                        <span className={cn(
                          "px-2 py-0.5 rounded text-[10px] font-bold uppercase",
                          a.severity === 'critical' ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"
                        )}>
                          {a.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-zinc-200">
                        {a.message || a.metric || 'Threshold Breach'}
                      </td>
                      <td className="px-4 py-3 font-mono">
                        {a.value !== null && a.value !== undefined ? a.value : '—'}
                      </td>
                      <td className="px-4 py-3 text-zinc-500">
                        {new Date(a.timestamp).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "px-2 py-0.5 rounded text-[10px] font-semibold",
                          a.resolved_at ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                        )}>
                          {a.resolved_at ? 'Resolved' : 'Active'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {alerts.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-center text-zinc-500 text-xs">
                        No alerts recorded for this device.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Col: Threshold Settings */}
        <div className="space-y-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <SettingsIcon className="h-4 w-4 text-indigo-400" />
              <span>Thresholds & Debounce</span>
            </h3>

            {!isAdmin && (
              <div className="bg-zinc-950 border border-zinc-850 rounded p-4 text-zinc-500 text-xs">
                Admin permissions required to modify alert threshold parameters.
              </div>
            )}

            {isAdmin && (
              <form onSubmit={handleThresholdSubmit} className="space-y-4">
                {configError && (
                  <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                    <span>{configError}</span>
                  </div>
                )}

                {configSuccess && (
                  <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 flex-shrink-0" />
                    <span>{configSuccess}</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Warning Threshold (°C)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={warningThreshold}
                    onChange={(e) => setWarningThreshold(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Critical Threshold (°C)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={criticalThreshold}
                    onChange={(e) => setCriticalThreshold(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Hysteresis (°C)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={hysteresis}
                    onChange={(e) => setHysteresis(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
                  />
                  <span className="text-[10px] text-zinc-500 mt-1 block">
                    Recovery offset to prevent oscillations.
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Debounce Window (Seconds)
                  </label>
                  <input
                    type="number"
                    value={debounceSeconds}
                    onChange={(e) => setDebounceSeconds(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
                  />
                  <span className="text-[10px] text-zinc-500 mt-1 block">
                    Minimum cooldown period between logged alert events.
                  </span>
                </div>

                <div className="pt-2">
                  <button
                    type="submit"
                    disabled={thresholdMutation.isPending}
                    className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    {thresholdMutation.isPending ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Saving...</span>
                      </>
                    ) : (
                      <span>Save Thresholds</span>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
