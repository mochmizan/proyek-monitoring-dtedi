# Proposal: Dashboard Full shadcn Redesign + Chart Fix + Node Folding

## Summary

Full shadcn/ui `new-york` (Base UI) redesign of the SMSB dashboard to replace generic Tailwind template markup with composed shadcn primitives, fix the unreadable Telemetry History chart, and fold the wasteful 6-card Node Information grid into header badges. The existing `dashboard/src/components/device/HistoryChart.tsx` custom 800×260 SVG renders temperature and humidity on a single shared Y-axis: humidity (30-95%) compresses the temperature line (22-29°C) into a flat 4-pixel trace, thresholds float incorrectly, and gaps are painted as opaque `#52525b` rectangles. The `dashboard/src/routes/device.$deviceId.tsx` Node Information block consumes 6 `bg-zinc-950` cards for hub/room/date/coordinate/thresholds that belong inline. This proposal converges all dashboard surfaces — Overview stats + Room cards + All Connected Nodes Table + Device Telemetry + Controls + Thresholds + Floor Map/Topology + Schedules — onto shadcn `new-york` with design tokens `--color-background:#09090b` / `--color-primary:#6366f1` + accent teal `#14B8A6` + amber `#F59E0B`, Inter + Fragment Mono + Source Serif 4 typography, and a signature hairline trace. Schedules (`dashboard/src/routes/schedules.tsx`) is already migrated and is the reference pattern; this change finishes the migration so every route satisfies shadcn composition, emil motion, and Vercel composition guidelines.

## Motivation

### 1. Chart is unreadable — single Y-axis destroys signal

**Current:** `HistoryChart.tsx:49-74` computes `minY/maxY` as `Math.min(temp..., humid...)` / `Math.max(temp..., humid...)` then flattens with `Math.max(span,6)`. A typical TS reading is `temp 25.4°C / humid 68%`. Because both map to one scale, a 2°C swing (25→27) occupies `(2/45)*plotHeight ≈ 11px` while humidity dominates the domain. The temperature line reads flat; operators cannot detect drift.

```
Current (shared Y 15–95):
  humid 68 ──────────────╮ indigo 2.5px
  temp  25 ── ······ ──  ╯ emerald 2px  ← 4px visual range
  Y: 0 ────────────────── 100
  Result: temp appears dead, thresholds meaningless
```

Humidity should use a right axis `0-100%`; temperature should use a left axis `15-30°C` (padded). Thresholds (`warning`/`critical`) are temperature-only and must anchor to the left axis, not the blended domain.

### 2. Node Information wastes 40% of device page vertical space

`device.$deviceId.tsx:94-106` renders 6 equal `bg-zinc-950 p-3 rounded border` cards for: Gateway Hub, Room Assignment, Registered Date, Map Coordinate, Warning Level, Critical Level. This is metadata, not content. It pushes Device Alert Log below the fold and repeats information already in the header subtitle (`MAC / ID · Type · Room`) and polling badge. Campos et al. (Vercel dashboard) fold this into `Badge` + `Tooltip` + `Separator` inline.

### 3. Generic template everywhere else

- `routes/index.tsx` stats are raw `bg-zinc-900 border rounded-lg` divs, not `CardHeader`/`CardTitle`/`CardContent`.
- The `All Connected Nodes` table is hand-rolled `<table>` + `<th>` + `statusDot` span instead of `Table` + `TableHeader` + `Badge` + sortable `Button variant="ghost"`.
- `routes/room.$roomId.tsx` command modal is a `fixed inset-0 bg-black/70` div without `DialogTitle`/`DialogDescription` (fails a11y).
- `routes/map.tsx` tabs are `<button className="pb-3 border-b-2">` not `TabsList`/`TabsTrigger`.
- `components/RoomCard.tsx` and `components/TopologyView.tsx` use ad-hoc status spans instead of `Badge variant="secondary|outline"` + semantic tokens.
- `index.css` imports Inter only; no mono (data) or serif (display) pairing — the brief forbid "one font everywhere."

### 4. Why shadcn `new-york` / Base UI now

- `dashboard/components.json` already declares `style: new-york`, `baseColor: zinc`, `cssVariables: true`, `tailwind.css: src/index.css`, `tailwindVersion: v4` via `@tailwindcss/vite`. The previous change (`ats-flexible-schedule-2026-08-29`) proved the pipeline (`@tailwindcss/vite` + Radix → Base UI migration path). Two design systems cannot ship.
- Admins live in this dashboard; generic styling erodes trust. A distinctive hairline-trace chart with calibrated dual-axis and motion-polished controls is the competitive signal in a campus LAN where feature count is equal.
- `npx shadcn@latest add chart separator alert skeleton tooltip avatar empty input-group field` is incremental (no rebuild), tree-shaken, and replaces the hand SVG with a maintained `ChartContainer` (Recharts) wrapper.

## What Changes

### In scope — full migration checklist

| Surface | File(s) | From | To |
|---|---|---|---|
| **Tokens** | `dashboard/src/index.css` | Inter only, 4 colors | `@theme inline` 6 hex + 3 typefaces |
| **Chart** | `components/device/HistoryChart.tsx` + `lib/chartUtils.ts` | custom SVG single-Y, fixed 800×260, `outage rect` | `Chart` (Recharts) `ComposedChart` dual `YAxis` (left temp `15-30`, right humid `0-100`), `ReferenceLine` thresholds on left, `ReferenceArea` for gaps (`null` breaks), `Brush`, synced `ChartTooltip` |
| **Device header** | `routes/device.$deviceId.tsx` header | `h1 + status span + <p> MAC` + polling `div` | sticky `CardHeader` pattern + `Badge` status + `Tooltip` + hub/room/date/coordinate folded inline; `Skeleton` while pending; remove 6-card grid entirely |
| **Node Information folding** | `routes/device.$deviceId.tsx:94-106` | 6-card grid | Deleted; data moved: hub→`Badge variant="outline"` in header, room→`Badge` + link, coordinate→`Tooltip` on map pin icon, warning/critical→inline `Alert` threshold row inside chart header + `Field` in controls |
| **Dashboard Overview** | `routes/index.tsx:141-177` stats + `189-204` rooms + `206-298` nodes table | raw divs + hand table | `Card` x4 (Total Rooms / Active Devices / Warning / Critical) with `CardHeader`→`CardTitle`/`CardDescription`→`CardContent`; `Separator` between icon/stat; `Skeleton` during `isInitialLoading`; nodes table → `Table` + `TableHeader` + `TableBody` + `TableRow` + `TableHead` (sortable via `Button variant="ghost" size="sm"` + `ArrowUp/Down`) + `TableCell` + `Badge` + `Avatar` fallback |
| **Device telemetry header** | `HistoryChart` stats grid | 4 `bg-zinc-950` divs | `Card` composition inside chart chrome + `ChartContainer` |
| **Controls** | `components/device/Controls.tsx` (room modal excerpt duplicates) | `select` + native `checkbox` + stacked buttons | `FieldGroup` + `Field` + `FieldLabel` + `Select` (`SelectGroup`→`SelectItem`) + `ToggleGroup type="single"` for mode/genset + `InputGroup` + `Alert` feedback + `Button` with `data-icon` |
| **Thresholds** | `routes/settings.tsx` threshold form (implied) | raw inputs | `FieldGroup` + `Field` + `FieldDescription` + `InputGroupAddon` (°C) + `Separator` sections |
| **Floor Map / Topology** | `routes/map.tsx` + `components/TopologyView.tsx` | custom floor-plan + raw tabs | `Tabs` (`TabsList`→`TabsTrigger`→`TabsContent`), `Card` map frame, `Separator` between legend and canvas, `Tooltip` marker details (with `var(--transform-origin)`), `Empty` for no rooms / no image |
| **Room detail** | `routes/room.$roomId.tsx` | `fixed inset-0` modal + hand floor-plan | `Dialog` (`DialogTitle` required) + `Drawer` mobile fallback + `Sheet` alternate, same `Card` floor-plan treatment, `Badge` for device type |
| **Schedules** | `routes/schedules.tsx` | — | **Already done** — audited, kept, polished to match new tokens/type (no regression) |
| **Shared** | `components/RoomCard.tsx` | ad-hoc status span | `Card` + `CardHeader` + `CardContent` + `CardFooter` + `Badge` + `AvatarFallback` + `Skeleton` import fix |
| **Icons** | all routes | `size-4` on icons inside buttons | remove sizing; rely on component CSS; add `data-icon="inline-start|end"` |

### Out of scope

- Server `app/` routers/services, hub `main.py`, firmware `.ino` sketches, DB schema — unchanged except documenting chart payload shape already stored.
- Adding new pages/routes or changing polling (`POLL_MS=3000`) or auth (`GET /api/auth/me`).
- Replacing TanStack Router/Query/Zustand or rewriting `scheduleApi.ts`/`queryKeys.ts`.

## Capabilities

### New

- `dashboard-ui` — shadcn `new-york` Base UI system: tokens, type, layout, motion, and primitive composition for every dashboard surface.
- `chart` — dual-Y telemetry chart with correct domains, threshold anchoring, gap handling, brush, and responsive tooltip.

### Modified

- `dashboard-overview`, `room-cards`, `nodes-table`, `floor-map`, `topology`, `device-detail`, `device-controls`, `thresholds-form`, `schedules-polish` (all under `dashboard-ui` umbrella; `schedules` retains behavior, only tokens/type pass).

## Impact

- **Code:** `dashboard/src/index.css` (`@theme inline` expanded), `dashboard/components.json` (`style: new-york` retained), ~12 `components/ui/*` newly added or updated (`chart`, `separator`, `alert`, `empty`, `skeleton`, `input-group`, `field`, `tooltip`, `badge`, `avatar`, `tabs`, `card` polish), `lib/chartUtils.ts` gap→null transform, every route under `routes/` + `components/` touched with diff-like precision (no wholesale rewrite without audit).
- **Dependencies:** add `recharts` (peer of `chart`), already have `@tailwindcss/vite`, `lucide-react`, `zod`; no new server deps.
- **Build:** `tsc -b && vite build` must stay green; hidden sourcemap retained; bundle delta target +30-55 kB gzipped (chart is heaviest; lazy if >60).
- **UX:** Chart temperature variation becomes legible (15-30 left axis magnifies 2°C to ~28% of plot). Node metadata drops from 6 cards to 1 inline row. Sorting moves from custom `<Link>` in `<th>` to accessible `Button` pattern with `aria-sort`. All surfaces share one visual language.
- **Ops:** Same-origin proxy unchanged (`/api`→`:8000`), Nginx `443→127.0.0.1:8000`, no CORS change.
- **Docs:** `dashboard/AGENTS.md` Child DOX Index unchanged; root `AGENTS.md` verification unchanged.

## Decisions

| ID | Topic | Verdict | Rationale |
|---|---|---|---|
| **C1** | Chart primitive | **ADD shadcn `chart` (Recharts) vs keep custom SVG** | Custom SVG forced manual scales, tooltip math, and responsivity. `ChartContainer` + `ComposedChart` gives `ResponsiveContainer`, `Brush`, `Tooltip`, dual `YAxis`, `ReferenceLine/Area` for free, themed via `--chart-*` CSS vars. Cost ~12kB gzipped vs maintaining 289 lines of manual path math. Preserve `chartUtils.getGapThresholdMs` logic but map gaps to `null` values + `ReferenceArea`. |
| **C2** | Dual YAxis vs stacked vs normalized | **Dual YAxis: left temp `domain=[15,30]` right humid `domain=[0,100]`** | Stacked bars hide correlation; normalized 0-1 loses units and operator intuition (`25.4°C` must read as 25.4). Dual axis keeps both units legible; temp zoom amplifies drift. Reject `normalize to 0-100` — violates "words are design material" (units matter). |
| **C3** | Node info folding | **Delete 6-card grid; fold into header `Badge` row + `Tooltip` + `Separator`** | Metadata density: 6 cards for 6 facts is `1:1` card:fact absurdity. Header badges with `Tooltip` carry hub/room/coordinate without scroll tax. Warning/critical move to inline `FieldDescription` + chart threshold row. Frees ~260px vertical for chart + alerts. |
| **C4** | Token palette | **6 named hex: zinc `#09090b` bg, indigo `#6366f1` primary, teal `#14B8A6` humid/ATS, amber `#F59E0B` warning, red `#EF4444` critical, `zinc-800 #27272A` border** | Existing tokens already define `background:#09090b` + `primary:#6366f1`. Teal complements indigo on Itten wheel and maps to humidity/cold/telemetry; amber is already `status-warning` (`#f59e0b` exists) — normalize to uppercase consistent. Red/critical already aligned. |
| **C5** | Typography | **Display `Source Serif 4`, body `Inter`, mono `Fragment Mono` (Google Fonts) — 3 roles** | Brief demands distinctive type: serif display for `h1/h2` (monitoring thesis), Inter for body, Fragment Mono for `Badge`, `TableCell font-mono`, chart ticks/tooltip. Pair carried by shadcn typography tokens, not ad-hoc classes. |
| **C6** | Signature | **Hairline trace — 0.75px `stroke` + `dot: false` + `activeDot r=3` + `ReferenceLine strokeDasharray="4 4"` + subtle `Area` gradient `0.18→0.02` opacity** | Maximalist glow rejected. Signature is precision: the chart reads like an oscilloscope trace on zinc, not a crayon. Teal/Indigo lines at hairline weight are the memorable element; everything else stays quiet. Justifies the chart budget. |
| **C7** | Schedules scope | **Polish-only (tokens/type/motion)** | `schedules.tsx` already uses `Card/Table/Select/Dialog/Switch/Badge/Button`. Rewriting risks regression. Touch only: replace remaining `space-y-*` with `gap-*`, ensure `Label` + `Field`, ensure `Separator` between dialog sections, ensure `Tooltip` `var(--transform-origin)`. |
| **C8** | Preset/style choice | **Keep `new-york` (already in `components.json`); Base UI enabled** | `new-york` is the project contract. Switching to `default` would churn every component. Base UI is the forward path per shadcn docs; `npx shadcn@latest init` with Base UI aligns with the AST migration already done. |

## Risks / Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Bundle exceeds 60kB** | LCP regression on LAN | `chart` lazy-load via `React.lazy` on `device.$deviceId` route only; `Brush` behind feature flag; measure with `vite build --mode production` |
| **Recharts dual axis misaligned on narrow screens** | Ticks clip | `ChartContainer` `ResponsiveContainer` with `margin` via CSS vars; test at 320/768/1024; snapshot tests for tick count |
| **Deleting 6-card grid loses copy-pastable MAC** | Operators copy `dev_id` | Header `Badge` keeps `font-mono` full `dev_id` + `Tooltip` "Click to copy" + `navigator.clipboard.writeText`; fallback to selection |
| **Threshold `ReferenceLine` outside domain** | Line invisible | Clamp: render only if `warn/crit ∈ [15,30]`; show `Alert variant="default"` "Threshold outside chart range" otherwise |
| **Motion triggers on `prefers-reduced-motion`** | Vestibular trigger, a11y fail | Gate all `scale`/`translate` behind `@media (prefers-reduced-motion: reduce) { transition: none; transform: none; }`; keep `opacity` only for comprehension |
| **shadcn CLI `add` churns `components.json` alias** | Import break | Verify `aliases.components= "@/components"` + `utils= "@/lib/utils"` unchanged post-add; forced `use client` not needed (Vite SPA, `rsc:false`) |
| **Null gap breaks line continuity** | Isolated dots lost | Preserve `isolated` dot logic: when a segment collapses to 1 point, render `<circle r=3>` via `Customized` or separate `Scatter`; cover with test |

## Alternatives Considered

- **Keep custom SVG, just tweak `minY/maxY`:** Rejected — leaves gap rendering, tooltip, brush, responsivity as bespoke bugs. The 289-line manual path builder is already at its complexity ceiling.
- **Stacked temperature+humidity bars:** Rejected — humidity 68 dwarfs temp 25; product insight requires correlation on same X with distinct Y.
- **Normalize both to 0-1:** Rejected — loses units, violates operational readability (`25.4°C` must be read, not inferred from `0.34`).
- **Card-per-fact for Node Information:** Rejected — information density violation; verified against `RoomCard` pattern which uses 1 card with footer `Separator`, not N cards.
