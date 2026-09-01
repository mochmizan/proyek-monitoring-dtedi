import React from 'react';

export interface PanelGridProps {
  yTicks: number[];
  getYCoord: (val: number) => number;
  paddingLeft: number;
  paddingRight: number;
  width: number;
  unit?: string;
  formatTick?: (val: number) => string;
}

export const PanelGrid: React.FC<PanelGridProps> = ({
  yTicks,
  getYCoord,
  paddingLeft,
  paddingRight,
  width,
  unit = '',
  formatTick,
}) => {
  return (
    <g className="panel-grid select-none">
      {yTicks.map((t, idx) => {
        const yPos = getYCoord(t);
        const label = formatTick
          ? formatTick(t)
          : `${unit ? t.toFixed(unit === 'V' && t % 1 !== 0 ? 1 : 0) : t.toFixed(0)}${unit}`;

        return (
          <g key={`y-grid-${idx}`}>
            <line
              x1={paddingLeft}
              x2={width - paddingRight}
              y1={yPos}
              y2={yPos}
              stroke="#27272a"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
            <text
              x={paddingLeft - 8}
              y={yPos + 3.5}
              textAnchor="end"
              className="text-[10px] fill-zinc-500 font-mono"
            >
              {label}
            </text>
          </g>
        );
      })}
    </g>
  );
};
