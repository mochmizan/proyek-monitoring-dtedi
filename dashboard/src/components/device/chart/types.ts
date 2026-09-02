import type { TelemetryHistoryPoint } from '../../../types/api';

export type TimeRange = '6h' | '24h' | '7d' | '30d';

export interface SeriesConfig {
  id: string;
  label: string;
  tooltipLabel?: string;
  color: string;
  getValue: (p: TelemetryHistoryPoint) => number | null | undefined;
  unit?: string;
  isArea?: boolean;
  gradientId?: string;
  strokeWidth?: number;
  testId?: string;
  toggleTestId?: string;
  visible?: boolean;
  active?: boolean;
}

export interface ThresholdGuide {
  value: number;
  label: string;
  badgeLabel?: string;
  color: string;
  dashed?: boolean;
  testId?: string;
  type?: 'warning' | 'critical';
}

export interface PanelConfig {
  id: string;
  title: string;
  unit: string;
  height: number;
  padding?: {
    top: number;
    right: number;
    bottom: number;
    left: number;
  };
  minY: number;
  maxY: number;
  yTicks: number[];
  series: SeriesConfig[];
  thresholds?: ThresholdGuide[];
  showTimeAxis?: boolean;
  testId?: string;
  crosshairTestId?: string;
}

export interface TimeWindowContext {
  width: number;
  plotWidth: number;
  minTimeMs: number;
  maxTimeMs: number;
  paddingLeft: number;
  paddingRight: number;
  timeRange: TimeRange;
  pointTimes: (number | null)[];
  gapThresholdMs: number;
  outages: { start: number; end: number }[];
  xTimeTicks: Date[];
  timeToX: (tMs: number) => number;
  getX: (index: number) => number;
}

export interface HoverState {
  hoverIndex: number | null;
  hoverSvgX: number | null;
}

export interface TelemetryChartProps {
  points: TelemetryHistoryPoint[];
  devType: string;
  timeRange: TimeRange;
  setTimeRange: (r: TimeRange) => void;
  warningThresholdVal?: number | null;
  criticalThresholdVal?: number | null;
  isFetching?: boolean;
  onRefresh?: () => void;
  dataUpdatedAt?: number | Date | string | null;
}
