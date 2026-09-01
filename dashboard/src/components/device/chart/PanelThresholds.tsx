import React from 'react';
import type { ThresholdGuide } from './types';

export interface PanelThresholdsProps {
  thresholds?: ThresholdGuide[];
  minY: number;
  maxY: number;
  getYCoord: (val: number) => number;
  paddingLeft: number;
  paddingRight: number;
  width: number;
}

export const PanelThresholds: React.FC<PanelThresholdsProps> = ({
  thresholds,
  minY,
  maxY,
  getYCoord,
  paddingLeft,
  paddingRight,
  width,
}) => {
  if (!thresholds || thresholds.length === 0) return null;

  return (
    <g className="panel-thresholds select-none">
      {thresholds.map((th, idx) => {
        if (typeof th.value !== 'number' || isNaN(th.value)) return null;
        if (th.value < minY || th.value > maxY) return null;

        const yPos = getYCoord(th.value);
        const strokeColor = th.color || (th.type === 'critical' ? '#ef4444' : '#f59e0b');
        const textColor = th.type === 'critical' ? 'fill-red-400' : 'fill-amber-400';

        return (
          <g key={`threshold-${th.type || idx}`} data-testid={th.testId}>
            <line
              x1={paddingLeft}
              x2={width - paddingRight}
              y1={yPos}
              y2={yPos}
              stroke={strokeColor}
              strokeWidth="1.5"
              strokeDasharray={th.dashed !== false ? '4 4' : undefined}
              opacity="0.85"
            />
            <text
              x={width - paddingRight}
              y={yPos - 4}
              textAnchor="end"
              className={`text-[9px] ${textColor} font-mono font-medium`}
            >
              {th.label}
            </text>
          </g>
        );
      })}
    </g>
  );
};
