import { useState } from 'react';
import { TrendingUp, Activity } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { TelemetryHistoryPoint } from '../../types/api';
import { parseToDate, formatAxisTime, formatTooltipTime, getGapThresholdMs, getOutages } from '../../lib/chartUtils';

interface TelemetryChartProps {
  points: TelemetryHistoryPoint[];
  devType: string;
  timeRange: '6h' | '24h' | '7d' | '30d';
  setTimeRange: (r: '6h' | '24h' | '7d' | '30d') => void;
  warningThresholdVal: number | null;
  criticalThresholdVal: number | null;
}

export function HistoryChart({ points, devType, timeRange, setTimeRange, warningThresholdVal, criticalThresholdVal }: TelemetryChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const isTS = devType === 'TS' || devType === 'AC' || devType === 'ACC';
  const isATS = devType === 'ATS';

  const tempValues = points.map((p) => p.temp).filter((v): v is number => typeof v === 'number');
  const humidValues = points.map((p) => p.humid).filter((v): v is number => typeof v === 'number');
  const plnValues = points.map((p) => p.pln).filter((v): v is number => typeof v === 'number');
  const gensetValues = points.map((p) => p.genset).filter((v): v is number => typeof v === 'number');
  const akiValues = points.map((p) => p.aki).filter((v): v is number => typeof v === 'number');

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

  const width = 800;
  const height = 260;
  const padding = { top: 25, right: 35, bottom: 35, left: 45 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

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

  const windowHours = timeRange === '6h' ? 6 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 * 24 : 30 * 24;
  const windowMs = windowHours * 3600 * 1000;
  const latestPointTime = points.length > 0 && points[points.length - 1].timestamp ? parseToDate(points[points.length - 1].timestamp).getTime() : Date.now();
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

  interface SeriesPaths { linePath: string; areaPath: string; isolated: { x: number; y: number }[]; }
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
        areas.push(`${seg} L ${current[current.length - 1].x.toFixed(1)} ${bottomY.toFixed(1)} L ${current[0].x.toFixed(1)} ${bottomY.toFixed(1)} Z`);
      } else if (current.length === 1) {
        isolated.push({ x: current[0].x, y: current[0].y });
      }
      current = [];
    };
    let lastT: number | null = null;
    points.forEach((p, idx) => {
      const v = getValue(p);
      if (typeof v !== 'number' || isNaN(v)) { flush(); return; }
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

  const yTicks = [0, 1, 2, 3, 4].map((i) => minY + (i / 4) * (maxY - minY));
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
      if (diff < minDiff) { minDiff = diff; closestIdx = idx; }
    });
    setHoverIndex(closestIdx);
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            <span>Telemetry History & Trends</span>
          </h3>
          <p className="text-xs text-zinc-500 mt-0.5">Real-time telemetry stream across selected monitoring timeframe</p>
        </div>
        <div className="flex items-center gap-1.5 bg-zinc-950 p-1 rounded-lg border border-zinc-800 self-start sm:self-auto">
          {(['6h', '24h', '7d', '30d'] as const).map((r) => (
            <button key={r} type="button" onClick={() => setTimeRange(r)} className={cn("px-3 py-1 text-xs font-semibold rounded-md transition-all cursor-pointer", timeRange === r ? "bg-indigo-600 text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50")}>{r}</button>
          ))}
        </div>
      </div>

      {points.length > 0 && (
        <>
          {isTS || (!isTS && !isATS) ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-indigo-500" /> Current Temp</span><p className="text-lg font-mono font-bold text-zinc-100 mt-1">{currentTemp !== null ? `${currentTemp.toFixed(1)}°C` : '—'}</p><span className="text-[10px] text-zinc-500">{currentHumid !== null ? `Humidity: ${currentHumid.toFixed(1)}%` : '—'}</span></div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500">Min Temp</span><p className="text-lg font-mono font-bold text-emerald-400 mt-1">{minTemp !== null ? `${minTemp.toFixed(1)}°C` : '—'}</p><span className="text-[10px] text-zinc-500">{minHumid !== null ? `Min Hum: ${minHumid.toFixed(1)}%` : '—'}</span></div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500">Max Temp</span><p className="text-lg font-mono font-bold text-red-400 mt-1">{maxTemp !== null ? `${maxTemp.toFixed(1)}°C` : '—'}</p><span className="text-[10px] text-zinc-500">{maxHumid !== null ? `Max Hum: ${maxHumid.toFixed(1)}%` : '—'}</span></div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500">Average Temp</span><p className="text-lg font-mono font-bold text-indigo-300 mt-1">{avgTemp !== null ? `${avgTemp.toFixed(1)}°C` : '—'}</p><span className="text-[10px] text-zinc-500">{avgHumid !== null ? `Avg Hum: ${avgHumid.toFixed(1)}%` : '—'}</span></div>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400" /> PLN Voltage</span><p className="text-lg font-mono font-bold text-emerald-400 mt-1">{currentPln !== null ? `${currentPln.toFixed(1)} V` : '—'}</p><span className="text-[10px] text-zinc-500">{avgPln !== null ? `Avg: ${avgPln.toFixed(1)}V` : '—'}</span></div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-400" /> Genset Voltage</span><p className="text-lg font-mono font-bold text-amber-400 mt-1">{currentGenset !== null ? `${currentGenset.toFixed(1)} V` : '—'}</p><span className="text-[10px] text-zinc-500">{maxGenset !== null ? `Max: ${maxGenset.toFixed(1)}V` : '—'}</span></div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500 flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-indigo-400" /> Battery (AKI)</span><p className="text-lg font-mono font-bold text-indigo-400 mt-1">{currentAki !== null ? `${currentAki.toFixed(1)} V` : '—'}</p><span className="text-[10px] text-zinc-500">{avgAki !== null ? `Avg: ${avgAki.toFixed(1)}V` : '—'}</span></div>
              <div className="bg-zinc-950 p-3 rounded-md border border-zinc-800/60"><span className="text-[10px] uppercase font-semibold text-zinc-500">Controller State</span><p className="text-sm font-mono font-bold text-zinc-200 mt-1.5 truncate">{currentState || 'STANDBY'}</p><span className="text-[10px] text-zinc-500">{points.length} samples</span></div>
            </div>
          )}
        </>
      )}

      {points.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 text-xs pt-1 border-t border-zinc-800/60">
          <div className="flex items-center gap-4">
            {isTS || (!isTS && !isATS) ? (
              <>
                <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-indigo-500" /><span className="text-zinc-300 font-medium">Temperature (°C)</span></div>
                <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-400" /><span className="text-zinc-300 font-medium">Humidity (%)</span></div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-400" /><span className="text-zinc-300 font-medium">PLN Main (V)</span></div>
                <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-amber-400" /><span className="text-zinc-300 font-medium">Genset (V)</span></div>
                <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-indigo-400" /><span className="text-zinc-300 font-medium">Battery AKI (V)</span></div>
              </>
            )}
          </div>
          {(isTS || (!isTS && !isATS)) && (warningThresholdVal || criticalThresholdVal) && (
            <div className="flex items-center gap-3 text-[11px] font-mono text-zinc-400">
              {warningThresholdVal && (<div className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-amber-400 border-b border-dashed border-amber-400" /><span className="text-amber-400/90">Warn: {warningThresholdVal}°C</span></div>)}
              {criticalThresholdVal && (<div className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-red-400 border-b border-dashed border-red-400" /><span className="text-red-400/90">Crit: {criticalThresholdVal}°C</span></div>)}
            </div>
          )}
        </div>
      )}

      {points.length === 0 ? (
        <div className="h-56 flex flex-col items-center justify-center text-center p-6 border border-dashed border-zinc-800 rounded-lg bg-zinc-950/40">
          <Activity className="h-8 w-8 text-zinc-600 mb-2 animate-pulse" />
          <p className="text-sm font-medium text-zinc-300">Collecting telemetry data...</p>
          <p className="text-xs text-zinc-500 mt-1">No historical telemetry records found for device within the {timeRange} window.</p>
        </div>
      ) : (
        <div className="relative select-none">
          <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto overflow-visible cursor-crosshair" onMouseMove={handleMouseMove} onMouseLeave={() => setHoverIndex(null)}>
            <defs><linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6366f1" stopOpacity="0.25" /><stop offset="100%" stopColor="#6366f1" stopOpacity="0.0" /></linearGradient></defs>
            {yTicks.map((t, idx) => {
              const yPos = getY(t);
              return (<g key={idx}><line x1={padding.left} x2={width - padding.right} y1={yPos} y2={yPos} stroke="#27272a" strokeWidth="1" strokeDasharray="2 2" /><text x={padding.left - 8} y={yPos + 3.5} textAnchor="end" className="text-[10px] fill-zinc-500 font-mono">{t.toFixed(0)}</text></g>);
            })}
            {(isTS || (!isTS && !isATS)) && warningThresholdVal !== null && warningThresholdVal >= minY && warningThresholdVal <= maxY && (
              <g><line x1={padding.left} x2={width - padding.right} y1={getY(warningThresholdVal)} y2={getY(warningThresholdVal)} stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="4 4" opacity="0.85" /><text x={width - padding.right} y={getY(warningThresholdVal) - 4} textAnchor="end" className="text-[9px] fill-amber-400 font-mono font-medium">Warn ({warningThresholdVal}°C)</text></g>
            )}
            {(isTS || (!isTS && !isATS)) && criticalThresholdVal !== null && criticalThresholdVal >= minY && criticalThresholdVal <= maxY && (
              <g><line x1={padding.left} x2={width - padding.right} y1={getY(criticalThresholdVal)} y2={getY(criticalThresholdVal)} stroke="#ef4444" strokeWidth="1.5" strokeDasharray="4 4" opacity="0.85" /><text x={width - padding.right} y={getY(criticalThresholdVal) - 4} textAnchor="end" className="text-[9px] fill-red-400 font-mono font-medium">Crit ({criticalThresholdVal}°C)</text></g>
            )}
            {outages.map((o, i) => {
              const x1 = Math.max(padding.left, timeToX(o.start));
              const x2 = Math.min(width - padding.right, timeToX(o.end));
              if (x2 - x1 < 2) return null;
              return (<g key={`outage-${i}`}><rect x={x1} y={padding.top} width={x2 - x1} height={plotHeight} fill="#52525b" opacity="0.25" />{x2 - x1 > 44 && (<text x={(x1 + x2) / 2} y={padding.top + 12} textAnchor="middle" className="text-[9px] fill-zinc-500 font-mono">offline</text>)}</g>);
            })}
            {isTS || (!isTS && !isATS) ? (
              <>
                {tempLine.areaPath && <path d={tempLine.areaPath} fill="url(#tempGradient)" />}
                {humidLine.linePath && <path d={humidLine.linePath} fill="none" stroke="#10b981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />}
                {tempLine.linePath && <path d={tempLine.linePath} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
                {tempLine.isolated.map((d, i) => (<circle key={`iso-t-${i}`} cx={d.x} cy={d.y} r={3} fill="#6366f1" />))}
                {humidLine.isolated.map((d, i) => (<circle key={`iso-h-${i}`} cx={d.x} cy={d.y} r={3} fill="#10b981" />))}
              </>
            ) : (
              <>
                {plnLine.linePath && <path d={plnLine.linePath} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
                {gensetLine.linePath && <path d={gensetLine.linePath} fill="none" stroke="#f59e0b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
                {akiLine.linePath && <path d={akiLine.linePath} fill="none" stroke="#6366f1" strokeWidth="2" strokeDasharray="3 3" strokeLinecap="round" strokeLinejoin="round" />}
                {plnLine.isolated.map((d, i) => (<circle key={`iso-p-${i}`} cx={d.x} cy={d.y} r={3} fill="#10b981" />))}
                {gensetLine.isolated.map((d, i) => (<circle key={`iso-g-${i}`} cx={d.x} cy={d.y} r={3} fill="#f59e0b" />))}
                {akiLine.isolated.map((d, i) => (<circle key={`iso-a-${i}`} cx={d.x} cy={d.y} r={3} fill="#6366f1" />))}
              </>
            )}
            {xTimeTicks.map((tickDate, idx) => { const xPos = padding.left + (idx / 4) * plotWidth; return (<text key={idx} x={xPos} y={height - 8} textAnchor="middle" className="text-[10px] fill-zinc-500 font-mono">{formatAxisTime(tickDate.toISOString(), timeRange)}</text>); })}
            {hoverIndex !== null && points[hoverIndex] && (
              <g>
                <line x1={getX(hoverIndex)} x2={getX(hoverIndex)} y1={padding.top} y2={padding.top + plotHeight} stroke="#a1a1aa" strokeWidth="1" strokeDasharray="3 3" />
                {(isTS || (!isTS && !isATS)) && (<>{typeof points[hoverIndex].temp === 'number' && (<circle cx={getX(hoverIndex)} cy={getY(points[hoverIndex].temp!)} r="5" fill="#6366f1" stroke="#ffffff" strokeWidth="2" />)}{typeof points[hoverIndex].humid === 'number' && (<circle cx={getX(hoverIndex)} cy={getY(points[hoverIndex].humid!)} r="5" fill="#10b981" stroke="#ffffff" strokeWidth="2" />)}</>)}
                {isATS && (<>{typeof points[hoverIndex].pln === 'number' && (<circle cx={getX(hoverIndex)} cy={getY(points[hoverIndex].pln!)} r="5" fill="#10b981" stroke="#ffffff" strokeWidth="2" />)}{typeof points[hoverIndex].genset === 'number' && (<circle cx={getX(hoverIndex)} cy={getY(points[hoverIndex].genset!)} r="5" fill="#f59e0b" stroke="#ffffff" strokeWidth="2" />)}{typeof points[hoverIndex].aki === 'number' && (<circle cx={getX(hoverIndex)} cy={getY(points[hoverIndex].aki!)} r="4" fill="#6366f1" stroke="#ffffff" strokeWidth="2" />)}</>)}
              </g>
            )}
          </svg>
          {hoverIndex !== null && points[hoverIndex] && (
            <div className="absolute pointer-events-none z-20 bg-zinc-900/95 backdrop-blur-md border border-zinc-700 shadow-xl rounded-lg p-2.5 text-xs text-zinc-200" style={{ left: `${(getX(hoverIndex) / width) * 100}%`, top: '10px', transform: hoverIndex > points.length / 2 ? 'translateX(-105%)' : 'translateX(5%)' }}>
              <div className="text-[10px] text-zinc-400 font-mono pb-1 border-b border-zinc-800 mb-1.5 flex items-center gap-1.5"><Activity className="h-3 w-3 text-indigo-400" /><span>{formatTooltipTime(points[hoverIndex].timestamp)}</span></div>
              {(isTS || (!isTS && !isATS)) && (<div className="space-y-1">{typeof points[hoverIndex].temp === 'number' && (<div className="flex items-center justify-between gap-4 font-mono"><span className="text-indigo-400 font-sans text-[11px] flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-indigo-500" /> Temp:</span><span className="font-bold text-zinc-100">{points[hoverIndex].temp?.toFixed(1)} °C</span></div>)}{typeof points[hoverIndex].humid === 'number' && (<div className="flex items-center justify-between gap-4 font-mono"><span className="text-emerald-400 font-sans text-[11px] flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Humidity:</span><span className="font-bold text-zinc-100">{points[hoverIndex].humid?.toFixed(1)} %</span></div>)}</div>)}
              {isATS && (<div className="space-y-1">{typeof points[hoverIndex].pln === 'number' && (<div className="flex items-center justify-between gap-4 font-mono"><span className="text-emerald-400 font-sans text-[11px]">PLN:</span><span className="font-bold text-zinc-100">{points[hoverIndex].pln?.toFixed(1)} V</span></div>)}{typeof points[hoverIndex].genset === 'number' && (<div className="flex items-center justify-between gap-4 font-mono"><span className="text-amber-400 font-sans text-[11px]">Genset:</span><span className="font-bold text-zinc-100">{points[hoverIndex].genset?.toFixed(1)} V</span></div>)}{typeof points[hoverIndex].aki === 'number' && (<div className="flex items-center justify-between gap-4 font-mono"><span className="text-indigo-400 font-sans text-[11px]">Battery:</span><span className="font-bold text-zinc-100">{points[hoverIndex].aki?.toFixed(1)} V</span></div>)}{points[hoverIndex].state && (<div className="flex items-center justify-between gap-4 font-mono pt-1 border-t border-zinc-800/60"><span className="text-zinc-400 font-sans text-[10px]">State:</span><span className="font-semibold text-zinc-200 text-[10px]">{points[hoverIndex].state}</span></div>)}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
export default HistoryChart;
