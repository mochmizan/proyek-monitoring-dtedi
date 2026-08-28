# Spec: dashboard-ui

## Purpose

shadcn `new-york` Base UI system for every dashboard surface, plus the Node Information folding that frees the device page for the chart. This spec covers tokens, composition contracts, and page-level behavior; chart-specific ranges are in `specs/chart/spec.md`. `schedules` retains behavior and is polished to match new tokens/motion.

## ADDED Requirements

### Requirement: Design tokens via Tailwind v4 @theme inline

The system SHALL expose 6 named hex tokens plus status/border tokens and 3 typefaces via `dashboard/src/index.css` `@theme inline`, using semantic `bg-background`/`text-muted-foreground`/`bg-primary` etc. throughout components and forbidding raw `bg-blue-500` or `dark:` overrides.

#### Scenario: Token palette present

- **WHEN** `src/index.css` is read after the change
- **THEN** it contains `@theme inline` with `--color-background: #09090b`, `--color-primary: #6366f1`, `--color-accent: #14b8a6`, `--color-border: #27272a`, `--color-chart-1: #6366f1`, `--color-chart-2: #14b8a6`, `--color-chart-3: #f59e0b`, `--color-chart-4: #ef4444`, `--radius: 0.625rem`, and `--font-mono: "Fragment Mono"` / `--font-serif: "Source Serif 4"` plus `Inter` import

#### Scenario: Semantic colors used everywhere

- **WHEN** any dashboard `.tsx` file renders a styled element
- **THEN** it uses `bg-background`, `bg-card`, `text-muted-foreground`, `border`, `text-primary`, `bg-primary`, `bg-secondary`, `text-destructive`, `bg-muted`, `text-accent` — and `rg "bg-red-500|bg-blue|text-white"` grep outside tokens finds zero hits

### Requirement: Typography roles

The system SHALL use 3 type roles: Display (`Source Serif 4`) for page `h1/h2`, Body (`Inter`) for UI, Data (`Fragment Mono`) for mono contexts (Badge, TableCell, chart ticks/tooltip, MAC/coordinate, thresholds).

#### Scenario: Device header uses serif display

- **WHEN** `routes/device.$deviceId.tsx` header renders `device.dev_name` as title
- **THEN** the `<h1>` carries `className="font-serif text-2xl font-semibold tracking-tight"` (not `font-sans`) and the MAC `Badge` carries `font-mono`

#### Scenario: Table data cells monospace

- **WHEN** `routes/index.tsx` nodes Table renders MAC / ID column
- **THEN** the `TableCell` contains `className="font-mono text-xs"` and the type cell uses `<Badge variant="secondary" className="font-mono">`

### Requirement: Card composition (CardHeader/Title/Description/Content/Footer)

Every Card SHALL use full composition `Card`→`CardHeader`→`CardTitle`/`CardDescription`→`CardContent`→(`CardFooter`|`Separator`) and SHALL NOT dump content into a single `CardContent` or raw `bg-zinc-900` div.

#### Scenario: Overview stat Cards

- **WHEN** Dashboard Overview stats render (Total Rooms / Active Devices / Warning / Critical)
- **THEN** each renders as `<Card><CardHeader><CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Total Rooms</CardTitle></CardHeader><Separator className="mx-6 w-auto"/><CardContent><p className="text-2xl font-bold font-mono">12</p></CardContent></Card>` with `data-icon="inline-end"` on the icon

#### Scenario: RoomCard uses Header/Content/Footer

- **WHEN** `components/RoomCard.tsx` renders a room with temp available
- **THEN** it renders `<Card><CardHeader>` (name link + `StatusDot` in `Badge` via `gap-1.5`) `<CardContent>` (temp/humidity) `<CardFooter className="border-t">` (device count + sparkline + chevron) with `cn("size-*")` not `w-* h-*`

### Requirement: Skeleton for loading, not animate-pulse divs

Every loading placeholder for Cards/Tables/Headers SHALL use `Skeleton` imported from `@/components/ui/skeleton` with `className="h-4 w-*"` style props.

#### Scenario: Dashboard initial loading

- **WHEN** `routes/index.tsx` `isInitialLoading` is true (rooms pending)
- **THEN** the rooms grid shows 6 `RoomCardSkeleton` each rendering `Skeleton className="h-4 w-24"` etc., and the nodes Table `TableBody` fallback rows render `Skeleton className="h-4 w-full"`, not `<div className="animate-pulse">`

#### Scenario: Device header loading

- **WHEN** `routes/device.$deviceId.tsx` device is undefined
- **THEN** the sticky header shows `Skeleton className="h-6 w-40"` for title and `Skeleton className="h-3 w-32"` for subtitle, not a plain spinner alone

### Requirement: Separator anywhere there is a horizontal or vertical rule

The system SHALL use `Separator` for every rule, never `<hr>` or `<div className="border-t">`.

#### Scenario: Card rules replaced

- **WHEN** `RoomCard` renders its footer bar or `device.$deviceId` header renders its badge row and controls Card renders form sections
- **THEN** every horizontal rule is `<Separator />` and every vertical inline separator is `<Separator orientation="vertical" className="h-3" />`

### Requirement: Alert for callouts

Informational/success/error callouts SHALL use `Alert`/`AlertTitle`/`AlertDescription`, not custom `bg-red-500/10 border` divs.

#### Scenario: Command feedback uses Alert

- **WHEN** `routes/room.$roomId.tsx` `cmdError` or `cmdSuccess` is set after a `sendDeviceCommand` mutation
- **THEN** the feedback renders as `<Alert variant="destructive"><AlertTriangle data-icon="inline-start"/><AlertTitle>Failed</AlertTitle><AlertDescription>{cmdError}</AlertDescription></Alert>` and success as `<Alert><CheckCircle data-icon="inline-start"/><AlertTitle>Queued</AlertTitle><AlertDescription>…</AlertDescription></Alert>`

### Requirement: Badge for status and type

Every status label and device-type label SHALL use `Badge`, not hand `span className="bg-zinc-800 text-xs px-2.5"` .

#### Scenario: Nodes Table type and status

- **WHEN** `routes/index.tsx` renders a device row with `dev_type=TS` and `status=online`
- **THEN** the type cell renders `<Badge variant="secondary" className="font-mono text-xs">TS</Badge>` and status cell renders `<Badge variant="default" className="gap-1.5"><StatusDot tone="emerald" …/>Online</Badge>`; `isPending` (`!is_active`) maps to `variant="secondary"` amber, offline maps to `variant="outline"` zinc

### Requirement: Avatar always with AvatarFallback

Whenever `Avatar` is used, it SHALL include `AvatarFallback`.

#### Scenario: Nodes Table avatar fallback

- **WHEN** the nodes Table optionally renders an `Avatar` for device monogram in a future iteration or existing `RoomCard` context expects one
- **THEN** the markup is `<Avatar className="size-8"><AvatarFallback>{initials || dev_type[0]}</AvatarFallback></Avatar>`; grep ensures no bare `<Avatar>` without sibling `AvatarFallback`

### Requirement: Dialog/Sheet/Drawer always with Title

Every `Dialog`, `Sheet`, `Drawer` content SHALL contain `DialogTitle`/`SheetTitle`/`DrawerTitle` openable by assistive tech, even if visually hidden via `sr-only`.

#### Scenario: Room command dialog

- **WHEN** `routes/room.$roomId.tsx` opens the Command Control dialog (`selectedDeviceForCmd !== null`)
- **THEN** the DOM contains `<DialogTitle>Command Control: {name}</DialogTitle>` inside `DialogHeader` and `<DialogDescription className="font-mono text-xs">TS Node · queued via pending_commands</DialogDescription>`

#### Scenario: Device page no fixed inset div

- **WHEN** the device page command UI is inspected after the change
- **THEN** there is zero `class="fixed inset-0 bg-black/70"` modal pattern; all modals are `Dialog`/`Sheet`/`Drawer` via shadcn

### Requirement: Select with SelectGroup wrapping SelectItem

Every `SelectItem` SHALL be nested inside `SelectGroup` inside `SelectContent`.

#### Scenario: Device picker in schedules and room modals

- **WHEN** `routes/schedules.tsx` `Select` dev_id and `routes/room.$roomId.tsx` room picker render their `SelectContent`
- **THEN** markup is `<SelectContent><SelectGroup><SelectItem value="all">…</SelectItem>…</SelectGroup></SelectContent>`; bare `<SelectContent><SelectItem>` fails this requirement

### Requirement: TabsTrigger inside TabsList

Every `TabsTrigger` SHALL be inside `TabsList`, which is inside `Tabs`, with `TabsContent` panels.

#### Scenario: Map view tabs

- **WHEN** `routes/map.tsx` renders the Floor Plan / Topology switcher
- **THEN** it renders:
  ```tsx
  <Tabs value={activeView} onValueChange={…}>
    <TabsList><TabsTrigger value="floor-plan"><LayoutGrid data-icon="inline-start"/>Floor Plan</TabsTrigger><TabsTrigger value="topology"><Network data-icon="inline-start"/>Topology</TabsTrigger></TabsList>
    <TabsContent value="floor-plan">…Card floor-plan…</TabsContent>
    <TabsContent value="topology"><TopologyView/></TabsContent>
  </Tabs>
  ```
  and there is zero `class="flex border-b"` + `button border-b-2` tab pattern

### Requirement: ToggleGroup for 2-7 choices

Option sets of 2-7 mutually exclusive values SHALL use `ToggleGroup type="single"` + `ToggleGroupItem`, not a `Button` loop with manual active state.

#### Scenario: Room command toggles

- **WHEN** `routes/room.$roomId.tsx` renders Operating Mode and Genset Ignition pickers
- **THEN** each picker is:
  ```tsx
  <ToggleGroup type="single" value={commandPayload.mode||""} onValueChange={…} variant="outline" size="sm">
    <ToggleGroupItem value="auto">Auto</ToggleGroupItem><ToggleGroupItem value="manual">Manual</ToggleGroupItem>
  </ToggleGroup>
  ```
  and history `timeRange` toggle (`6h/24h/7d/30d`) is the same `ToggleGroup`, not hand `button` map

#### Scenario: Threshold controls use ToggleGroup or Select not buttons

- **WHEN** the history range selector in `HistoryChartHeader` renders
- **THEN** it uses `ToggleGroup type="single" value={timeRange}` where change calls `setTimeRange` via `HistoryChartProvider actions`, with variant `outline` and size `sm`

### Requirement: FieldGroup/Field for forms, InputGroup for adornments

Form sections SHALL use `FieldGroup`→`Field`→`FieldLabel`→(`InputGroup`→`InputGroupInput`+`InputGroupAddon`|`Select`/`ToggleGroup`)→`FieldDescription` and validation SHALL use `data-invalid` on `Field` + `aria-invalid` on the control. Buttons inside non-submit form flows are not used in place of `ToggleGroup`.

#### Scenario: Thresholds warning/critical inputs

- **WHEN** settings renders thresholds form fields
- **THEN** each field is:
  ```tsx
  import { FieldGroup, Field, FieldLabel, FieldDescription } from "@/components/ui/field"
  import { InputGroup, InputGroupInput, InputGroupAddon } from "@/components/ui/input-group"
  <FieldGroup>
    <Field data-invalid={!!warnError}>
      <FieldLabel htmlFor="warn">Warning Threshold</FieldLabel>
      <InputGroup><InputGroupInput id="warn" type="number" aria-invalid={!!warnError} /><InputGroupAddon align="inline-end">°C</InputGroupAddon></InputGroup>
      <FieldDescription>Trigger warning alert above this temperature</FieldDescription>
    </Field>
    <Separator/>
    <Field>…critical…</Field>
  </FieldGroup>
  ```
  and raw `div className="space-y-4"` form containers do not exist

#### Scenario: Room command form validation uses data-invalid

- **WHEN** a command payload field is invalid
- **THEN** the containing `Field` carries `data-invalid` and the `InputGroupInput`/`SelectTrigger` carries `aria-invalid="true"` and `FieldDescription` shows the message in `text-destructive`

### Requirement: Tooltip origin-aware and provider-wrapped

Every `Tooltip` SHALL be inside `TooltipProvider`, use `TooltipTrigger asChild`, and style with `transform-origin: var(--transform-origin)` and `data-starting-style`/`data-ending-style` transitions, not `center` origin.

#### Scenario: Coordinates and badges show Tooltip

- **WHEN** the device header coordinate `field` or floor-plan marker is hovered/focused
- **THEN** a `TooltipContent` appears with `side="top"` and CSS `transform-origin: var(--transform-origin)` and entrance `scale(0.95) opacity 0 → 1` over `125ms ease-out` via `[data-starting-style]` selector

### Requirement: Empty for zero states

Every zero state (no rooms, no devices, no history, no floor-plan image, no topology hubs) SHALL use `Empty` (`EmptyMedia`/`EmptyHeader`/`EmptyTitle`/`EmptyDescription`), not hand `colSpan` table row or `p text-center` div.

#### Scenario: Dashboard no devices

- **WHEN** `routes/index.tsx` `sortedDevices.length===0`
- **THEN** the Card wrapping the Table renders `<Empty><EmptyMedia><HelpCircle/></EmptyMedia><EmptyHeader><EmptyTitle>No devices found</EmptyTitle><EmptyDescription>Pair a device in Settings</EmptyDescription></EmptyHeader></Empty>` instead of `<tr><td colSpan=7>No devices</td></tr>`

#### Scenario: Device history empty

- **WHEN** `HistoryChart` receives `points.length===0`
- **THEN** it renders `<Empty><EmptyTitle>Collecting telemetry…</EmptyTitle><EmptyDescription>No history within {timeRange}</EmptyDescription></Empty>` with no `border-dashed` plain div

### Requirement: Node Information folding — 6-card grid deleted, header badges inline

The 6-card `Node Information` grid in `routes/device.$deviceId.tsx` SHALL be deleted and the six facts folded into the sticky header `Badge` row as specified.

#### Scenario: Six-card grid absent

- **WHEN** `routes/device.$deviceId.tsx` is inspected post-change
- **THEN** there is no `h3 Node Information` and no `grid grid-cols-2 sm:grid-cols-3 gap-4` containing cards for Gateway Hub / Room Assignment / Registered Date / Map Coordinate / Warning Level / Critical Level; instead the header contains a `div className="flex flex-wrap items-center gap-2"` with badges for `MAC/font-mono`, `type`, `room`, `coordinate Tooltip`, `created date muted`, with `Separator orientation="vertical"` between each

#### Scenario: Thresholds relocated

- **WHEN** warning and critical threshold values exist on the device
- **THEN** they do not appear as isolated `bg-zinc-950 p-3` cards; they appear as (a) textual legend items next to the chart heading and (b) `FieldDescription` values inside `DeviceControls` fields

### Requirement: Dashboard nodes Table sortable headers via Button (a11y)

Sortable column headers SHALL use `Button variant="ghost" size="sm"` inside `TableHead` with `aria-sort` and swap `ArrowUp`/`ArrowDown`/`ArrowUpDown` correctly.

#### Scenario: Sorting feedback

- **WHEN** `routes/index.tsx` renders with `search sortBy=name sortOrder=asc`
- **THEN** the Name `TableHead` carries `aria-sort="ascending"` and the Button shows `ArrowUp` with `data-icon="inline-end"` in `text-primary`, while inactive headers show `ArrowUpDown` at `opacity-40`

#### Scenario: Sorting action

- **WHEN** the user activates (click or keyboard Enter) the Type header `Button`
- **THEN** navigation calls `navigate({ to: ".", search: (prev)=>({ ...prev, sortBy: "type", sortOrder: active ? (prev.sortOrder==="asc"?"desc":"asc"):"asc" }) })` with no full page reload and `sort` reflects in URL

### Requirement: Spacing and sizing shadcn rules

Layout spacing SHALL use `gap-*` with `flex`/`grid`, not `space-y-*`/`space-x-*`; equal w/h SHALL use `size-*` not `w-* h-*`; content truncation SHALL use `truncate`.

#### Scenario: Spacing audit

- **WHEN** a grep `rg "space-y-|space-x-" dashboard/src` is run after the change
- **THEN** the result count is 0 (except inside ui vendor files allowed to keep it if untouched); every vertical stack is `flex flex-col gap-4` or `grid gap-*`

#### Scenario: Sizing audit

- **WHEN** `Avatar` or square icon container is inspected
- **THEN** it uses `className="size-8"` (or `size-10`) never `className="w-8 h-8"`; grep `w-8 h-8` on dashboard components returns 0 for custom code

### Requirement: Icon composition rules

Icons inside `Button` SHALL use `data-icon="inline-start"` or `"inline-end"` and SHALL NOT carry `size-4`/`h-4 w-4` within the button; the button CSS handles sizing. Icons outside buttons pass size via `className="size-4"` (preferred over `h-4 w-4` where equal is implied but both are acceptable if `size-*` is used elsewhere).

#### Scenario: Action buttons

- **WHEN** `routes/index.tsx`, `routes/room.$roomId.tsx`, or `routes/schedules.tsx` render a `Button` with a leading icon (`Plus`, `Layers`, `Loader2`, `ArrowUp`, `Play`, `Pencil`)
- **THEN** the icon element is `<Plus data-icon="inline-start" />` with no `className="h-4 w-4"` on that icon; if the icon is outside a `Button` (e.g., in `CardTitle` ornament) it uses `className="size-4 text-muted-foreground"`

### Requirement: Motion (emil) — scale press, tooltip scale+origin, durations, hover guard

Motion SHALL conform to emil tokens: press `scale(0.97)` `120ms ease-out` (`cubic-bezier(0.23,1,0.32,1)`), tooltip entry `125ms scale(0.95) opacity 0→1` with `transform-origin: var(--transform-origin)`, hover-gated by `@media (hover: hover) and (pointer: fine)`, and respecting `prefers-reduced-motion: reduce`.

#### Scenario: Button press feedback

- **WHEN** any `Button` (or pressable `ToggleGroupItem`/`TabsTrigger`) is pressed via mouse/touch
- **THEN** `:active` applies `transform: scale(0.97)` within `transition: transform 120ms var(--ease-out)` and at rest it is `scale(1)`; `transition: all` is absent

#### Scenario: Tooltip not scaled from center

- **WHEN** a floor-plan marker `TooltipContent` appears anchored to a trigger at top-center
- **THEN** its CSS specifies `transform-origin: var(--transform-origin)` (not `center`) and content starts at `scale(0.95) opacity 0` when `data-starting-style` and animates to `scale(1) opacity 1`; `data-instant` tooltips use `transition-duration: 0ms`

#### Scenario: Reduced motion

- **WHEN** the user has `prefers-reduced-motion: reduce`
- **THEN** `value-flash`, `card-stagger` animation, and `tooltip` transitions are disabled (`transition: none; transform: none; animation: none`); opacity-only fade remains where it aids comprehension (opacity transition still 150ms `ease-out`)

### Requirement: Schedules route polish only (no functional regression)

`schedules` route SHALL retain its CRUD + RBAC + cron validation behavior and only receive token/type/motion deltas; every requirement above that touches it still applies where the spec mentions it (Table/Card/Dialog/Select/Badge/Switch/Skeleton/Alert/Empty composition), but no new requirement mandates changing schedule semantics or payload shape.

#### Scenario: Schedule table retains semantics

- **WHEN** `routes/schedules.tsx` is audited after the change
- **THEN** it still lists schedules via `queryKeys.schedules` with filter `dev_id`/`enabled`, shows `cron_expr` + `human` + `payload Badge` + `enabled Switch`, and `Dialog` creates/edits with `SelectGroup`→`SelectItem` + `DialogFooter`, while colors now come from `var(--chart-*)` semantic tokens if heat or tone is rendered

## MODIFIED Requirements

None — this change does not alter existing spec MODIFIED deltas; `ats-flexible-schedule-2026-08-29` specs remain authoritative for scheduler domain. This `dashboard-ui` capability coexists; if any overlap, this spec controls dashboard presentation.

