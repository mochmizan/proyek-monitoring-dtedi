import React from 'react';

export interface PanelOutagesProps {
  outages: { start: number; end: number }[];
  timeToX: (tMs: number) => number;
  paddingLeft: number;
  paddingRight: number;
  paddingTop: number;
  plotHeight: number;
  width: number;
}

export const PanelOutages: React.FC<PanelOutagesProps> = ({
  outages,
  timeToX,
  paddingLeft,
  paddingRight,
  paddingTop,
  plotHeight,
  width,
}) => {
  if (!outages || outages.length === 0) return null;

  return (
    <g className="panel-outages select-none pointer-events-none">
      {outages.map((o, i) => {
        const x1 = Math.max(paddingLeft, timeToX(o.start));
        const x2 = Math.min(width - paddingRight, timeToX(o.end));
        if (x2 - x1 < 2) return null;
        const outageMinutes = Math.round((o.end - o.start) / 60000);

        return (
          <g key={`outage-${i}`} className="pointer-events-auto">
            <title>hub offline - no samples ({outageMinutes} min gap)</title>
            <rect
              x={x1}
              y={paddingTop}
              width={x2 - x1}
              height={plotHeight}
              fill="#52525b"
              opacity="0.18"
            />
            {x2 - x1 > 60 && (
              <text
                x={(x1 + x2) / 2}
                y={paddingTop + 12}
                textAnchor="middle"
                className="text-[9px] fill-zinc-400 font-mono"
              >
                hub offline - no samples
              </text>
            )}
            {x2 - x1 > 24 && x2 - x1 <= 60 && (
              <text
                x={(x1 + x2) / 2}
                y={paddingTop + 12}
                textAnchor="middle"
                className="text-[9px] fill-zinc-400 font-mono"
              >
                offline
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
};
