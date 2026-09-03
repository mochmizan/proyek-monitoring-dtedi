import { cn } from '../lib/utils';

interface SparklineProps {
  values: (number | null | undefined)[];
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline({ values, width = 96, height = 28, className }: SparklineProps) {
  const validPoints = values
    .map((v, i) => (v !== null && v !== undefined && Number.isFinite(v) ? { val: v, i } : null))
    .filter((p): p is { val: number; i: number } => p !== null);

  if (validPoints.length < 2 || values.length < 2) {
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

  const min = Math.min(...validPoints.map((p) => p.val));
  const max = Math.max(...validPoints.map((p) => p.val));
  const range = max - min || 1;
  const stepX = width / (values.length - 1);

  // Group into contiguous segments of valid points
  const segments: { x: number; y: number }[][] = [];
  let currentSegment: { x: number; y: number }[] = [];

  values.forEach((v, i) => {
    if (v !== null && v !== undefined && Number.isFinite(v)) {
      const x = i * stepX;
      const y = height - 3 - ((v - min) / range) * (height - 6);
      currentSegment.push({ x, y });
    } else {
      if (currentSegment.length > 0) {
        segments.push(currentSegment);
        currentSegment = [];
      }
    }
  });
  if (currentSegment.length > 0) {
    segments.push(currentSegment);
  }

  const lastValid = validPoints[validPoints.length - 1];
  const lastX = lastValid.i * stepX;
  const lastY = height - 3 - ((lastValid.val - min) / range) * (height - 6);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      className={cn('shrink-0', className)}
    >
      {segments.map((seg, idx) => {
        if (seg.length === 1) {
          return (
            <circle
              key={`dot-${idx}`}
              cx={seg[0].x}
              cy={seg[0].y}
              r="1.5"
              className="fill-indigo-400"
            />
          );
        }
        const pointsStr = seg.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
        return (
          <polyline
            key={`seg-${idx}`}
            points={pointsStr}
            fill="none"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="stroke-indigo-400"
          />
        );
      })}
      <circle cx={lastX} cy={lastY} r="2" className="fill-indigo-400" />
    </svg>
  );
}
