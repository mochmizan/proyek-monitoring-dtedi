# Tasks: dashboard-full-shadcn-redesign-2026-08-29

## 1. Scaffolding & token pass

- [ ] 1.1 Verify change folder `openspec/changes/dashboard-full-shadcn-redesign-2026-08-29` exists with `.openspec.yaml` `schema: spec-driven` `status: proposed` `created: 2026-08-29`
- [ ] 1.2 Read `dashboard/src/index.css`, `dashboard/components.json`, `dashboard/vite.config.ts` to confirm `@tailwindcss/vite` plugin, `aliases` (`@/components`, `@/lib/utils`), `style: new-york`, `rsc: false`, Tailwind v4
- [ ] 1.3 Update `dashboard/src/index.css` `@theme inline`: add `--color-accent: #14b8a6`, `--color-accent-foreground: #09090b`, `--color-chart-1..5` (indigo/teal/amber/red/muted), `--radius: 0.625rem`, `--font-mono: "Fragment Mono"`, `--font-serif: "Source Serif 4"`, `--color-popover`/`--color-popover-foreground`; retain `background:#09090b` `primary:#6366f1` `border:#27272a`
- [ ] 1.4 Add Google Fonts import line to top of `index.css` as first statement: `@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fragment+Mono&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');`
- [ ] 1.5 Add motion tokens to `index.css`: `--ease-out: cubic-bezier(0.23,1,0.32,1)` + `--ease-in-out: cubic-bezier(0.77,0,0.175,1)` + `.button:active { transform: scale(0.97) }` with `120ms ease-out` + `.tooltip { transform-origin: var(--transform-origin); transition: transform 125ms ease-out, opacity 125ms }` + stagger `@keyframes fadeIn` + `@media (prefers-reduced-motion: reduce)` `transition:none` + `@media (hover:hover) and (pointer:fine)` hover gate
- [ ] 1.6 Rename existing `space-y-*` gaps strategy: grep repo for `space-y-` and `space-x-` inside `dashboard/src` and list files to touch (audit only, no edit yet)

## 2. shadcn primitives — install & audit

- [ ] 2.1 Run in `dashboard/` using project package manager (check `package.json` `packageManager`): `npx shadcn@latest add chart separator alert skeleton tooltip avatar empty input-group field toggle-group --overwrite` (or `pnpm dlx`/`bunx` per manager). If `packageManager` absent, use `npx`. Confirm `src/components/ui/` gets `chart.tsx`, `separator.tsx`, `alert.tsx`, `skeleton.tsx`, `tooltip.tsx`, `avatar.tsx`, `empty.tsx`, `input-group.tsx`, `field.tsx`, `toggle-group.tsx`
- [ ] 2.2 Verify no `rsc` `"use client"` injected incorrectly (Vite SPA `rsc: false`, so no directive). If present, remove.
- [ ] 2.3 Verify `dashboard/components.json` aliases intact: `components: "@/components"` `utils: "@/lib/utils"` `ui: "@/components/ui"` — revert if CLI changed them
- [ ] 2.4 Run `npx shadcn@latest docs chart separator alert skeleton tooltip avatar empty input-group field toggle-group` and fetch URLs to confirm `SelectItem→SelectGroup`, `TabsTrigger→TabsList`, `ToggleGroup`, `FieldGroup` composition from docs (record URLs in task notes)
- [ ] 2.5 Audit `dashboard/src/routes/schedules.tsx` against shadcn rules (no edit unless needed): check `CardHeader`/`CardTitle`/`CardDescription`/`CardContent` present, `DialogTitle` present, `SelectItem` inside `SelectGroup`, `gap-*` not `space-y-*`, no `isPending` on Button, no `size-4` on icon inside Button (should use `data-icon`)
- [ ] 2.6 Install chart peer: `npm install recharts` (or `pnpm add recharts` per manager) if not already via `chart` add; verify `ChartContainer`, `ChartTooltip`, `ChartTooltipContent` importable from `@/components/ui/chart`

## 3. chartUtils — gap to null transform

- [ ] 3.1 Read `dashboard/src/lib/chartUtils.ts` and record current `getGapThresholdMs`, `getOutages`, `GAP_FLOOR_MS`, `GAP_FLOOR_MIN` usage in `HistoryChart.tsx:101-107`
- [ ] 3.2 Add exported helper `toChartData(points, gapThresholdMs)` in `lib/chartUtils.ts`:
  ```ts
  export type ChartDatum = { t: string; ts: number; temp: number|null; humid: number|null; pln: number|null; genset: number|null; aki: number|null; state?: string|null }
  export function toChartData(points: TelemetryHistoryPoint[], gapThresholdMs: number): ChartDatum[] {
    const times = points.map(p => p.timestamp ? parseToDate(p.timestamp).getTime() : NaN)
    return points.map((p, i) => {
      const t = times[i]; const prev = times[i-1]
      const isGap = i>0 && Number.isFinite(t) && Number.isFinite(prev) && t - prev > gapThresholdMs
      return {
        t: p.timestamp, ts: Number.isFinite(t) ? t : Date.now(),
        temp:  isGap ? null : (typeof p.temp==="number" ? p.temp : null),
        humid: isGap ? null : (typeof p.humid==="number" ? p.humid : null),
        pln:   isGap ? null : (typeof p.pln==="number" ? p.pln : null),
        genset:isGap ? null : (typeof p.genset==="number" ? p.genset : null),
        aki:  isGap ? null : (typeof p.aki==="number" ? p.aki : null),
        state: p.state ?? null,
      }
    })
  }
  ```
- [ ] 3.3 Keep `parseToDate`, `formatAxisTime`, `formatTooltipTime`, `getMedianIntervalMs`, `getGapThresholdMs`, `getOutages` unchanged — `getOutages` now only drives `ReferenceArea` X1/X2, not SVG rects
- [ ] 3.4 Write unit test `dashboard/src/__tests__/chartUtils.test.ts` for `toChartData` gap→null (empty array, single point, gap threshold, NaN timestamp)
- [ ] 3.5 Replace any `verbatimModuleSyntax` violations: ensure `import type { ChartDatum }`

## 4. HistoryChart — dual YAxis shadcn Chart (Vercel composition)

- [ ] 4.1 Create `dashboard/src/components/device/HistoryChartProvider.tsx` or co-locate inside `HistoryChart.tsx` (decide, document gap):
  - [ ] 4.1.1 Define `HistoryChartState` `{ points, timeRange: '6h'|'24h'|'7d'|'30d', warningThresholdVal, criticalThresholdVal, devType }`, `HistoryChartActions { setTimeRange }`, `HistoryChartMeta { gapThresholdMs }`
  - [ ] 4.1.2 Create `HistoryChartContext = createContext<…|null>(null)` + `HistoryChartProvider({ children, state, actions, meta })` wraps `<TooltipProvider>`
  - [ ] 4.1.3 `useHistoryChart()` uses `use(HistoryChartContext)` (React 19 `use`, not `useContext`); throws if outside provider
- [ ] 4.2 Create explicit variants — forbid `isTS/isATS` boolean:
  - [ ] 4.2.1 `TSChartVariant` as `function TSChartVariant(): React.ReactNode` inside provider boundary:
    ```tsx
    import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
    import { CartesianGrid, ComposedChart, XAxis, YAxis, Line, Area, Brush, ReferenceLine, ReferenceArea } from "recharts"
    function TSChartVariant() {
      const { state, meta } = useHistoryChart()
      const chartData = useMemo(() => toChartData(state.points, meta.gapThresholdMs), [state.points, meta.gapThresholdMs])
      return (
        <ChartContainer config={{ temp: { label: "Temperature", color: "var(--chart-1)" }, humid: { label: "Humidity", color: "var(--chart-2)" } }} className="h-[260px] w-full">
          <ComposedChart data={chartData} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}>
            <defs><linearGradient id="tempGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.18}/><stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.02}/>
            </linearGradient></defs>
            <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
            <XAxis dataKey="t" tickFormatter={(v: string)=>formatAxisTime(v, state.timeRange)} tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }} axisLine={{ stroke: "var(--border)" }} tickLine={false} minTickGap={24} />
            <YAxis yAxisId="temp" domain={[15,30]} tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
            <YAxis yAxisId="humid" orientation="right" domain={[0,100]} tickFormatter={(v: number)=>`${v}%`} tick={{ fill: "var(--muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={(v: string)=>formatTooltipTime(v)} indicator="dot" />} cursor={{ strokeDasharray: "3 3" }} />
            {typeof state.warningThresholdVal==="number" && state.warningThresholdVal>=15 && state.warningThresholdVal<=30 && (
              <ReferenceLine yAxisId="temp" y={state.warningThresholdVal} stroke="var(--chart-3)" strokeDasharray="4 4" strokeWidth={1.25} label={{ value: `Warn ${state.warningThresholdVal}°C`, position: "right", fill: "var(--chart-3)", fontSize: 10, fontFamily: "var(--font-mono)" }} />
            )}
            {typeof state.criticalThresholdVal==="number" && state.criticalThresholdVal>=15 && state.criticalThresholdVal<=30 && (
              <ReferenceLine yAxisId="temp" y={state.criticalThresholdVal} stroke="var(--chart-4)" strokeDasharray="4 4" strokeWidth={1.25} label={{ value: `Crit ${state.criticalThresholdVal}°C`, position: "right", fill: "var(--chart-4)", fontSize: 10 }} />
            )}
            {getOutages(chartData.map(d=>d.ts), minTimeMs, meta.gapThresholdMs).map((o,i)=>
              <ReferenceArea key={i} x1={new Date(o.start).toISOString()} x2={new Date(o.end).toISOString()} yAxisId="temp" fill="var(--muted)" fillOpacity={0.08} strokeOpacity={0} />
            )}
            <Area yAxisId="temp" type="monotone" dataKey="temp" fill="url(#tempGradient)" stroke="none" />
            <Line yAxisId="temp" type="monotone" dataKey="temp" stroke="var(--chart-1)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 2 }} connectNulls={false} />
            <Line yAxisId="humid" type="monotone" dataKey="humid" stroke="var(--chart-2)" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls={false} />
            <Brush dataKey="t" height={24} stroke="var(--border)" fill="var(--card)" travellerWidth={8} tickFormatter={(v: string)=>formatAxisTime(v, state.timeRange)} />
          </ComposedChart>
        </ChartContainer>
      )
    }
    ```
  - [ ] 4.2.2 `ATSChartVariant` as sibling — single `YAxis domain={[0, max*1.05]}` (compute from chartData), three `Line`s: `pln` `var(--chart-2)` `2.5`, `genset` `#f59e0b` `2.5`, `aki` `var(--chart-1)` dashed `3 3` `2`
- [ ] 4.3 Create compound export at bottom of file:
  ```ts
  export const HistoryChart = {
    Provider: HistoryChartProvider,
    Frame: function HistoryChartFrame({ children }: { children: React.ReactNode }) { return <Card className="overflow-hidden"><CardHeader>…</CardHeader><CardContent className="p-0 pt-2">{children}</CardContent></Card> },
    Header: function HistoryChartHeader() { /* Badge row + legend + Separator */ },
    CanvasTS: TSChartVariant,
    CanvasATS: ATSChartVariant,
  }
  // Also default export wrapper for compat: function HistoryChartWrapper(props) renders Provider + Frame + Header + (devType==="ATS"?CanvasATS:CanvasTS)
  ```
- [ ] 4.4 Rewrite `dashboard/src/components/device/HistoryChart.tsx` head: delete custom SVG fixed width/height (`width=800`, `height=260`, `padding`, `plotWidth`, `plotHeight`, `getY`, `timeToX`, `getX`, `buildLine`, `yTicks`, `xTimeTicks`, `handleMouseMove`, `hoverIndex` SVG state), replace with ChartContainer logic above; keep range toggle but convert to `ToggleGroup type="single"` with 4 items `6h/24h/7d/30d` (`variant="outline" size="sm"`)
- [ ] 4.5 Telemetry stat header inside `CardHeader`: 4 stats for TS (`Current/Min/Max/Avg Temp` + `Humidity` sub) and 4 for ATS (`PLN/Genset/Battery/State`) using `CardHeader`→`Badge` dot + `Separator`, not `bg-zinc-950` divs
- [ ] 4.6 Legend row: `flex flex-wrap gap-4 text-xs` with `gap` dot + label, plus `Separator orientation="vertical"` before threshold legend when thresholds shown
- [ ] 4.7 Empty branch: when `points.length===0` render `Empty` not hand `div border-dashed`:
  ```tsx
  import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia } from "@/components/ui/empty"
  {points.length===0 && <Empty><EmptyMedia><Activity className="size-8 text-muted-foreground" data-icon="inline-start" /></EmptyMedia><EmptyHeader><EmptyTitle>Collecting telemetry…</EmptyTitle><EmptyDescription>No history within {timeRange}</EmptyDescription></EmptyHeader></Empty>}
  ```
- [ ] 4.8 Remove mouse-move SVG hover state; rely on `ChartTooltip`; ensure `connectNulls={false}` so gaps break line correctly
- [ ] 4.9 Brush footnote: brush renders only when `points.length > 30`; otherwise omitted to save height
- [ ] 4.10 Ensure `CartesianGrid` uses `stroke="var(--border)"` semantic token, not `#27272a` raw

## 5. Device header — Node Information folding (delete 6-card grid)

- [ ] 5.1 Read `dashboard/src/routes/device.$deviceId.tsx` lines 72-124 fully; snapshot before edit
- [ ] 5.2 Refactor header block (72-90) to sticky + CardHeader pattern:
  - [ ] 5.2.1 Wrap header in `<div className="sticky top-0 z-10 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b px-1 -mx-1 py-3">`
  - [ ] 5.2.2 Replace raw status `span` with `Badge`:
    ```tsx
    import { Badge } from "@/components/ui/badge"
    import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip"
    <Badge variant={isPending?"secondary": isOnline?"default":"outline"} className="gap-1.5 font-mono text-xs">
      <span className={cn("size-1.5 rounded-full", isPending?"bg-amber-400": isOnline?"bg-emerald-400 animate-pulse":"bg-zinc-500")} aria-hidden />
      {isPending ? "Pending Approval" : isOnline ? "Online" : "Offline"}
    </Badge>
    ```
  - [ ] 5.2.3 Replace `p font-mono MAC / ID · Type · Room` with inline badge row:
    ```tsx
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge variant="outline" className="font-mono">{device.dev_id}</Badge>
      <Separator orientation="vertical" className="h-3" />
      <Badge variant="secondary">{device.dev_type || "Generic"}</Badge>
      <Separator orientation="vertical" className="h-3" />
      <TooltipProvider><Tooltip><TooltipTrigger asChild><Badge variant="outline">{room?.name || "Unpaired"}</Badge></TooltipTrigger><TooltipContent>Room assignment</TooltipContent></Tooltip></TooltipProvider>
      <TooltipProvider><Tooltip><TooltipTrigger asChild><span className="font-mono text-muted-foreground">{device.marker_x!==null && device.marker_y!==null ? `${device.marker_x}%, ${device.marker_y}%` : "Unplaced"}</span></TooltipTrigger><TooltipContent>Map coordinate — drag in Settings → Floor Plan</TooltipContent></Tooltip></TooltipProvider>
      <Separator orientation="vertical" className="h-3" />
      <span className="text-muted-foreground text-xs">{device.created_at ? new Date(device.created_at).toLocaleDateString() : "—"}</span>
    </div>
    ```
  - [ ] 5.2.4 Replace polling `div` with `Badge variant="outline" className="gap-1.5"` containing `Loader2` or `RefreshCw` with `data-icon="inline-start"` + `className="size-3 animate-spin"` (no `size-4`)
  - [ ] 5.2.5 Add `Skeleton` when `!device` pending: `Card` wrapping `Skeleton className="h-6 w-40"` etc.
- [ ] 5.3 **DELETE** `Node Information` 6-card grid `92-106` entirely (remove the `<div className="bg-zinc-900 border rounded-lg p-6 space-y-4"><h3>Node Information</h3><div className="grid grid-cols-2 sm:grid-cols-3 gap-4">…6 cards</div></div>`). Do not leave empty wrapper.
- [ ] 5.4 Move Warning/Critical values into two places:
  - [ ] 5.4.1 Chart header threshold legend (already in `TSChartVariant` as `ReferenceLine` + textual `warn: X°C` legend)
  - [ ] 5.4.2 Device Controls thresholds as `FieldDescription` inside `Controls.tsx` Field (see §7)
- [ ] 5.5 Alert Log table: wrap in `Card` with `CardHeader`→`CardTitle` + `CardContent className="p-0"` + `Table` + `TableHeader` + `TableRow` + `TableHead` + `TableCell` + `Badge` severity + `Separator` above; empty shows `Empty` not `tr colSpan`
- [ ] 5.6 Body grid change: `<div className="grid grid-cols-12 gap-6">` `<div className="col-span-12 lg:col-span-8 space-y-4">` (chart + alert log) `<div className="col-span-12 lg:col-span-4 space-y-4">` (`DeviceControls`)
- [ ] 5.7 Ensure header title uses `font-serif text-2xl font-semibold tracking-tight` to meet type role

## 6. Dashboard overview + rooms + nodes table

- [ ] 6.1 Stats bar `141-177`: replace `grid md:grid-cols-4` raw `bg-zinc-900 border rounded-lg p-5` divs with:
  ```tsx
  import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
  import { Separator } from "@/components/ui/separator"
  import { Skeleton } from "@/components/ui/skeleton"
  <div className="grid gap-4 md:grid-cols-4">
    <Card className="card-stagger"><CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
      <CardTitle className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Total Rooms</CardTitle>
      <Layers className="size-4 text-muted-foreground" data-icon="inline-end" />
    </CardHeader><Separator className="mx-6 w-auto" /><CardContent><p className="text-2xl font-bold font-mono">{rooms.length}</p></CardContent></Card>
    {/* Repeat for Active Devices (HardDrive), Warning Alerts (amber), Critical (red) with variant colors via Badge dot */}
  </div>
  ```
- [ ] 6.2 Rooms section `189-204`: wrap each `RoomCard` stagger `className="card-stagger"` inline style delay via `style={{ animationDelay: `${i*40}ms` }}` on wrapper; ensure `RoomCardSkeleton` imports `Skeleton` not `animate-pulse` divs (see 6.4)
- [ ] 6.3 Nodes table `206-298`: convert to shadcn Table:
  - [ ] 6.3.1 Import `Table, TableHeader, TableBody, TableRow, TableHead, TableCell` + `Badge` + `Avatar, AvatarFallback` + `Tooltip` + `Skeleton`
  - [ ] 6.3.2 Replace `<div className="bg-zinc-900 border rounded-lg overflow-hidden"><div className="overflow-x-auto"><table` with `<Card className="overflow-hidden"><CardContent className="p-0"><div className="overflow-x-auto"><Table>`
  - [ ] 6.3.3 Replace `<thead>` with `<TableHeader><TableRow>`
  - [ ] 6.3.4 Replace each hand `<th className="px-6 py-4"><Link>` sortable header with:
    ```tsx
    import { Button } from "@/components/ui/button"
    function SortHead({ label, sortKey }: { label: string; sortKey: typeof sortBy }) {
      const active = sortBy===sortKey
      return (
        <TableHead aria-sort={active ? (sortOrder==="asc"?"ascending":"descending":"none") : "none"}>
          <Button variant="ghost" size="sm" className="h-7 gap-1.5 px-2 -ml-2 font-semibold uppercase tracking-wider text-xs"
            onClick={()=>navigate({ to: ".", search: (prev)=>({ ...prev, sortBy: sortKey, sortOrder: active? (prev.sortOrder==="asc"?"desc":"asc"):"asc"}) })}>
            {label}
            {active ? (sortOrder==="asc"?<ArrowUp data-icon="inline-end"/>:<ArrowDown data-icon="inline-end"/>):<ArrowUpDown className="size-3.5 opacity-40" data-icon="inline-end" />}
          </Button>
        </TableHead>
      )
    }
    ```
  - [ ] 6.3.5 Replace `<td><span className="bg-zinc-800 text-xs px-2.5…>` type cell with `<TableCell><Badge variant="secondary" className="font-mono">{device.dev_type||"Generic"}</Badge></TableCell>`
  - [ ] 6.3.6 Replace `<td>room name` with `<TableCell><Badge variant="outline">{room.name}</Badge>` or `<span className="text-muted-foreground italic">Unassigned</span>`
  - [ ] 6.3.7 Replace status `span` with `<Badge variant={isPending?"secondary":isOnline?"default":"outline"} className="gap-1.5"><StatusDot …/>{label}</Badge>` inside `TableCell`
  - [ ] 6.3.8 Replace thresholds `td` with `TooltipProvider→Tooltip→TooltipTrigger Badge outline → TooltipContent "Warning X°C / Critical Y°C"`; default cell shows `<span className="text-muted-foreground text-xs">Default</span>`
  - [ ] 6.3.9 Ensure `cn()` used only for layout (`hover:bg-muted/50`), not color; `gap-*` not `space-y-*`; `Skeleton` shown during `isInitialLoading` via `TableBody` fallback rows of `Skeleton className="h-4 w-full"`
  - [ ] 6.3.10 Empty state: replace `<tr><td colSpan={7} … No devices>` with `Empty` inside `CardContent`:
    ```tsx
    import { Empty, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
    {sortedDevices.length===0 && <div className="px-6 py-10"><Empty><EmptyTitle>No devices found</EmptyTitle><EmptyDescription>Pair a device in Settings</EmptyDescription></Empty></div>}
    ```

## 7. RoomCard + TopologyView + Map — Tabs / Empty / Badge / Separator / Skeleton

- [ ] 7.1 `src/components/RoomCard.tsx`:
  - [ ] 7.1.1 Verify imports `Avatar, AvatarFallback`, `Badge`, `Skeleton`, `Separator`
  - [ ] 7.1.2 Replace root `<div className="relative rounded-xl bg-zinc-900 border">` with `<Card className={cn("relative hover:border-zinc-700 transition-colors", className)}>` and split into `<CardHeader>` (title + StatusDot), `<CardContent>` (temp/humidity), `<CardFooter className="border-t">` (device count + sparkline)
  - [ ] 7.1.3 Replace status raw dot logic with `Badge variant={status==="Critical"?"destructive":status==="Warning"?"secondary":"outline"}` where appropriate; keep `StatusDot` inside `Badge` via `gap-1.5`
  - [ ] 7.1.4 `RoomCardSkeleton`: replace `animate-pulse` hand `div className="h-4 w-24 rounded bg-zinc-800"` with `<Skeleton className="h-4 w-24" />`; same for 4 lines
- [ ] 7.2 `src/routes/map.tsx`:
  - [ ] 7.2.1 Replace hand tabs `186-210` (`flex border-b` + `button pb-3 border-b-2`) with:
    ```tsx
    import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
    <Tabs value={activeView} onValueChange={(v)=>setView(v as "floor-plan"|"topology")}>
      <TabsList><TabsTrigger value="floor-plan"><LayoutGrid data-icon="inline-start"/>Floor Plan</TabsTrigger><TabsTrigger value="topology"><Network data-icon="inline-start"/>Topology</TabsTrigger></TabsList>
      <TabsContent value="floor-plan">…floor-plan Card…</TabsContent>
      <TabsContent value="topology"><TopologyView/></TabsContent>
    </Tabs>
    ```
  - [ ] 7.2.2 Remove `useState view` local if replaced; keep `mapSearchSchema` but set with `router.navigate` or `Tabs` callback so URL stays source (validateSearch already handles `view`)
  - [ ] 7.2.3 Replace empty `rooms.length===0` and `!has_image` branches `147-159` with `Empty`:
    ```tsx
    import { Empty, EmptyMedia, EmptyHeader, EmptyTitle, EmptyDescription } from "@/components/ui/empty"
    <Empty><EmptyMedia><HelpCircle className="size-8" /></EmptyMedia><EmptyHeader><EmptyTitle>No rooms found</EmptyTitle><EmptyDescription>Create rooms in Settings</EmptyDescription></EmptyHeader></Empty>
    ```
  - [ ] 7.2.4 Replace `select` room picker with shadcn `Select` + `SelectGroup`→`SelectItem` + `SelectTrigger`
  - [ ] 7.2.5 Wrap floor-plan image area in `Card` + `CardContent` + `Separator` between legend and canvas
  - [ ] 7.2.6 Marker tooltip: use `TooltipProvider` + `Tooltip` + `TooltipContent` with `className="data-[state=open]:animate-in data-[state=closed]:animate-out"` and `transform-origin: var(--transform-origin)`; remove hand `group-hover:opacity-100` CSS tooltip
- [ ] 7.3 `src/components/TopologyView.tsx`:
  - [ ] 7.3.1 Replace hand status `StatusDot` + node container `w-44 bg-zinc-900 border` with `Card` pattern inside `TopologyNodeView`; keep `Handle` but ensure `CardHeader`-like inner split if needed
  - [ ] 7.3.2 Replace empty `No edge hubs registered` `div flex-1 bg-zinc-900 border` with `Empty` + `EmptyMedia HelpCircle`
  - [ ] 7.3.3 Legend/separator: add `Separator` between canvas and control bar if present
  - [ ] 7.3.4 Verify `Tooltip`/`Popover` content (if any hover detail) uses `data-starting-style` transform, not `data-state` transform

## 8. Room detail + Device controls — FieldGroup / ToggleGroup / Dialog / Sheet

- [ ] 8.1 `src/routes/room.$roomId.tsx`:
  - [ ] 8.1.1 Delete `fixed inset-0 bg-black/70 backdrop-blur-xs … animate-in fade-in` modal block (353-472) and replace with `Dialog`:
    ```tsx
    import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
    import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
    import { FieldGroup, Field, FieldLabel } from "@/components/ui/field"
    import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
    import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
    <Dialog open={!!selectedDeviceForCmd} onOpenChange={(o)=> !o && setSelectedDeviceForCmd(null)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Command Control: {selectedDeviceForCmd?.dev_name || selectedDeviceForCmd?.dev_id}</DialogTitle>
          <DialogDescription className="font-mono text-xs">{selectedDeviceForCmd?.dev_type} Node · queued via pending_commands</DialogDescription>
        </DialogHeader>
        {cmdError && <Alert variant="destructive"><AlertTriangle data-icon="inline-start"/><AlertTitle>Failed</AlertTitle><AlertDescription>{cmdError}</AlertDescription></Alert>}
        {cmdSuccess && <Alert><CheckCircle data-icon="inline-start"/><AlertTitle>Queued</AlertTitle><AlertDescription>{cmdSuccess}</AlertDescription></Alert>}
        <FieldGroup>
          <Field>
            <FieldLabel>Operating Mode</FieldLabel>
            <ToggleGroup type="single" value={commandPayload.mode||""} onValueChange={(v)=> setCommandPayload({ ...commandPayload, mode: (v as "auto"|"manual")||undefined }) } variant="outline" size="sm">
              <ToggleGroupItem value="auto">Auto</ToggleGroupItem>
              <ToggleGroupItem value="manual">Manual</ToggleGroupItem>
            </ToggleGroup>
          </Field>
          <Field>
            <FieldLabel>Genset Ignition (Manual Only)</FieldLabel>
            <ToggleGroup type="single" value={commandPayload.start_genset||""} onValueChange={(v)=> setCommandPayload({ ...commandPayload, start_genset: (v as "on"|"off")||undefined })} variant="outline" size="sm">
              <ToggleGroupItem value="on">Start ON</ToggleGroupItem>
              <ToggleGroupItem value="off">Stop OFF</ToggleGroupItem>
            </ToggleGroup>
          </Field>
          {isAdmin && (
            <Field>
              <FieldLabel>Controller Reset (Admin Only)</FieldLabel>
              <div className="flex items-center gap-2"><Switch id="reset" checked={commandPayload.reset==="rst"} onCheckedChange={(c)=> setCommandPayload({ ...commandPayload, reset: c?"rst":undefined })} /><label htmlFor="reset" className="text-sm text-muted-foreground">Issue hardware reset</label></div>
            </Field>
          )}
        </FieldGroup>
        <Separator />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={()=>setSelectedDeviceForCmd(null)}>Cancel</Button>
          <Button type="submit" onClick={handleExecuteCommand} disabled={commandMutation.isPending} className="gap-2">
            {commandMutation.isPending ? <><Loader2 className="size-3.5 animate-spin" data-icon="inline-start" />Sending…</> : "Queue Command"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    ```
  - [ ] 8.1.2 Remove native `select` + `input type=checkbox` remnants; ensure `cn()` gap rules, no `space-y`
  - [ ] 8.1.3 Floor plan section: wrap in `Card` + `CardHeader`→`CardTitle` + `Separator` + `CardContent`; empty state with `Empty`
  - [ ] 8.1.4 Device assignment grid cards: each `div bg-zinc-900 border rounded-lg p-5` becomes `Card` with `CardHeader`→`CardTitle` + `Badge` type + `CardContent` telemetry `FieldGroup` + `Separator` + `CardFooter` (Link + Button)
- [ ] 8.2 `src/components/device/Controls.tsx` (read first — file not enumerated but implied from `device.$deviceId` import):
  - [ ] 8.2.1 Mirror same `FieldGroup`/`ToggleGroup`/`InputGroup`/`Alert`/`Button data-icon`/`Separator` conversion; ensure `SelectItem→SelectGroup`, `Button` no `isPending`, icons use `data-icon`, `size-*` not `w-* h-*`
  - [ ] 8.2.2 If no separate file (controls inline in `room.$roomId`), mark task done with note and skip
- [ ] 8.3 Thresholds / Settings form (likely `src/routes/settings.tsx` or `components/settings/RoomsTab`):
  - [ ] 8.3.1 Replace raw numeric `Input` for warning/critical with:
    ```tsx
    import { FieldGroup, Field, FieldLabel, FieldDescription } from "@/components/ui/field"
    import { InputGroup, InputGroupInput, InputGroupAddon } from "@/components/ui/input-group"
    import { Separator } from "@/components/ui/separator"
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="warn">Warning Threshold</FieldLabel>
        <InputGroup><InputGroupInput id="warn" type="number" value={warning} onChange={…} aria-invalid={warnError? true:undefined} /><InputGroupAddon align="inline-end">°C</InputGroupAddon></InputGroup>
        {warnError ? <FieldDescription className="text-destructive">{warnError}</FieldDescription> : <FieldDescription>Trigger warning alert above this temperature</FieldDescription>}
      </Field>
      <Separator />
      <Field>
        <FieldLabel htmlFor="crit">Critical Threshold</FieldLabel>
        <InputGroup><InputGroupInput id="crit" type="number" value={crit} onChange={…} /><InputGroupAddon align="inline-end">°C</InputGroupAddon></InputGroup>
        <FieldDescription>Trigger critical alert above this temperature</FieldDescription>
      </Field>
    </FieldGroup>
    ```
  - [ ] 8.3.2 Ensure validation uses `data-invalid` on `Field` + `aria-invalid` on the `Input`, not manual `border-red-500` alone

## 9. Schedules polish (no rewrite)

- [ ] 9.1 Audit `dashboard/src/routes/schedules.tsx` end-to-end for D6 checklist; file is 520+ lines and already shadcn—diff should be small:
  - [ ] 9.1.1 Replace any remaining `space-y-4` / `space-y-1` with `flex flex-col gap-*` (grep: `space-y`)
  - [ ] 9.1.2 Ensure every `Select` wraps `SelectItem` with `SelectGroup` (already present — verify not regressed)
  - [ ] 9.1.3 Ensure `Dialog` has `DialogTitle` + `DialogDescription` (already present at lines ~389-393 — verify `DialogFooter` uses `gap-2` not `space-x`)
  - [ ] 9.1.4 Ensure `TableHead` sorted headers (if any) use `Button variant="ghost"` pattern or leave as is (schedule table is non-sortable today)
  - [ ] 9.1.5 Replace raw `textarea` for custom JSON with `Textarea` from `ui/textarea` inside `InputGroup` context if appropriate, or keep `InputGroupTextarea` per `input-group` spec (`InputGroupTextarea` not raw `Textarea` inside `InputGroup`)
  - [ ] 9.1.6 Ensure icons in Buttons use `data-icon="inline-start"` and no `size-4` class; trust component CSS
  - [ ] 9.1.7 Ensure `Badge payload` + `Switch` + `Tooltip` + `Alert`/`Empty` for empty schedules uses semantic tokens (no `bg-blue-500`);

## 10. Cross-cutting sweep — styling & composition & icons & type

- [ ] 10.1 Grep sweep `dashboard/src`: `grep -R "space-y-"` must be 0; `grep -R "space-x-"` must be 0; fix each hit to `flex gap-*` or `flex flex-col gap-*`
- [ ] 10.2 Grep `w-[0-9]+ h-[0-9]+` on same line of `size-` equal dimensions (e.g., `w-8 h-8` on `Avatar` or icon) → replace with `size-*` (`size-8`, `size-10`)
- [ ] 10.3 Grep `overview-hidden|text-ellipsis|whitespace-nowrap` combo → replace with `truncate` single class
- [ ] 10.4 Grep `dark:` overrides on colors → remove, rely on semantic tokens `bg-background` `text-muted-foreground`
- [ ] 10.5 Grep `z-*` on `Dialog`/`Sheet`/`Popover`/`Tooltip` wrappers → remove manual z-index (component handles stacking)
- [ ] 10.6 Grep `Buttons.*isPending|isLoading` prop → replace with `{pending && <Spinner data-icon="inline-start" />}` + `disabled={pending}`
- [ ] 10.7 Grep `SelectItem` not immediately under `SelectGroup` → fix by wrapping in `SelectGroup`
- [ ] 10.8 Grep `TabsTrigger` outside `TabsList` → fix by nesting inside `TabsList`
- [ ] 10.9 Grep `Avatar` without subsequent `AvatarFallback` in same file → add `AvatarFallback` with initials or `dev_type` monogram
- [ ] 10.10 Ensure every `DialogContent`/`SheetContent`/`DrawerContent` has `Title` (`DialogTitle`/`SheetTitle`/`DrawerTitle`) even if `className="sr-only"` when visually hidden
- [ ] 10.11 Replace any `<hr>` or `<div className="border-t">` with `<Separator />` or `<Separator orientation="vertical" />`
- [ ] 10.12 Replace any custom `animate-pulse` empty div with `<Skeleton>` import
- [ ] 10.13 Ensure `import type` for all types (`import type { DeviceResponse }`) due to `verbatimModuleSyntax`

## 11. Verification

- [ ] 11.1 `npm run lint` in `dashboard/` — expect 0 errors, at most 14 fast-refresh warns; fail if new errors from chart/toggle types
- [ ] 11.2 `npm run build` in `dashboard/` — `tsc -b && vite build` succeeds, hidden sourcemap generated, bundle delta recorded; if chunk >60kB added, lazy-load `HistoryChart` via `React.lazy` and re-build, document size
- [ ] 11.3 `npm run test -- --run` in `dashboard/` — vitest (3 smoke) + new `chartUtils` unit test green
- [ ] 11.4 `npx playwright test --list` in `dashboard/` — 1+ e2e visible, no broken import; optionally `npm run e2e` (needs Vite :5173)
- [ ] 11.5 `pytest` at repo root — 107 tests (server 79 + hub 13 + pipeline) green; no DB schema change so no alembic step
- [ ] 11.6 `docker compose config` — still binds `127.0.0.1:5432/1883` (not `0.0.0.0`) — run and check output
- [ ] 11.7 `bash -n deploy/setup_push_deploy.sh` — no syntax error
- [ ] 11.8 `curl` health if API running (`https://127.0.0.1/api/health` → `{"status":"ok","db":"up"}`) — optional if env up
- [ ] 11.9 Visual smoke: open `device.$deviceId` with real history → verify chart dual axis legible (temp variation ~28% of plot per 2°C), threshold lines pinned to left axis, gaps break line with faint area, tooltip shows `25.4°C · 68%` with synced dot, brush drags; header badges show hub/room/coord without 6-card grid; table sort headers toggle `aria-sort` and icon
- [ ] 11.10 `graphify update .` if code touched; check `graphify-out/` dirty expected so note to skip if stale

## 12. Docs & closeout

- [ ] 12.1 No `dashboard/AGENTS.md` or `openspec/AGENTS.md` edit required unless a new durable boundary added — record in closeout that no AGENTS doc edit was needed and why
- [ ] 12.2 Remove any stale contradictory note about hand SVG if found in `docs/` (audit only)
- [ ] 12.3 Verify `git log --all -- openspec/changes/` still shows prior `ats-flexible-schedule` archived at `8f1e12e^` and new change sits alongside, not pruning prior
