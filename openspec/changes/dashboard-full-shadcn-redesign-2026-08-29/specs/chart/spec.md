# Spec: chart

## Purpose

Dual-Y telemetry chart for TS/AC/ATS device history that makes temperature drift legible, keeps humidity on its natural 0-100 scale, anchors thresholds to temperature, and renders gaps as broken lines with faint overlay rather than opaque blocks. Consumes `GET /api/iot/history?dev_id=&range=` via `useDeviceHistory(deviceId, range)` and `lib/chartUtils.toChartData`.

## ADDED Requirements

### Requirement: Chart container, composition, and responsivity

The system SHALL render telemetry history as a `ChartContainer` + `ComposedChart` (Recharts) via `@/components/ui/chart`, inside `HistoryChart.Frame` (Card) `HistoryChartProvider`, with `ResponsiveContainer` behavior, `CartesianGrid vertical=false`, and semantic `--border`/`--muted-foreground` strokes; there SHALL be no fixed `width=800 height=260` SVG viewBox.

#### Scenario: Container present

- **WHEN** `components/device/HistoryChart.tsx` is inspected after the change
- **THEN** it imports `{ ChartContainer, ChartTooltip, ChartTooltipContent }` from `@/components/ui/chart` and `{ ComposedChart, CartesianGrid, XAxis, YAxis, Line, Area, Brush, ReferenceLine, ReferenceArea }` from `recharts`, and the rendered subtree contains `<ChartContainer config={…} className="h-[260px] w-full"><ComposedChart`

#### Scenario: Responsive and grid

- **WHEN** the chart renders at 320px viewport width
- **THEN** it fills 100% width without horizontal scroll, `CartesianGrid` shows only horizontal dashed lines (`strokeDasharray="3 3"` in `--border` at `0.5 opacity`), no manual `viewBox="0 0 800 260"` remains

### Requirement: Dual YAxis domains — temp left 15-30°C, humid right 0-100%

The TS chart SHALL expose two `YAxis` axes: left `yAxisId="temp"` with `domain={[15,30]}` (or dynamic clamp `[min-2, max+2]` constrained to `[15,30]` if provided) and right `yAxisId="humid"` with `domain={[0,100]}` and `tickFormatter (v)=>`${v}%``. ATS chart uses single left axis `domain={[0, ceil(max*1.05)]}`. Both axes SHALL use `Fragment Mono` ticks.

#### Scenario: Dual axes defined

- **WHEN** `TSChartVariant` renders inside `HistoryChartProvider` with TS `devType`
- **THEN** the JSX contains `<YAxis yAxisId="temp" domain={[15,30]} … width={36} />` and `<YAxis yAxisId="humid" orientation="right" domain={[0,100]} tickFormatter={(v)=>`${v}%`} … width={40} />` and `humid` line carries `yAxisId="humid"`

#### Scenario: Temp variation becomes legible

- **WHEN** data contains `temp` 25.0 → 27.0 across 24h with `humid` 60-75 flat
- **THEN** a 2°C swing occupies ~`(2/15)*260 ≈ 35%` of vertical space (vs ~11px before), visibly diagonal, not flat; hum line floats independently 60-75 on its own scale

#### Scenario: Ticks style

- **WHEN** Y axes render ticks
- **THEN** each `YAxis` prop includes `tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }}` and `axisLine={false} tickLine={false}`

### Requirement: Lines — hairline trace signature

The system SHALL render temperature `Line yAxisId="temp"` with `stroke="var(--chart-1)" strokeWidth={1.5} type="monotone" dot={false} activeDot={{ r: 3, strokeWidth: 2 }} connectNulls={false}`, humidity `Line yAxisId="humid"` with `stroke="var(--chart-2)" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls={false}`, ATS `pln` emerald `2.5`, `genset` amber `2.5`, `aki` indigo dashed `3 3` `2`, plus a hairline area gradient for temperature `Area yAxisId="temp" fill="url(#tempGradient)"` where gradient is `0% 0.18 → 100% 0.02` in current line color.

#### Scenario: Hairline present

- **WHEN** `TSChartVariant` DOM is inspected
- **THEN** there are two `<Line>` elements with `strokeWidth="1.5"` and `dot={false}`, one `Area` with `fill="url(#tempGradient)"` and the `linearGradient#tempGradient` definition, and zero `strokeWidth="2.5"` on temp/humid

#### Scenario: ATS variant lines

- **WHEN** `ATSChartVariant` renders with sample ATS points `{ pln: 210, genset: 220, aki: 13.6 }`
- **THEN** it renders three `Line`s with `dataKey` `pln`/`genset`/`aki`, `stroke` `var(--chart-2)` / `#f59e0b` / `var(--chart-1)`, `strokeDasharray="3 3"` only on `aki`, and all `connectNulls={false}`

### Requirement: Thresholds anchored to left (temp) axis as ReferenceLine

When `warningThresholdVal` or `criticalThresholdVal` is a finite number in `[15,30]`, the system SHALL render `ReferenceLine yAxisId="temp"` at that `y`, with `stroke="var(--chart-3)"` (warn amber) / `var(--chart-4)` (critical red), `strokeDasharray="4 4"`, `strokeWidth={1.25}`, `opacity={0.9}`, and `label` with `font-mono 10` reading `Warn {v}°C` / `Crit {v}°C`. When outside `[15,30]`, no line is rendered and an `Alert` fallback is shown instead.

#### Scenario: Threshold inside domain

- **WHEN** `TSChartVariant` renders with `warningThresholdVal=28` and `criticalThresholdVal=30`
- **THEN** there are two `ReferenceLine` components each with `yAxisId="temp"`, `strokeDasharray="4 4"`, and `label={{ value: "Warn 28°C" }}` / `"Crit 30°C"` anchored right, font `var(--font-mono)` `10`

#### Scenario: Threshold outside domain shows Alert not line

- **WHEN** thresholds are `warningThresholdVal=35` (above 30)
- **THEN** zero `ReferenceLine` renders for that threshold and an `Alert variant="default"` subtree with `AlertTitle "Threshold outside chart range"` and `AlertDescription "Warning 35°C is above the 15–30°C display range"` is present alongside the chart (not inside `ComposedChart`)

### Requirement: Gaps — null breaks + ReferenceArea

Any gap exceeding `gapThresholdMs` (`getGapThresholdMs` from `chartUtils.ts`) SHALL render as `null` in `chartData` so the `Line` breaks (`connectNulls=false`), and a `ReferenceArea` SHALL overlay the gap span with `fill="var(--muted)" fillOpacity={0.08} strokeOpacity={0}`. The previous opaque `rect fill="#52525b" opacity="0.25"` outage rectangles SHALL NOT exist.

#### Scenario: Line breaks on gap

- **WHEN** `chartData` built via `toChartData(points, gapThresholdMs)` contains a gap between indices `i-1` and `i` where `times[i]-times[i-1] > gapThresholdMs`
- **THEN** `chartData[i].temp` and `chartData[i].humid` are `null` at the boundary, and `ComposedChart` with `connectNulls={false}` shows a visual discontinuity (no diagonal bridge across the gap)

#### Scenario: Faint ReferenceArea replaces rects

- **WHEN** `getOutages(chartData.map(d=>d.ts), minTimeMs, gapThresholdMs)` returns `[{start,end}]`
- **THEN** the chart subtree contains `<ReferenceArea x1={isoStart} x2={isoEnd} yAxisId="temp" fill="var(--muted)" fillOpacity={0.08} strokeOpacity={0} />` for each outage, and `rg 'fill="#52525b"'` returns 0

#### Scenario: Isolated single-point dots still visible

- **WHEN** a segment collapses to a single point after gap nulling
- **THEN** that datum renders as an active dot (via `activeDot` or explicit `Scatter` fallback) at `r=3` so single samples are not invisible; test with `points=[{t:"2026-08-29T10:00:00Z", temp:26, humid:60}]` as the only point in range

### Requirement: Tooltip synced with labelFormatter and Brush

The chart SHALL use `ChartTooltip content={<ChartTooltipContent labelFormatter={formatTooltipTime} indicator="dot" />}` with `cursor={{ strokeDasharray: "3 3" }}` and `Brush dataKey="t" height={24}` with `stroke="var(--border)" fill="var(--card)" travellerWidth={8}` and `tickFormatter` via `formatAxisTime`. Hoever on any line SHALL show the synced point's `temp 25.4°C` and `humid 68%` together regardless of axis.

#### Scenario: Tooltip shows both units

- **WHEN** the user hovers `ComposedChart` at `x` corresponding to `t="2026-08-29T10:00:00Z"` where `temp=25.4 humid=68`
- **THEN** `ChartTooltipContent` displays `formatTooltipTime(t)` as label (with `WIB` suffix) and rows `Temperature 25.4°C` in `var(--chart-1)` and `Humidity 68%` in `var(--chart-2)` using dot indicator, each sourced from the matching `yAxisId`

#### Scenario: Brush present when dense

- **WHEN** `chartData.length > 30`
- **THEN** `ComposedChart` subtree contains `<Brush dataKey="t" height={24} stroke="var(--border)" … />`; when `length <= 30` brush is omitted to avoid clutter (tracked but not required for spec pass)

### Requirement: XAxis formatting and responsive ticks

`XAxis dataKey="t"` SHALL use `tickFormatter (v)=>formatAxisTime(v, timeRange)` from `lib/chartUtils.ts` and `tick={{ fill:"var(--muted-foreground)", fontFamily:"var(--font-mono)", fontSize:10 }}` with `axisLine { stroke: "var(--border)" }` and `tickLine={false} minTickGap={24}`.

#### Scenario: X ticks match range

- **WHEN** `timeRange="24h"` and data spans Jakarta midnight
- **THEN** `XAxis` tick labels read `HH:mm` via `formatAxisTime` `timeZone: Asia/Jakarta` (e.g., `06:00` `12:00`); `7d/30d` show `MM/DD HH:mm` equivalent as defined by `formatAxisTime` second branch

### Requirement: Data mapping — null guards and out-of-range clamping

Any datum where `typeof temp!=="number"` or `NaN` SHALL map to `null` for that series so `Line` interpolates only over valid numbers; compiler-type strictness SHALL enforce `ChartDatum` (`temp|null` etc.). Chart domains SHALL NOT be auto-clamped to `minY/maxY` blended temperature+humidity — they stay `15-30` / `0-100` regardless of data spikes, with y-overflow handled by line clipping, not rescaling.

#### Scenario: NaN skipped

- **WHEN** `chartData` contains `{ t:"…", temp: NaN, humid: 70 }`
- **THEN** the temp `Line` receives `null` for that index and does not draw through it; the humid `Line` still draws `70` at that `t`; no `typeof v!=="number" || isNaN` path is duplicated per-series beyond `toChartData`

#### Scenario: Domain never blends

- **WHEN** a `humid` spike to `99` occurs
- **THEN** `YAxis yAxisId="temp"` still shows `15-30` (not `15-99`) and the `humid 99` sits near top of the right axis, not clamped to left scale

### Requirement: Accessibility and data fallback

When `points` is empty or `chartData` all-null, the chart canvas SHALL NOT render stale axes with phantom lines; instead `Empty` behavior applies (parent spec). When `points` is non-empty, the canvas SHALL at least render axes and grid, even if one series is entirely null.

#### Scenario: All null series

- **WHEN** data has only `pln/genset/aki` (no temp/humid) and `TSChartVariant` is mounted (fallback for unknown `devType`)
- **THEN** axes still render and grid remains; the `Line`s simply produce no path segments but do not throw; the parent `HistoryChart` falls back to `ATSChartVariant` if `devType==="ATS"` as the authoritative guard
