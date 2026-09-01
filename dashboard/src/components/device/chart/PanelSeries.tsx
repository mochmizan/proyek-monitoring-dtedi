import React from 'react';
import type { TelemetryHistoryPoint } from '../../../types/api';
import type { SeriesConfig } from './types';
import { buildPathSegments } from './chartMath';

export interface PanelSeriesProps {
  points: TelemetryHistoryPoint[];
  series: SeriesConfig[];
  getXCoord: (idx: number) => number;
  getYCoord: (val: number) => number;
  plotBottomY: number;
  pointTimes: (number | null)[];
  gapThresholdMs: number;
}

export const PanelSeries: React.FC<PanelSeriesProps> = ({
  points,
  series,
  getXCoord,
  getYCoord,
  plotBottomY,
  pointTimes,
  gapThresholdMs,
}) => {
  return (
    <g className="panel-series select-none">
      <defs>
        {series
          .filter((s) => s.isArea)
          .map((s) => {
            const gradId = s.gradientId || `grad-${s.id}`;
            return (
              <linearGradient key={gradId} id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity="0.25" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0.0" />
              </linearGradient>
            );
          })}
      </defs>

      {series.map((s) => {
        if (s.visible === false) return null;

        const { linePath, areaPath, isolated } = buildPathSegments(
          points,
          s.getValue,
          getXCoord,
          getYCoord,
          plotBottomY,
          pointTimes,
          gapThresholdMs
        );

        const gradId = s.gradientId || `grad-${s.id}`;

        return (
          <g key={`series-${s.id}`}>
            {s.isArea && areaPath && (
              <path d={areaPath} fill={`url(#${gradId})`} />
            )}
            {linePath && (
              <path
                d={linePath}
                fill="none"
                stroke={s.color}
                strokeWidth={s.strokeWidth || 2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
                data-testid={s.testId}
              />
            )}
            {isolated.map((d, i) => (
              <circle
                key={`iso-${s.id}-${i}`}
                cx={d.x}
                cy={d.y}
                r={3}
                fill={s.color}
              />
            ))}
          </g>
        );
      })}
    </g>
  );
};
