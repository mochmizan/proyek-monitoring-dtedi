import React from 'react';
import type { TelemetryHistoryPoint } from '../../../types/api';
import type { SeriesConfig } from './types';

export interface PanelCrosshairProps {
  hoverIndex: number | null;
  points: TelemetryHistoryPoint[];
  series: SeriesConfig[];
  getXCoord: (idx: number) => number;
  getYCoord: (val: number) => number;
  paddingTop: number;
  plotHeight: number;
  testId?: string;
}

export const PanelCrosshair: React.FC<PanelCrosshairProps> = ({
  hoverIndex,
  points,
  series,
  getXCoord,
  getYCoord,
  paddingTop,
  plotHeight,
  testId,
}) => {
  if (hoverIndex === null || !points[hoverIndex]) return null;

  const currentPoint = points[hoverIndex];
  const xPos = getXCoord(hoverIndex);

  return (
    <g className="panel-crosshair pointer-events-none select-none" data-testid={testId}>
      <line
        x1={xPos}
        x2={xPos}
        y1={paddingTop}
        y2={paddingTop + plotHeight}
        stroke="#a1a1aa"
        strokeWidth="1"
        strokeDasharray="3 3"
      />
      {series.map((s) => {
        if (s.visible === false) return null;
        const val = s.getValue(currentPoint);
        if (typeof val !== 'number' || isNaN(val)) return null;

        const yPos = getYCoord(val);
        return (
          <circle
            key={`crosshair-dot-${s.id}`}
            cx={xPos}
            cy={yPos}
            r="4.5"
            fill={s.color}
            stroke="#ffffff"
            strokeWidth="2"
          />
        );
      })}
    </g>
  );
};
