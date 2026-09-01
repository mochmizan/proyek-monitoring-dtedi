import React, { useState, useMemo } from 'react';
import { Activity } from 'lucide-react';
import type { TelemetryHistoryPoint } from '../../../types/api';
import type { PanelConfig, TimeRange, TimeWindowContext } from './types';
import { timeToX, getOutages } from './chartMath';
import { parseToDate, formatTooltipTime, getGapThresholdMs } from '../../../lib/chartUtils';
import { TelemetryPanel } from './TelemetryPanel';

export interface MultiPanelChartContainerProps {
  panels: PanelConfig[];
  points: TelemetryHistoryPoint[];
  timeRange: TimeRange;
  onToggleSeries: (seriesId: string) => void;
  containerTestId?: string;
  tooltipTestId?: string;
  formatTick?: (val: number) => string;
}

export const MultiPanelChartContainer: React.FC<MultiPanelChartContainerProps> = ({
  panels,
  points,
  timeRange,
  onToggleSeries,
  containerTestId,
  tooltipTestId,
  formatTick,
}) => {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const width = 800;
  const paddingLeft = 45;
  const paddingRight = 35;
  const plotWidth = width - paddingLeft - paddingRight;

  const windowHours =
    timeRange === '6h' ? 6 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 * 24 : 30 * 24;
  const windowMs = windowHours * 3600 * 1000;

  const latestPointTime =
    points.length > 0 && points[points.length - 1].timestamp
      ? parseToDate(points[points.length - 1].timestamp).getTime()
      : Date.now();
  const maxTimeMs = !isNaN(latestPointTime) ? latestPointTime : Date.now();
  const minTimeMs = maxTimeMs - windowMs;

  const pointTimes: (number | null)[] = useMemo(() => {
    return points.map((p) => {
      const t = p.timestamp ? parseToDate(p.timestamp).getTime() : NaN;
      return isNaN(t) ? null : t;
    });
  }, [points]);

  const gapThresholdMs = useMemo(() => getGapThresholdMs(pointTimes), [pointTimes]);
  const outages = useMemo(
    () => getOutages(pointTimes, minTimeMs, maxTimeMs, gapThresholdMs),
    [pointTimes, minTimeMs, maxTimeMs, gapThresholdMs]
  );

  const timeToXCoord = (tMs: number) => {
    return timeToX(tMs, minTimeMs, maxTimeMs, plotWidth, paddingLeft);
  };

  const getX = (index: number) => {
    const pt = points[index];
    const t = pt && pt.timestamp ? parseToDate(pt.timestamp).getTime() : NaN;
    if (isNaN(t)) {
      if (points.length <= 1) return paddingLeft + plotWidth / 2;
      return paddingLeft + (index / (points.length - 1)) * plotWidth;
    }
    return timeToXCoord(t);
  };

  const xTimeTicks = useMemo(() => {
    return [0, 1, 2, 3, 4].map((i) => new Date(minTimeMs + (i / 4) * (maxTimeMs - minTimeMs)));
  }, [minTimeMs, maxTimeMs]);

  const timeWindow: TimeWindowContext = {
    width,
    plotWidth,
    minTimeMs,
    maxTimeMs,
    paddingLeft,
    paddingRight,
    timeRange,
    pointTimes,
    outages,
    xTimeTicks,
    timeToX: timeToXCoord,
    getX,
  };

  const hoveredPoint = hoverIndex !== null && points[hoverIndex] ? points[hoverIndex] : null;

  // Flatten all series across panels to check active visible values
  const allVisibleSeries = panels.flatMap((p) => p.series.filter((s) => s.visible !== false));

  return (
    <div className="relative select-none space-y-6" data-testid={containerTestId}>
      {/* Aligned Floating Hover Tooltip */}
      {hoveredPoint && (
        <div
          className="absolute pointer-events-none z-30 bg-zinc-900/95 backdrop-blur-md border border-zinc-700 shadow-xl rounded-lg p-3 text-xs text-zinc-200"
          style={{
            left: `${(getX(hoverIndex!) / width) * 100}%`,
            top: '0px',
            transform: hoverIndex! > points.length / 2 ? 'translateX(-105%)' : 'translateX(5%)',
          }}
          data-testid={tooltipTestId}
        >
          <div className="text-[10px] text-zinc-400 font-mono pb-1 border-b border-zinc-800 mb-2 flex items-center gap-1.5">
            <Activity className="h-3 w-3 text-indigo-400" />
            <span>{formatTooltipTime(hoveredPoint.timestamp)}</span>
          </div>

          <div className="space-y-1.5 min-w-[140px]">
            {allVisibleSeries.map((s) => {
              const val = s.getValue(hoveredPoint);
              if (typeof val !== 'number' || isNaN(val)) return null;
              const labelText = s.tooltipLabel || `${s.label}:`;

              return (
                <div key={s.id} className="flex items-center justify-between gap-4 font-mono">
                  <span className="font-sans text-[11px] flex items-center gap-1" style={{ color: s.color }}>
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
                    {labelText}
                  </span>
                  <span className="font-bold text-zinc-100">
                    {val.toFixed(1)} {s.unit || ''}
                  </span>
                </div>
              );
            })}

            {hoveredPoint.state && (
              <div className="flex items-center justify-between gap-4 font-mono pt-1 border-t border-zinc-800/60">
                <span className="text-zinc-400 font-sans text-[10px]">State:</span>
                <span className="font-semibold text-zinc-200 text-[10px]">{hoveredPoint.state}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Render Stacked Panels */}
      {panels.map((panel) => (
        <TelemetryPanel
          key={panel.id}
          panel={panel}
          points={points}
          timeWindow={timeWindow}
          hoverIndex={hoverIndex}
          onHoverIndexChange={setHoverIndex}
          onToggleSeries={onToggleSeries}
          formatTick={formatTick}
        />
      ))}
    </div>
  );
};
