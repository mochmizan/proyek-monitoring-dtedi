import React from 'react';
import { formatAxisTime } from '../../../lib/chartUtils';

export interface PanelTimeAxisProps {
  xTimeTicks: Date[];
  timeRange: string;
  paddingLeft: number;
  plotWidth: number;
  height: number;
  offsetY?: number;
}

export const PanelTimeAxis: React.FC<PanelTimeAxisProps> = ({
  xTimeTicks,
  timeRange,
  paddingLeft,
  plotWidth,
  height,
  offsetY = 6,
}) => {
  if (!xTimeTicks || xTimeTicks.length === 0) return null;

  return (
    <g className="panel-time-axis select-none pointer-events-none">
      {xTimeTicks.map((tickDate, idx) => {
        const xPos = paddingLeft + (idx / (xTimeTicks.length - 1)) * plotWidth;
        return (
          <text
            key={`x-tick-${idx}`}
            x={xPos}
            y={height - offsetY}
            textAnchor="middle"
            className="text-[10px] fill-zinc-500 font-mono"
          >
            {formatAxisTime(tickDate.toISOString(), timeRange)}
          </text>
        );
      })}
    </g>
  );
};
