# Design: Dashboard Full shadcn Redesign + Chart Fix + Node Folding

## Context

SMSB is a campus LAN IoT building monitor. Vite SPA at `dashboard/` polls HubGate V5 (`server/app/`) every 3s (`POLL_MS=3000`) via same-origin `/api` (Vite proxy `:8000` dev, Nginx `443→127.0.0.1:8000` prod). Stack: React 19.2.7, TS ~6.0.2 (`erasableSyntaxOnly` + `verbatimModuleSyntax` → `import type`), Vite 8.1.1, TanStack Router 1.170.17, TanStack Query 5.101.2, Zustand 5.0.14, Zod 4.4.3, Tailwind 4.3.2 via `@tailwindcss/vite`, oxlint 1.71, `shadcn new-york` Base UI (`dashboard/components.json` `baseColor: zinc`, `cssVariables: true`, `rsc: false`). Design tokens: `background:#09090b`, `primary:#6366f1` in `src/index.css` `@theme inline`. Current dashboard is a generic zinc template: hand-rolled `<table>`, custom 800×260 SVG chart with single Y, 6-card Node Information grid, `fixed inset-0` modals without `DialogTitle`. Previous change `ats-flexible-schedule-2026-08-29` already migrated `routes/schedules.tsx` to proper shadcn (`Card/Dialog/Select/Table/Switch/Badge`) and proved the pipeline. This change converges every remaining surface to that level.

Related docs: `docs/2026-07-01-iot-temperature-monitoring-design.md`, `dashboard/AGENTS.md` route→`routeTree.gen.ts`, `server/AGENTS.md` verbatimModuleSyntax, `hub/AGENTS.md` WAL `MAX_PENDING_ROWS=20000`.

## Goals / Non-Goals

**Goals:**
- One visual language: every route uses shadcn `new-york` Base UI composed by the book (CardHeader/Title/Content, SelectItem→SelectGroup, TabsTrigger→TabsList, ToggleGroup, FieldGroup).
- Readable telemetry: temperature 15-30°C left axis, humidity 0-100% right axis, thresholds on left, gaps as `null` + `ReferenceArea`, synced tooltip, brush, responsive.
- Fold Node Information 6-card grid into header inline (`Badge` row + `Tooltip` + `Separator`).
- Sticky header + 8-col chart / 4-col controls layout with hairline trace signature.
- Token pass: 6 named hex, 3 typefaces, motion per emil (120ms scale 0.97), Vercel compound components for chart.
- Zero regressions: `npm run lint/build/test`, `pytest` green, polling/auth/schedules untouched.
- Weak-model executability: every task ships with a literal code snippet the implementer can copy-paste, file:line targets, and acceptance hash.

**Non-Goals:**
- Server/hub/firmware changes, DB migrations, new routes.
- Replacing TanStack Router/Query or adding SSE/WebSocket.
- Sub-second realtime, edge charting, 3D floor-plan.
- Changing `POLL_MS`/`STALE_MS`/`GAP_FLOOR_MIN` semantics beyond adapting gaps to `null`.

## Architecture

```
Vite SPA  dashboard/src/                HubGate VPS  server/app/
  routes/index.tsx        ─ Card grid + Table (shadcn)
  routes/device.$deviceId ─┬─ sticky header (Badge row) + Skeleton
                           ├─ HistoryChartProvider → ChartContainer
                           │    ├─ TSChart  : temp left [15,30] + humid right [0,100]
                           │    └─ ATSChart : pln/genset/aki  [0, max*1.05]
                           ├─ DeviceControls : FieldGroup + ToggleGroup + InputGroup
                           └─ Thresholds (settings) : FieldGroup
  routes/room.$roomId     ─ Dialog/Sheet + Card floor-plan + Badge
  routes/map.tsx          ─ Tabs (TabsList→TabsTrigger) + Card canvas + Empty
  components/TopologyView ─ Card + Separator + Tiny StatusDot + shadcn Tooltip
  components/RoomCard     ─ Card + CardHeader/Content/Footer + Badge + Skeleton
  lib/chartUtils.ts       ─ gap → null transform (replaces outage rect)
  index.css               ─ @theme inline 6 hex + 3 typefaces + motion tokens
                                    ──HTTPS/WAL──►  HubGate polls unchanged (3s, same-origin)
```

Trigger path unchanged: ESP→Pi `hs109rs/#`→VPS HTTPS WAL 0.35s → `GET /api/iot/history?dev_id=&range=` → TanStack Query → `HistoryChartProvider`.

## Wireframes (ASCII)

### Device detail — sticky header + 8/4 layout

```
┌─ sticky top-0 z-10 bg-background/80 backdrop-blur ──────────────────────┐
│  ←  ATS-4F12: genset hall        [Badge Online pulse] [Badge ATS] [hub] │
│  MAC ATS-4F12 · Room Genset Hall · Coord Tooltip (34%, 62%) · Date      │
│  ── Separator ──                                                         │
│  live Polling badge  ·  Skeleton when pending                            │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌─ 8-col chart Card ──────────────┐  ┌─ 4-col controls Card ───────────┐│
│  │ CardHeader: Title "Telemetry"   │  │ CardHeader: Controls             ││
│  │ Badge temp 25.4°C · hum 68%     │  │ FieldGroup                       ││
│  │ ── ChartContainer ──            │  │  Field mode  → ToggleGroup       ││
│  │  Y left [15,30] temp indigo     │  │  Field genset→ ToggleGroup       ││
│  │  Y right [0,100] humid teal     │  │  Field reset → Switch            ││
│  │  ReferenceLine warn/crit left   │  │  ── Separator ──                 ││
│  │  ReferenceArea gap  opacity .08 │  │  [Queue Command Button]          ││
│  │  Brush + Tooltip synced         │  │  Alert success/error             ││
│  │ CardFooter: 6h/24h/7d/30d Tabs  │  └──────────────────────────────────┘│
│  └─────────────────────────────────┘   (Field threshold form sibling)    │
│  ── Separator ──                                                         │
│  Device Alert Log : Table (Severity Badge · Metric · Value · Time · Status)│
│  Empty when zero (with Empty component)                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Dashboard overview — 4 stat Cards + rooms + nodes Table

```
┌─ 4× Card (Total Rooms / Active Devices / Warning / Critical) ───────────┐
│ [CardHeader: CardTitle small-caps + description]                        │
│ [Separator vertical] icon latest                                       │
│ [CardContent: 2xl value + muted sub]            [Skeleton while pending] │
├──────────────────────────────────────────────────────────────────────────┤
│ Rooms: Card grid (3 cols)  RoomCard (Header/Content/Footer) + Skeleton   │
├──────────────────────────────────────────────────────────────────────────┤
│ All Connected Nodes: Card wrapping Table                                  │
│  TableHeader: name/type/room/devId/status/thresholds/created (sortable   │
│   with Button variant=ghost size=sm + ArrowUpDown)                       │
│  TableBody: Badge type mono · Room Badge · MAC font-mono · Badge status │
│           · Threshold default muted · Separator between sections         │
└──────────────────────────────────────────────────────────────────────────┘
```

### Map — Tabs + Card canvas + Empty

```
┌─ Tabs ──────────────────────────────────────────────────────────────────┐
│ TabsList → TabsTrigger "Floor Plan"  TabsTrigger "Topology"             │
│ TabsContent floor-plan: Card → floor-plan img + markers → Tooltip        │
│   Empty when no rooms / no image (with Empty Title/Description)         │
│ TabsContent topology: Card + MiniMap + Controls + Separator             │
└──────────────────────────────────────────────────────────────────────────┘
```

## Decisions

### D1 — Palette (6 named hex, @theme inline, semantic tokens, no raw overrides)

```css
/* dashboard/src/index.css — @theme inline (Tailwind v4) */
@theme inline {
  --color-background: #09090b;  /* zinc-950 */
  --color-foreground: #fafafa;
  --color-card: #18181b;         /* zinc-900 */
  --color-card-foreground: #fafafa;
  --color-popover: #18181b;
  --color-popover-foreground: #fafafa;
  --color-primary: #6366f1;      /* indigo — temp line, primary buttons */
  --color-primary-foreground: #ffffff;
  --color-secondary: #27272a;    /* zinc-800 */
  --color-secondary-foreground: #fafafa;
  --color-muted: #27272a;
  --color-muted-foreground: #a1a1aa; /* zinc-400 */
  --color-accent: #14b8a6;       /* teal-500 — humidity / ATS secondary */
  --color-accent-foreground: #09090b;
  --color-destructive: #ef4444;  /* red-500 — critical */
  --color-border: #27272a;
  --color-input: #27272a;
  --color-ring: #6366f1;
  --color-chart-1: #6366f1;      /* temp */
  --color-chart-2: #14b8a6;      /* humidity */
  --color-chart-3: #f59e0b;      /* amber warning */
  --color-chart-4: #ef4444;      /* red critical */
  --color-chart-5: #a1a1aa;      /* gap */
  --radius: 0.625rem;            /* new-york */
  --font-sans: "Inter", system-ui, sans-serif;
  --font-mono: "Fragment Mono", ui-monospace, monospace;
  --font-serif: "Source Serif 4", ui-serif, serif;
}
```

- Use `bg-background`, `text-muted-foreground`, `bg-primary`, `border`, `text-primary`, never `bg-blue-500` or `dark:text-white`.
- `cn()` composes only layout (`gap-*`, `flex`, `grid`), never color overrides on shadcn primitives.

### D2 — Type (3 roles, explicit scale, no single-font template)

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fragment+Mono&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');
```

- **Display:** `Source Serif 4` for `h1/h2` display (`text-2xl font-semibold tracking-tight font-serif`) — thesis is the device identity on dark.
- **Body:** `Inter` for all UI, 400/500/600 weights, clear scale `xs 12, sm 14, base 16, xl 24`.
- **Data:** `Fragment Mono` for `Badge`, `TableCell font-mono`, chart ticks/tooltip, MAC/coord, thresholds.
- No `Inter everywhere` template: display uses serif sparingly (header titles only) so it reads intentionally.

### D3 — Layout (12-col, sticky header, 8/4 device split)

- `routes/device.$deviceId.tsx`: `<div className="sticky top-0 z-10 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b">` header; body is `className="grid grid-cols-12 gap-6"` with chart `col-span-12 lg:col-span-8` and controls `col-span-12 lg:col-span-4`.
- `routes/index.tsx`: stats `grid-cols-1 md:grid-cols-4 gap-4` with `Card`; rooms `grid-cols-1 sm:grid-cols-2 xl:grid-cols-3`; nodes Table in `Card overflow-hidden` + inner `overflow-x-auto`.
- `routes/map.tsx` + `components/TopologyView.tsx`: `Tabs defaultValue="floor-plan"` single state, no hand `useState` view flag.

### D4 — Signature (hairline trace)

- Temperature/ATS lines `strokeWidth="1.5"` (0.75px on high DPI) + `dot={false}` + `activeDot={{ r: 3, strokeWidth: 2 }}` + `type="monotone"` smoothing `0.18`.
- Area under temp `fill="url(#tempGradient)"` linear `stopOpacity 0.18→0.02`.
- `ReferenceLine` thresholds `strokeDasharray="4 4"` `strokeWidth={1.25}` `opacity={0.9}`.
- `ReferenceArea` for gaps `fill="var(--color-muted)" fillOpacity={0.08}` `strokeOpacity={0}` (not opaque `#52525b`).
- Stagger not needed on chart; apply to cards instead (see Motion).

### D5 — Tailwind v4 @theme inline (not tailwind.config.js)

- Project already uses `@tailwindcss/vite` with empty `tailwind.config` per `components.json`. All tokens live in `src/index.css` `@theme inline` (migrated from inline hex to variable block above). No `tailwind.config.ts` introduced.
- `vite.config.ts` already includes `@tailwindcss/vite` plugin; verify `content` covers `src/**/*.{ts,tsx}`.

### D6 — shadcn composition rules (absolute, no guessing)

Every rule maps to a before/after the weak model must follow verbatim:

```tsx
// Card — correct (Title/Description in Header, not Content)
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
<Card>
  <CardHeader><CardTitle>Total Rooms</CardTitle><CardDescription>Across facility</CardDescription></CardHeader>
  <CardContent><p className="text-2xl font-bold">12</p></CardContent>
  <CardFooter><span className="text-xs text-muted-foreground">Live 3s polling</span></CardFooter>
</Card>
// Wrong: <Card><CardContent><h3>Total Rooms</h3></CardContent></Card>

// Dialog — always needs Title for a11y
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
<Dialog open={open} onOpenChange={setOpen}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Command Control: {name}</DialogTitle>
      <DialogDescription>Queue a command for edge delivery via pending_commands</DialogDescription>
    </DialogHeader>
    {/* FieldGroup ... */}
    <DialogFooter><Button>Queue Command</Button></DialogFooter>
  </DialogContent>
</Dialog>
// Wrong: <div className="fixed inset-0 bg-black/70"><h3>Command</h3></div>

// Select — items inside Group
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
<Select value={value} onValueChange={setValue}>
  <SelectTrigger><SelectValue placeholder="Select device" /></SelectTrigger>
  <SelectContent><SelectGroup>
    <SelectItem value="all">All devices</SelectItem>
    <SelectItem value="ATS-4F12">ATS-4F12</SelectItem>
  </SelectGroup></SelectContent>
</Select>
// Wrong: <Select><SelectItem> outside <SelectGroup>

// Tabs — triggers inside TabsList
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
<Tabs defaultValue="floor-plan"><TabsList>
  <TabsTrigger value="floor-plan">Floor Plan</TabsTrigger>
  <TabsTrigger value="topology">Topology</TabsTrigger>
</TabsList><TabsContent value="floor-plan">…</TabsContent></Tabs>

// ToggleGroup — for 2-7 choices (mode/genset/range)
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
<ToggleGroup type="single" value={mode} onValueChange={setMode} variant="outline" size="sm">
  <ToggleGroupItem value="auto">Auto</ToggleGroupItem>
  <ToggleGroupItem value="manual">Manual</ToggleGroupItem>
</ToggleGroup>
// Wrong: loop Button with manual active state

// Field / FieldGroup — form layout (not div+space-y)
import { FieldGroup, Field, FieldLabel, FieldDescription } from "@/components/ui/field"
import { InputGroup, InputGroupInput, InputGroupAddon } from "@/components/ui/input-group"
<FieldGroup>
  <Field>
    <FieldLabel htmlFor="warn">Warning Threshold</FieldLabel>
    <InputGroup>
      <InputGroupInput id="warn" type="number" value={w} onChange={…} />
      <InputGroupAddon align="inline-end">°C</InputGroupAddon>
    </InputGroup>
    <FieldDescription>Trigger warning alert above this temperature</FieldDescription>
  </Field>
</FieldGroup>

// Alert — for callouts (not custom div)
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
<Alert variant="destructive"><AlertTriangle /><AlertTitle>Threshold outside range</AlertTitle><AlertDescription>…</AlertDescription></Alert>

// Empty — for zero states
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia } from "@/components/ui/empty"
<Empty><EmptyMedia><Clock className="size-8" /></EmptyMedia><EmptyHeader><EmptyTitle>No schedules yet</EmptyTitle></EmptyHeader><EmptyDescription>Create…</EmptyDescription></Empty>

// Separator — instead of <hr> or border div
import { Separator } from "@/components/ui/separator"
<Separator />             {/* horizontal */}
<Separator orientation="vertical" />

// Skeleton — no animate-pulse div
import { Skeleton } from "@/components/ui/skeleton"
<Skeleton className="h-4 w-24" />

// Badge — not custom span
import { Badge } from "@/components/ui/badge"
<Badge variant="secondary">{dev_type}</Badge>
<Badge variant={isOnline ? "default" : isPending ? "secondary" : "outline"}>{label}</Badge>

// Tooltip — origin-aware
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip"
<TooltipProvider><Tooltip><TooltipTrigger>…</TooltipTrigger><TooltipContent>…</TooltipContent></Tooltip></TooltipProvider>

// Avatar — always needs fallback
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
<Avatar className="size-8"><AvatarFallback>{initials}</AvatarFallback></Avatar>

// Spacing/sizing rules (shadcn styling.md)
<div className="flex flex-col gap-4">   {/* correct */}
<div className="space-y-4">            {/* wrong */}
<Avatar className="size-8">            {/* correct */}
<Avatar className="w-8 h-8">           {/* wrong */}
<div className="truncate">             {/* correct */}
<div className="overflow-hidden text-ellipsis whitespace-nowrap"> {/* wrong */}
<Button><SearchIcon data-icon="inline-start" />Search</Button>  {/* correct, no size-4, use data-icon */}

// Semantic colors (styling.md)
<div className="bg-primary text-primary-foreground"> {/* correct */}
<div className="bg-[#6366f1] text-white">            {/* wrong */}
```

### D7 — Motion (emil design eng, invisible details compound)

```css
/* Tokens */
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);

/* Button press — must feel responsive */
.button { transition: transform 120ms var(--ease-out), background-color 150ms var(--ease-out); }
.button:active { transform: scale(0.97); }

/* Tooltip/popover — scale from trigger, never from center on popover */
.tooltip, .popover {
  transition: transform 125ms var(--ease-out), opacity 125ms var(--ease-out);
  transform-origin: var(--transform-origin);
}
.tooltip[data-starting-style], .tooltip[data-ending-style] { opacity: 0; transform: scale(0.95); }
.tooltip[data-instant] { transition-duration: 0ms; }

/* Card stagger on overview (30-80ms, decorative only, no interaction block) */
.card-stagger { opacity: 0; transform: translateY(8px); animation: fadeIn 300ms var(--ease-out) forwards; }
.card-stagger:nth-child(1) { animation-delay: 0ms; }
.card-stagger:nth-child(2) { animation-delay: 50ms; }
/* ... */
@keyframes fadeIn { to { opacity: 1; transform: translateY(0); } }

/* Chart tooltip — transition, not keyframes; interruptible */
.recharts-tooltip-wrapper { transition: transform 150ms var(--ease-out); }

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .button:active { transform: none; }
  .tooltip, .popover, .card-stagger, .recharts-tooltip-wrapper { transition: none; animation: none; transform: none; }
}
@media (hover: hover) and (pointer: fine) {
  .button:hover { filter: brightness(1.05); }
}
```

- No `transition: all 300ms`.
- Never `scale(0)` — start from `scale(0.95)` + `opacity: 0`.
- Popovers `transform-origin: var(--transform-origin)` (Base UI); modals keep `center`.
- Durations under 300ms except `card-stagger` (still 300ms max).
- Use `transform` + `opacity` only (GPU); never animate `height/margin`.

### D8 — Vercel composition (compound components, explicit variants, provider)

```tsx
// HistoryChart — compound + provider + explicit variants
// State is dependency-injected; UI only knows the context interface

interface HistoryChartState {
  points: TelemetryHistoryPoint[]
  timeRange: '6h'|'24h'|'7d'|'30d'
  warningThreshold: number|null
  criticalThreshold: number|null
  devType: string
}
interface HistoryChartActions { setTimeRange: (r: HistoryChartState['timeRange'])=>void }
interface HistoryChartMeta { gapThresholdMs: number }

// Generic context (state/actions/meta)
const HistoryChartContext = createContext<{ state: HistoryChartState; actions: HistoryChartActions; meta: HistoryChartMeta }|null>(null)
function HistoryChartProvider({ children, state, actions, meta }: { children: React.ReactNode; state: HistoryChartState; actions: HistoryChartActions; meta: HistoryChartMeta }) {
  return <HistoryChartContext value={{ state, actions, meta }}>{children}</HistoryChartContext>
}
function useHistoryChart() { const v = use(HistoryChartContext); if (!v) throw new Error("HistoryChart.* must be inside HistoryChartProvider"); return v }

// Compound leaves
function HistoryChartFrame({ children }: { children: React.ReactNode }) { return <Card className="overflow-hidden">{children}</Card> }
function HistoryChartHeader() { const { state } = useHistoryChart(); /* Badge row + Separator + Tiny legend */ return (… ) }
function HistoryChartCanvas() {
  const { state, meta } = useHistoryChart()
  // ComposedChart config is split per variant, not boolean prop:
  // Avoid isATS boolean — create explicit TSChartVariant vs ATSChartVariant
  return state.devType==="ATS" ? <ATSChartVariant/> : <TSChartVariant/>
}

// Explicit variants (patterns-explicit-variants)
function TSChartVariant() {
  // left YAxis temp [15,30], right YAxis humid [0,100]
  // Lines: temp stroke var(--chart-1) 1.5, humid stroke var(--chart-2) 1.5, dashed aki
  // ReferenceLine thresholds on yAxisId="temp"
  // Brush, Tooltip, ReferenceArea for gaps
  return (
    <ChartContainer config={tsChartConfig}>
      <ComposedChart data={chartData} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--color-border)" opacity={0.5} />
        <XAxis dataKey="t" tickFormatter={…} tick={{ fill: "var(--color-muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }} />
        <YAxis yAxisId="temp" domain={[15,30]} tick={{ fill: "var(--color-muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }} width={36} />
        <YAxis yAxisId="humid" orientation="right" domain={[0,100]} tickFormatter={(v)=>`${v}%`} tick={{ fill: "var(--color-muted-foreground)", fontFamily: "var(--font-mono)", fontSize: 10 }} width={40} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={formatTooltipTime} indicator="dot" />} cursor={{ strokeDasharray: "3 3" }} />
        <ReferenceLine yAxisId="temp" y={warningThreshold} stroke="var(--color-chart-3)" strokeDasharray="4 4" strokeWidth={1.25} />
        <ReferenceLine yAxisId="temp" y={criticalThreshold} stroke="var(--color-chart-4)" strokeDasharray="4 4" strokeWidth={1.25} />
        {outages.map((o,i)=><ReferenceArea key={i} x1={o.start} x2={o.end} yAxisId="temp" fill="var(--color-muted)" fillOpacity={0.08} strokeOpacity={0} />)}
        <Line yAxisId="temp" type="monotone" dataKey="temp" stroke="var(--color-chart-1)" strokeWidth={1.5} dot={false} activeDot={{ r: 3, strokeWidth: 2 }} connectNulls={false} />
        <Line yAxisId="humid" type="monotone" dataKey="humid" stroke="var(--color-chart-2)" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }} connectNulls={false} />
        <Area yAxisId="temp" type="monotone" dataKey="temp" fill="url(#tempGradient)" stroke="none" />
        <Brush dataKey="t" height={24} stroke="var(--color-border)" fill="var(--color-card)" travellerWidth={8} />
      </ComposedChart>
    </ChartContainer>
  )
}
function ATSChartVariant() { /* single Y 0..max*1.05, 3 Lines: pln emerald, genset amber, aki indigo dashed */ }

// Export compound
export const HistoryChart = {
  Provider: HistoryChartProvider,
  Frame: HistoryChartFrame,
  Header: HistoryChartHeader,
  Canvas: HistoryChartCanvas,
  TS: TSChartVariant,
  ATS: ATSChartVariant,
}
```

- `architecture-avoid-boolean-props`: never `HistoryChart isTS isATS showBrush` — use explicit `TSChartVariant`/`ATSChartVariant`.
- `architecture-compound-components`: `Provider` wraps `Frame`→`Header`→`Canvas`; children compose, no `renderHeader` prop.
- `state-decouple-implementation` + `state-context-interface` + `state-lift-state`: provider owns gap computation; `Header`/`Canvas` read via `use(HistoryChartContext)` (React 19 `use()` not `useContext`).
- `patterns-children-over-render-props`: control appearance is via children composition, not `renderTooltip` callback.
- `react19-no-forwardref`: `ref` is regular prop if needed; not `forwardRef`.

## Migration Plan

1. **Token pass** — update `dashboard/src/index.css` `@theme inline` (add `accent`, `chart-*`, `font-mono/serif`), add Google Fonts import (Inter/Fragment Mono/Source Serif 4), add motion tokens + stagger + reduced-motion; verify `components.json` unchanged.
2. **shadcn add** — `npx shadcn@latest add chart separator alert skeleton tooltip avatar empty input-group field toggle-group --overwrite` in `dashboard/` (runner per `components.json` `packageManager`). Verify `aliases.utils` rewrite, no extra `z-index` on overlays.
3. **chartUtils → null gaps** — `lib/chartUtils.ts` unchanged API; add helper `toChartData(points, gapThresholdMs)` that emits `{ t, temp, humid, pln, genset, aki }` with gaps as `null` (not outage rects). Keep `getGapThresholdMs`/`getOutages` but map outages to `ReferenceArea` X domain.
4. **HistoryChartProvider** — create `components/device/HistoryChartProvider.tsx` or co-locate in `HistoryChart.tsx` with compound export; `ATSChartVariant`/`TSChartVariant` explicit components.
5. **Device header folding** — `routes/device.$deviceId.tsx`: replace 6-card grid (delete `Node Information` block lines 94-106) with header `flex flex-wrap gap-2` `Badge` row: hub `variant="outline"` + `Tooltip` coordinate + date `text-xs text-muted-foreground` + `Separator`; move thresholds to chart header ligand; polling badge uses `Badge variant="outline"` + `Spinner`.
6. **Dashboard overview** — `routes/index.tsx`: 4 stat Cards, rooms grid with `RoomCard` updated, nodes `Table` with sortable `Button variant="ghost"` headers + `Badge`/`Avatar` cells + `Separator` + `Skeleton` + `Empty`.
7. **Room/Topology/Map** — `routes/room.$roomId.tsx`: `Dialog` with `DialogTitle`; `routes/map.tsx`: `Tabs` + `Empty`; `components/RoomCard.tsx` + `TopologyView.tsx`: full Card/badge/separator/tooltip pass.
8. **Controls/Thresholds** — `components/device/Controls.tsx` + settings threshold form: `FieldGroup`→`Field`→`FieldLabel` + `ToggleGroup` + `SelectGroup`→`SelectItem` + `InputGroup` + `Alert` + `Separator`; buttons with `data-icon`.
9. **Schedules polish** — audit `routes/schedules.tsx` against D6 checklist; only token/type/motion deltas.
10. **Verification** — `npm run lint` (0 errors, 14 fast-refresh warns ok), `npm run build` (`tsc -b` + `vite build` hidden sourcemap), `npm test -- --run` (vitest), `npx playwright test --list`, `pytest` at root (107 tests), `docker compose config` still `127.0.0.1:5432/1883`, `bash -n deploy/setup_push_deploy.sh`.

## Risks

- **Regressions in data shape:** chart `dataKey` must match `toChartData` output; test with `temp null` edge case and empty `points`.
- **Base UI vs Radix interop:** Base UI uses `data-starting-style` not Radix `data-state`; motion CSS must target `data-starting-style`/`data-ending-style` per emil.
- **Tooltip `transform-origin` leak:** ensure `style={{ "--transform-origin": "…" }}` flows from `Tooltip`; no hardcoded `center`.
- **Bundle creep:** `recharts` is the heaviest add; code-split via `React.lazy(() => import("./HistoryChart"))` if `vite build` reports `>60kB` chunk.
- **Copy-paste drift:** weak model may invent `isPending` on `Button` or `space-y-*` — tasks explicitly forbid both with oxlint grep.
