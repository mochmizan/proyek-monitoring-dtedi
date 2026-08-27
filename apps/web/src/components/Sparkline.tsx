import { cn } from '../lib/utils';

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({ values, width = 96, height = 28, className }: SparklineProps) {
  const points = values.filter((v) => Number.isFinite(v));

  if (points.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden="true"
        className={className}
      >
        <line
          x1="0"
          y1={height - 1}
          x2={width}
          y2={height - 1}
          strokeWidth="1"
          strokeDasharray="2 3"
          className="stroke-zinc-700"
        />
      </svg>
    );
  }

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const stepX = width / (points.length - 1);

  const coords = points.map((value, i) => ({
    x: i * stepX,
    y: height - 3 - ((value - min) / range) * (height - 6),
  }));
  const path = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
  const last = coords[coords.length - 1];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      className={cn('shrink-0', className)}
    >
      <polyline
        points={path}
        fill="none"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-indigo-400"
      />
      <circle cx={last.x} cy={last.y} r="2" className="fill-indigo-400" />
    </svg>
  );
}
