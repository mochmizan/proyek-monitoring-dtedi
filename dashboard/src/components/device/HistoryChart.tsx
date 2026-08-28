import { createContext, useMemo, use } from "react";
import { TrendingUp, Activity, TriangleAlert } from "lucide-react";
import { CartesianGrid, ComposedChart, XAxis, YAxis, Line, Area, Brush, ReferenceLine, ReferenceArea } from "recharts";

import type { TelemetryHistoryPoint } from "@/types/api";
import { parseToDate, formatAxisTime, formatTooltipTime, getGapThresholdMs, getOutages, toChartData } from "@/lib/chartUtils";
import type { ChartConfig } from "@/components/ui/chart";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia } from "@/components/ui/empty";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";

// ── Context / provider (Vercel composition, React 19 use) ──────────────────

interface HistoryChartState {
  points: TelemetryHistoryPoint[];
  timeRange: "6h" | "24h" | "7d" | "30d";
  warningThresholdVal: number | null;
  criticalThresholdVal: number | null;
  devType: string;
}
interface HistoryChartActions {
  setTimeRange: (r: HistoryChartState["timeRange"]) => void;
}
interface HistoryChartMeta {
  gapThresholdMs: number;
}

const HistoryChartContext = createContext<{ state: HistoryChartState; actions: HistoryChartActions; meta: HistoryChartMeta } | null>(null);

function HistoryChartProvider({
  children,
  state,
  actions,
  meta,
}: {
  children: React.ReactNode;
  state: HistoryChartState;
  actions: HistoryChartActions;
  meta: HistoryChartMeta;
}) {
  return (
    <TooltipProvider>
      <HistoryChartContext.Provider value={{ state, actions, meta }}>{children}</HistoryChartContext.Provider>
    </TooltipProvider>
  );
}

function useHistoryChart() {
  const v = use(HistoryChartContext);
  if (!v) throw new Error("HistoryChart.* must be inside HistoryChartProvider");
  return v;
}

// ── Explicit variants (no boolean prop drilling) ────────────────────────────

function TSChartVariant() {
  const { state, meta } = useHistoryChart();
  const chartData = useMemo(() => toChartData(state.points, meta.gapThresholdMs), [state.points, meta.gapThresholdMs]);

  const windowHours = state.timeRange === "6h" ? 6 : state.timeRange === "24h" ? 24 : state.timeRange === "7d" ? 7 * 24 : 30 * 24;
  const windowMs = windowHours * 3600 * 1000;
  const latestPointTime =
    state.points.length > 0 && state.points[state.points.length - 1].timestamp
      ? parseToDate(state.points[state.points.length - 1].timestamp).getTime()
      : Date.now();
  const maxTimeMs = !isNaN(latestPointTime) ? latestPointTime : Date.now();
  const minTimeMs = maxTimeMs - windowMs;

  const outages = useMemo(
    () => getOutages(chartData.map((d) => d.ts), minTimeMs, meta.gapThresholdMs),
    [chartData, minTimeMs, meta.gapThresholdMs],
  );

  const warnOutOfRange =
    typeof state.warningThresholdVal === "number" &&
    (state.warningThresholdVal < 15 || state.warningThresholdVal > 30);
  const critOutOfRange =
    typeof state.criticalThresholdVal === "number" &&
    (state.criticalThresholdVal < 15 || state.criticalThresholdVal > 30);
  const showWarnLine =
    typeof state.warningThresholdVal === "number" && state.warningThresholdVal >= 15 && state.warningThresholdVal <= 30;
  const showCritLine =
    typeof state.criticalThresholdVal === "number" && state.criticalThresholdVal >= 15 && state.criticalThresholdVal <= 30;

  const tsConfig = {
    temp: { label: "Temperature", color: "var(--chart-1)" },
    humid: { label: "Humidity", color: "var(--chart-2)" },
  } satisfies ChartConfig;

  return (
    <div className="flex flex-col gap-3">
      <ChartContainer config={tsConfig} className="h-[260px] sm:h-[300px] w-full">
        <ComposedChart data={chartData} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.18} />
              <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
          <XAxis
            dataKey="t"
            tickFormatter={(v: string) => formatAxisTime(v, state.timeRange)}
            tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            yAxisId="temp"
            domain={[15, 30]}
            tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <YAxis
            yAxisId="humid"
            orientation="right"
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <ChartTooltip
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            content={<ChartTooltipContent labelFormatter={(label: any) => formatTooltipTime(String(label ?? ""))} indicator="dot" />}
            cursor={{ strokeDasharray: "3 3" }}
          />
          {showWarnLine && (
            <ReferenceLine
              yAxisId="temp"
              y={state.warningThresholdVal!}
              stroke="var(--chart-3)"
              strokeDasharray="4 4"
              strokeWidth={1.25}
              opacity={0.9}
              label={{
                value: `Warn ${state.warningThresholdVal}°C`,
                position: "right",
                fill: "var(--chart-3)",
                fontSize: 10,
                fontFamily: "var(--font-mono)",
              }}
            />
          )}
          {showCritLine && (
            <ReferenceLine
              yAxisId="temp"
              y={state.criticalThresholdVal!}
              stroke="var(--chart-4)"
              strokeDasharray="4 4"
              strokeWidth={1.25}
              opacity={0.9}
              label={{
                value: `Crit ${state.criticalThresholdVal}°C`,
                position: "right",
                fill: "var(--chart-4)",
                fontSize: 10,
                fontFamily: "var(--font-mono)",
              }}
            />
          )}
          {outages.map((o, i) => (
            <ReferenceArea
              key={i}
              x1={new Date(o.start).toISOString()}
              x2={new Date(o.end).toISOString()}
              yAxisId="temp"
              fill="var(--muted)"
              fillOpacity={0.08}
              strokeOpacity={0}
            />
          ))}
          <Area yAxisId="temp" type="monotone" dataKey="temp" fill="url(#tempGradient)" stroke="none" />
          <Line
            yAxisId="temp"
            type="monotone"
            dataKey="temp"
            stroke="var(--chart-1)"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, strokeWidth: 2 }}
            connectNulls={false}
          />
          <Line
            yAxisId="humid"
            type="monotone"
            dataKey="humid"
            stroke="var(--chart-2)"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls={false}
          />
          {chartData.length > 30 && (
            <Brush
              dataKey="t"
              height={24}
              stroke="var(--border)"
              fill="var(--card)"
              travellerWidth={8}
              tickFormatter={(v: string) => formatAxisTime(v, state.timeRange)}
            />
          )}
        </ComposedChart>
      </ChartContainer>
      {(warnOutOfRange || critOutOfRange) && (
        <div className="flex flex-col gap-2 px-1">
          {warnOutOfRange && (
            <Alert variant="default">
              <TriangleAlert data-icon="inline-start" />
              <AlertTitle>Threshold outside chart range</AlertTitle>
              <AlertDescription>Warning {state.warningThresholdVal}°C is above the 15–30°C display range</AlertDescription>
            </Alert>
          )}
          {critOutOfRange && (
            <Alert variant="default">
              <TriangleAlert data-icon="inline-start" />
              <AlertTitle>Threshold outside chart range</AlertTitle>
              <AlertDescription>
                {typeof state.criticalThresholdVal === "number" && state.criticalThresholdVal > 30
                  ? `Critical ${state.criticalThresholdVal}°C is above the 15–30°C display range`
                  : `Critical ${state.criticalThresholdVal}°C is below the 15–30°C display range`}
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}
    </div>
  );
}

function ATSChartVariant() {
  const { state, meta } = useHistoryChart();
  const chartData = useMemo(() => toChartData(state.points, meta.gapThresholdMs), [state.points, meta.gapThresholdMs]);

  const windowHours = state.timeRange === "6h" ? 6 : state.timeRange === "24h" ? 24 : state.timeRange === "7d" ? 7 * 24 : 30 * 24;
  const windowMs = windowHours * 3600 * 1000;
  const latestPointTime =
    state.points.length > 0 && state.points[state.points.length - 1].timestamp
      ? parseToDate(state.points[state.points.length - 1].timestamp).getTime()
      : Date.now();
  const maxTimeMs = !isNaN(latestPointTime) ? latestPointTime : Date.now();
  const minTimeMs = maxTimeMs - windowMs;

  const outages = useMemo(
    () => getOutages(chartData.map((d) => d.ts), minTimeMs, meta.gapThresholdMs),
    [chartData, minTimeMs, meta.gapThresholdMs],
  );

  const allVals = chartData.flatMap((d) => [d.pln, d.genset, d.aki].filter((v): v is number => typeof v === "number"));
  const rawMax = allVals.length > 0 ? Math.max(...allVals, 250) : 250;
  const yMax = Math.ceil(rawMax * 1.05);

  const atsConfig = {
    pln: { label: "PLN", color: "var(--chart-2)" },
    genset: { label: "Genset", color: "#f59e0b" },
    aki: { label: "Battery", color: "var(--chart-1)" },
  } satisfies ChartConfig;

  return (
    <ChartContainer config={atsConfig} className="h-[260px] sm:h-[300px] w-full">
      <ComposedChart data={chartData} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
        <XAxis
          dataKey="t"
          tickFormatter={(v: string) => formatAxisTime(v, state.timeRange)}
          tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }}
          axisLine={{ stroke: "var(--border)" }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis
          yAxisId="ats"
          domain={[0, yMax]}
          tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <ChartTooltip
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          content={<ChartTooltipContent labelFormatter={(label: any) => formatTooltipTime(String(label ?? ""))} indicator="dot" />}
          cursor={{ strokeDasharray: "3 3" }}
        />
        {outages.map((o, i) => (
          <ReferenceArea
            key={i}
            x1={new Date(o.start).toISOString()}
            x2={new Date(o.end).toISOString()}
            yAxisId="ats"
            fill="var(--muted)"
            fillOpacity={0.08}
            strokeOpacity={0}
          />
        ))}
        <Line
          yAxisId="ats"
          type="monotone"
          dataKey="pln"
          stroke="var(--chart-2)"
          strokeWidth={2.5}
          dot={false}
          activeDot={{ r: 3 }}
          connectNulls={false}
        />
        <Line
          yAxisId="ats"
          type="monotone"
          dataKey="genset"
          stroke="#f59e0b"
          strokeWidth={2.5}
          dot={false}
          activeDot={{ r: 3 }}
          connectNulls={false}
        />
        <Line
          yAxisId="ats"
          type="monotone"
          dataKey="aki"
          stroke="var(--chart-1)"
          strokeWidth={2}
          strokeDasharray="3 3"
          dot={false}
          activeDot={{ r: 3 }}
          connectNulls={false}
        />
        {chartData.length > 30 && (
          <Brush
            dataKey="t"
            height={24}
            stroke="var(--border)"
            fill="var(--card)"
            travellerWidth={8}
            tickFormatter={(v: string) => formatAxisTime(v, state.timeRange)}
          />
        )}
      </ComposedChart>
    </ChartContainer>
  );
}

// ── Compound frame / header ────────────────────────────────────────────────

function HistoryChartFrame({ children }: { children: React.ReactNode }) {
  return <Card className="overflow-hidden">{children}</Card>;
}

function HistoryChartHeader() {
  const { state, actions } = useHistoryChart();
  const points = state.points;
  const isATS = state.devType === "ATS";

  const tempValues = points.map((p) => p.temp).filter((v): v is number => typeof v === "number");
  const humidValues = points.map((p) => p.humid).filter((v): v is number => typeof v === "number");
  const currentTemp = tempValues.length > 0 ? tempValues[tempValues.length - 1] : null;
  const currentHumid = humidValues.length > 0 ? humidValues[humidValues.length - 1] : null;
  const minTemp = tempValues.length > 0 ? Math.min(...tempValues) : null;
  const maxTemp = tempValues.length > 0 ? Math.max(...tempValues) : null;
  const avgTemp = tempValues.length > 0 ? tempValues.reduce((a, b) => a + b, 0) / tempValues.length : null;

  const plnValues = points.map((p) => p.pln).filter((v): v is number => typeof v === "number");
  const gensetValues = points.map((p) => p.genset).filter((v): v is number => typeof v === "number");
  const akiValues = points.map((p) => p.aki).filter((v): v is number => typeof v === "number");
  const currentPln = plnValues.length > 0 ? plnValues[plnValues.length - 1] : null;
  const currentGenset = gensetValues.length > 0 ? gensetValues[gensetValues.length - 1] : null;
  const currentAki = akiValues.length > 0 ? akiValues[akiValues.length - 1] : null;
  const currentState = points.length > 0 ? points[points.length - 1].state : null;

  return (
    <>
      <CardHeader className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <TrendingUp className="size-4 text-primary" data-icon="inline-start" />
              Telemetry History & Trends
            </CardTitle>
            <CardDescription className="text-xs">Real-time telemetry stream across selected monitoring timeframe</CardDescription>
          </div>
          <ToggleGroup
            type="single"
            value={state.timeRange}
            onValueChange={(v) => {
              if (v) actions.setTimeRange(v as HistoryChartState["timeRange"]);
            }}
            variant="outline"
            size="sm"
          >
            <ToggleGroupItem value="6h">6h</ToggleGroupItem>
            <ToggleGroupItem value="24h">24h</ToggleGroupItem>
            <ToggleGroupItem value="7d">7d</ToggleGroupItem>
            <ToggleGroupItem value="30d">30d</ToggleGroupItem>
          </ToggleGroup>
        </div>

        {points.length > 0 && (
          <>
            <Separator />
            {isATS ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-muted-foreground">
                    <span className="size-2 rounded-full bg-[var(--chart-2)]" />
                    PLN Voltage
                  </span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {currentPln !== null ? `${currentPln.toFixed(1)} V` : "—"}
                  </p>
                </div>
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-muted-foreground">
                    <span className="size-2 rounded-full bg-[#f59e0b]" />
                    Genset Voltage
                  </span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {currentGenset !== null ? `${currentGenset.toFixed(1)} V` : "—"}
                  </p>
                </div>
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-muted-foreground">
                    <span className="size-2 rounded-full bg-[var(--chart-1)]" />
                    Battery (AKI)
                  </span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {currentAki !== null ? `${currentAki.toFixed(1)} V` : "—"}
                  </p>
                </div>
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="text-[10px] font-semibold uppercase text-muted-foreground">Controller State</span>
                  <p className="truncate font-mono text-sm font-bold text-card-foreground">{currentState || "STANDBY"}</p>
                  <span className="text-[10px] text-muted-foreground">{points.length} samples</span>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase text-muted-foreground">
                    <span className="size-2 rounded-full bg-[var(--chart-1)]" />
                    Current Temp
                  </span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {currentTemp !== null ? `${currentTemp.toFixed(1)}°C` : "—"}
                  </p>
                  <span className="truncate text-[10px] text-muted-foreground">
                    {currentHumid !== null ? `Humidity: ${currentHumid.toFixed(1)}%` : "—"}
                  </span>
                </div>
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="text-[10px] font-semibold uppercase text-muted-foreground">Min Temp</span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {minTemp !== null ? `${minTemp.toFixed(1)}°C` : "—"}
                  </p>
                </div>
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="text-[10px] font-semibold uppercase text-muted-foreground">Max Temp</span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {maxTemp !== null ? `${maxTemp.toFixed(1)}°C` : "—"}
                  </p>
                </div>
                <div className="flex flex-col gap-1 rounded-md border bg-card p-3">
                  <span className="text-[10px] font-semibold uppercase text-muted-foreground">Average Temp</span>
                  <p className="truncate font-mono text-lg font-bold text-card-foreground">
                    {avgTemp !== null ? `${avgTemp.toFixed(1)}°C` : "—"}
                  </p>
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-4 text-xs">
              <div className="flex flex-wrap items-center gap-4">
                {isATS ? (
                  <>
                    <span className="flex items-center gap-1.5">
                      <span className="size-2.5 rounded-full bg-[var(--chart-2)]" />
                      <span className="font-medium text-muted-foreground">PLN Main (V)</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="size-2.5 rounded-full bg-[#f59e0b]" />
                      <span className="font-medium text-muted-foreground">Genset (V)</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="size-2.5 rounded-full bg-[var(--chart-1)]" />
                      <span className="font-medium text-muted-foreground">Battery AKI (V)</span>
                    </span>
                  </>
                ) : (
                  <>
                    <span className="flex items-center gap-1.5">
                      <span className="size-2.5 rounded-full bg-[var(--chart-1)]" />
                      <span className="font-medium text-muted-foreground">Temperature (°C)</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className="size-2.5 rounded-full bg-[var(--chart-2)]" />
                      <span className="font-medium text-muted-foreground">Humidity (%)</span>
                    </span>
                  </>
                )}
              </div>
              {!isATS && (state.warningThresholdVal !== null || state.criticalThresholdVal !== null) && (
                <div className="flex items-center gap-3 font-mono text-[11px] text-muted-foreground">
                  {state.warningThresholdVal !== null && (
                    <span className="flex items-center gap-1.5">
                      <span className="h-0.5 w-3 bg-[var(--chart-3)]" />
                      <span className="text-[var(--chart-3)]">Warn: {state.warningThresholdVal}°C</span>
                    </span>
                  )}
                  {state.criticalThresholdVal !== null && (
                    <span className="flex items-center gap-1.5">
                      <span className="h-0.5 w-3 bg-[var(--chart-4)]" />
                      <span className="text-[var(--chart-4)]">Crit: {state.criticalThresholdVal}°C</span>
                    </span>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </CardHeader>
      <Separator />
    </>
  );
}

// ── Canvas dispatcher (explicit variants) ──────────────────────────────────

function HistoryChartCanvas() {
  const { state } = useHistoryChart();
  const isATS = state.devType === "ATS";
  return isATS ? <ATSChartVariant /> : <TSChartVariant />;
}

// ── Public wrapper (compat with device.$deviceId.tsx) ───────────────────────

interface TelemetryChartProps {
  points: TelemetryHistoryPoint[];
  devType: string;
  timeRange: "6h" | "24h" | "7d" | "30d";
  setTimeRange: (r: "6h" | "24h" | "7d" | "30d") => void;
  warningThresholdVal: number | null;
  criticalThresholdVal: number | null;
}

export function HistoryChart({
  points,
  devType,
  timeRange,
  setTimeRange,
  warningThresholdVal,
  criticalThresholdVal,
}: TelemetryChartProps) {
  const pointTimes = useMemo(() => points.map((p) => (p.timestamp ? parseToDate(p.timestamp).getTime() : null) as number | null), [points]);
  const gapThresholdMs = useMemo(() => getGapThresholdMs(pointTimes), [pointTimes]);

  // Empty — shadcn Empty, not border-dashed div
  if (points.length === 0) {
    return (
      <Card className="overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <TrendingUp className="size-4 text-primary" data-icon="inline-start" />
              Telemetry History & Trends
            </CardTitle>
            <CardDescription className="text-xs">Real-time telemetry stream across selected monitoring timeframe</CardDescription>
          </div>
          <ToggleGroup type="single" value={timeRange} onValueChange={(v) => v && setTimeRange(v as TelemetryChartProps["timeRange"])} variant="outline" size="sm">
            <ToggleGroupItem value="6h">6h</ToggleGroupItem>
            <ToggleGroupItem value="24h">24h</ToggleGroupItem>
            <ToggleGroupItem value="7d">7d</ToggleGroupItem>
            <ToggleGroupItem value="30d">30d</ToggleGroupItem>
          </ToggleGroup>
        </CardHeader>
        <CardContent>
          <Empty className="border border-dashed">
            <EmptyMedia>
              <Activity className="size-8 text-muted-foreground" data-icon="inline-start" />
            </EmptyMedia>
            <EmptyHeader>
              <EmptyTitle>Collecting telemetry…</EmptyTitle>
              <EmptyDescription>No history within {timeRange}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </CardContent>
      </Card>
    );
  }

  return (
    <HistoryChartProvider
      state={{ points, timeRange, warningThresholdVal, criticalThresholdVal, devType }}
      actions={{ setTimeRange }}
      meta={{ gapThresholdMs }}
    >
      <HistoryChartFrame>
        <HistoryChartHeader />
        <CardContent className="pt-4">
          <HistoryChartCanvas />
        </CardContent>
        <div className="px-6 pb-2">
          <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
            <Badge variant="outline" className="font-mono">
              {points.length} samples
            </Badge>
            <Separator orientation="vertical" className="h-3" />
            <span className="truncate">
              Range {timeRange} · gap {Math.round(gapThresholdMs / 60000)} min
            </span>
          </div>
        </div>
      </HistoryChartFrame>
    </HistoryChartProvider>
  );
}

export default HistoryChart;

// Compound export per D8 / tasks 4.3
export const HistoryChartCompound = {
  Provider: HistoryChartProvider,
  Frame: HistoryChartFrame,
  Header: HistoryChartHeader,
  Canvas: HistoryChartCanvas,
  TS: TSChartVariant,
  ATS: ATSChartVariant,
};
