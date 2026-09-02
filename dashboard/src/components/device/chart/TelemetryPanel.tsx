import React from 'react';
import { cn } from '../../../lib/utils';
import type { TelemetryHistoryPoint } from '../../../types/api';
import type { PanelConfig, TimeWindowContext } from './types';
import { getY, findClosestIndexByX } from './chartMath';
import { PanelGrid } from './PanelGrid';
import { PanelThresholds } from './PanelThresholds';
import { PanelOutages } from './PanelOutages';
import { PanelSeries } from './PanelSeries';
import { PanelTimeAxis } from './PanelTimeAxis';
import { PanelCrosshair } from './PanelCrosshair';

export interface TelemetryPanelProps {
  panel: PanelConfig;
  points: TelemetryHistoryPoint[];
  timeWindow: TimeWindowContext;
  hoverIndex: number | null;
  onHoverIndexChange: (index: number | null) => void;
  onToggleSeries: (seriesId: string) => void;
  formatTick?: (val: number) => string;
}

export const TelemetryPanel: React.FC<TelemetryPanelProps> = ({
  panel,
  points,
  timeWindow,
  hoverIndex,
  onHoverIndexChange,
  onToggleSeries,
  formatTick,
}) => {
  const padding = panel.padding || {
    top: 20,
    right: timeWindow.paddingRight,
    bottom: panel.showTimeAxis !== false ? 25 : 15,
    left: timeWindow.paddingLeft,
  };

  const plotHeight = panel.height - padding.top - padding.bottom;
  const plotBottomY = padding.top + plotHeight;

  const getYCoord = (val: number) => {
    return getY(val, panel.minY, panel.maxY, plotHeight, padding.top);
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (points.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const svgX = (mouseX / rect.width) * timeWindow.width;

    const closestIdx = findClosestIndexByX(points.length, timeWindow.getX, svgX);
    onHoverIndexChange(closestIdx);
  };

  const handleMouseLeave = () => {
    onHoverIndexChange(null);
  };

  return (
    <div
      className="bg-zinc-950/50 border border-zinc-800/80 rounded-lg p-4 space-y-3"
      data-testid={panel.testId}
    >
      {/* Panel Header: Title & Interactive Legend Toggles / Threshold Pills */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
          {panel.title}
        </span>

        <div className="flex flex-wrap items-center gap-2">
          {/* Auto Scale Toggles */}
          {panel.series.map((s) => {
            const isActive = s.active !== false;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => onToggleSeries(s.id)}
                aria-pressed={isActive}
                data-testid={s.toggleTestId}
                className={cn(
                  "px-2.5 py-1 text-xs font-semibold rounded-md border transition-all cursor-pointer inline-flex items-center gap-1.5",
                  isActive
                    ? "text-blue-400 bg-blue-500/10 border-blue-500/25"
                    : "bg-zinc-950/60 border-zinc-800 text-zinc-500 hover:text-zinc-400"
                )}
              >
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    isActive ? "bg-blue-400" : "bg-zinc-600"
                  )}
                />
                <span>{isActive ? '✓ Auto Scale' : 'Auto Scale'}</span>
              </button>
            );
          })}

          {/* Threshold Tags if any */}
          {panel.thresholds && panel.thresholds.length > 0 && (
            <div className="flex items-center gap-2 text-[11px] font-mono text-zinc-400">
              {panel.thresholds.map((th, idx) => (
                <span
                  key={idx}
                  className={cn(
                    "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border",
                    th.type === 'critical'
                      ? "bg-red-500/10 text-red-400 border-red-500/20"
                      : th.type === 'warning'
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  )}
                  style={
                    th.color && !th.type
                      ? {
                          backgroundColor: `${th.color}15`,
                          borderColor: `${th.color}30`,
                          color: th.color,
                        }
                      : undefined
                  }
                >
                  <span
                    className={cn(
                      "h-1 w-2 border-b border-dashed",
                      th.type === 'critical'
                        ? "border-red-400"
                        : th.type === 'warning'
                        ? "border-amber-400"
                        : "border-emerald-400"
                    )}
                    style={th.color && !th.type ? { borderColor: th.color } : undefined}
                  />
                  {th.badgeLabel || th.label}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* SVG Viewport */}
      <div className="relative">
        <svg
          viewBox={`0 0 ${timeWindow.width} ${panel.height}`}
          className="w-full h-auto overflow-visible cursor-crosshair"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          {/* Y Grid & Tick Labels */}
          <PanelGrid
            yTicks={panel.yTicks}
            getYCoord={getYCoord}
            paddingLeft={padding.left}
            paddingRight={padding.right}
            width={timeWindow.width}
            unit={panel.unit}
            formatTick={formatTick}
          />

          {/* Outages / Gaps */}
          <PanelOutages
            outages={timeWindow.outages}
            timeToX={timeWindow.timeToX}
            paddingLeft={padding.left}
            paddingRight={padding.right}
            paddingTop={padding.top}
            plotHeight={plotHeight}
            width={timeWindow.width}
          />

          {/* Threshold Lines */}
          <PanelThresholds
            thresholds={panel.thresholds}
            minY={panel.minY}
            maxY={panel.maxY}
            getYCoord={getYCoord}
            paddingLeft={padding.left}
            paddingRight={padding.right}
            width={timeWindow.width}
          />

          {/* Telemetry Series Paths */}
          <PanelSeries
            points={points}
            series={panel.series}
            getXCoord={timeWindow.getX}
            getYCoord={getYCoord}
            plotBottomY={plotBottomY}
            pointTimes={timeWindow.pointTimes}
            gapThresholdMs={timeWindow.gapThresholdMs}
          />

          {/* Bottom X Time Axis */}
          {panel.showTimeAxis !== false && (
            <PanelTimeAxis
              xTimeTicks={timeWindow.xTimeTicks}
              timeRange={timeWindow.timeRange}
              paddingLeft={padding.left}
              plotWidth={timeWindow.plotWidth}
              height={panel.height}
              offsetY={6}
            />
          )}

          {/* Crosshair on Hover */}
          <PanelCrosshair
            hoverIndex={hoverIndex}
            points={points}
            series={panel.series}
            getXCoord={timeWindow.getX}
            getYCoord={getYCoord}
            paddingTop={padding.top}
            plotHeight={plotHeight}
            testId={panel.crosshairTestId}
          />
        </svg>
      </div>
    </div>
  );
};
