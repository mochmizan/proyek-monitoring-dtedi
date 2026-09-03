---
type: entity
governed_by: AGENTS.md
links: [wiki/concept-frontend-navigation.md, wiki/concept-state-management.md, wiki/concept-frontend-resilience.md, wiki/concept-downsampling-v2.md, wiki/concept-telemetry-pipeline.md, wiki/concept-time-conventions.md, wiki/concept-command-path.md, wiki/workstream-flexible-scheduling.md, wiki/workstream-shadcn-revert.md]
sources: [dashboard/src/App.tsx, dashboard/src/routes/__root.tsx, dashboard/src/lib/queryClient.ts, dashboard/src/lib/queryKeys.ts, dashboard/src/lib/constants.ts, dashboard/src/lib/api.ts, dashboard/src/types/api.ts, dashboard/src/hooks/useCommandLifecycle.ts, dashboard/src/hooks/useDeviceHistory.ts, dashboard/src/components/device/HistoryChart.tsx, dashboard/src/components/device/Controls.tsx, dashboard/src/components/device/chart/MultiPanelChartContainer.tsx, dashboard/src/components/ui/pagination.tsx, dashboard/src/routes/, dashboard/package.json, dashboard/AGENTS.md, server/schemasv5.py, server/app/routers/schedules.py, server/app/routers/devices.py, commit:b290e3c, commit:35e0582]
updated: 2026-09-03
---

# Dashboard SPA (dashboard/)

The smsb dashboard is a React 19 + TypeScript SPA (Vite 8) communicating with HubGate V5 over same-origin `/api` endpoints — routed via Vite reverse proxy in development and Nginx port 443 in production.

---

## 1. System Overview & Technology Stack

| Domain | Implementation | Notes |
| :--- | :--- | :--- |
| **Framework & Runtime** | React 19.2.7, React DOM 19.2.7 | Client-side Single Page Application |
| **Language & Tooling** | TypeScript ~6.0.2, Vite 8.1.3, oxlint 1.71 | `erasableSyntaxOnly: true`, `verbatimModuleSyntax: true` |
| **Routing** | TanStack Router 1.170.17 | File-based routes (`src/routes/`), auto-generated `routeTree.gen.ts` |
| **Server State** | TanStack Query 5.101.2 | Hierarchical query keys, polling lifecycle, cache-first defaults |
| **Client UI State** | URL Search Params (Zod 4.4.3), Zustand 5.0.14 | Sort/filter/pagination in URL; `appStore.ts` isolated |
| **UI Primitives** | shadcn/ui (`new-york` style), Radix UI 1.6.7 | Dark theme (`#09090b`), Tailwind CSS 4.3.2 (`@tailwindcss/vite`) |
| **Telemetry Charts** | Bespoke Multi-Panel SVG Engine (`src/components/device/chart/*`) | Recharts evaluated & reverted (commit `35e0582`) |
| **Topology & Map** | `@xyflow/react` 12.11.3 | Lazy-loaded code split (~182 kB) in `TopologyView.tsx` |
| **Timezone** | Indonesian Western Time (`Asia/Jakarta` / `WIB`) | `id-ID` / `en-GB` locale, wall-clock WIB suffix, UTC `Z` defensive parsing |

---

## 2. Component Hierarchy

```
<App> (src/App.tsx)
└── <QueryClientProvider client={queryClient}>
    └── <RouterProvider router={router}>
        └── RootRoute (src/routes/__root.tsx)
            ├── RootError [Fallback error view on unhandled route crash]
            └── RootLayout
                ├── Viewport-Top Progress Bar ({isNavigating})
                ├── Aside (Sidebar Navigation w-64)
                │   ├── Logo & Brand Header (Cpu icon + "Proyek Monitoring")
                │   ├── Nav Links (<Link to="..." preload="intent">)
                │   │   ├── Dashboard (/)
                │   │   ├── Floor Map (/map)
                │   │   ├── Alert History (/alerts) [Active Badge Counter]
                │   │   ├── Hubs (/hubs)
                │   │   ├── Schedules (/schedules) [Admin/Operator Guarded]
                │   │   └── Settings (/settings) [Admin Guarded]
                │   └── User Profile Footer (<LogOut> button)
                ├── Header (Sticky h-16)
                │   ├── Route Breadcrumb / Title
                │   ├── Static Live Gateway Indicator ("Live Gateway Connected")
                │   └── Alert Bell (<Link to="/alerts"> with badge counter)
                └── Main Content (<Outlet />)
                    ├── Route: / (src/routes/index.tsx)
                    │   ├── Overview Stats Bar (Rooms, Devices, Warning, Critical)
                    │   ├── Rooms Section
                    │   │   ├── RoomCard Grid (Pure presentation)
                    │   │   │   ├── Sparkline (Custom SVG 6h room temp/humid)
                    │   │   │   └── ATS Power State & Battery Badges
                    │   │   └── Expand/Collapse Control (> 8 rooms)
                    │   └── Connected Nodes Table
                    │       ├── Sortable Headers (ArrowUp / ArrowDown)
                    │       └── Clickable Rows -> /device/$deviceId
                    ├── Route: /alerts (src/routes/alerts.tsx)
                    │   ├── Filter Bar (MultiSelect Rooms, Devices, Severity, Status, Range)
                    │   ├── Audit Log Table (Severity Badges, Timestamp WIB, Reading/Threshold)
                    │   └── Pagination (<Pagination> 15/page, resetScroll: false)
                    ├── Route: /device/$deviceId (src/routes/device.$deviceId.tsx)
                    │   ├── Header (Device metadata, status badge, copy MAC button)
                    │   ├── HistoryChart (src/components/device/HistoryChart.tsx)
                    │   │   └── MultiPanelChartContainer (src/components/device/chart/)
                    │   │       ├── TelemetryPanel (PLN Grid AC)
                    │   │       ├── TelemetryPanel (Genset AC)
                    │   │       ├── TelemetryPanel (Starter Battery DC + 11.8V/11.2V Guides)
                    │   │       ├── PanelOutages (Diagonal hatch gap fills)
                    │   │       ├── PanelCrosshair & Floating Synchronized Tooltip
                    │   │       └── Auto-Scale vs Preset Scale Toggles
                    │   ├── DeviceControls (src/components/device/Controls.tsx)
                    │   │   ├── Threshold Form (Protected by isEditingRef & isDirty)
                    │   │   ├── ATS Hardware Dispatch (Auto/Manual, Start/Stop Genset)
                    │   │   └── CommandStatusBadge (Elapsed counter, FSM progress)
                    │   └── Device Alert History Table (<Pagination> 10/page)
                    ├── Route: /room/$roomId (src/routes/room.$roomId.tsx)
                    │   ├── Room Telemetry Cards (TS, ATS, AC nodes)
                    │   ├── Command Dispatch Dialog (ATS generator controls)
                    │   └── Room Alerts Table
                    ├── Route: /map (src/routes/map.tsx)
                    │   ├── View Switcher (Floor Plan vs Topology)
                    │   ├── Floor Plan View (Spatial markers, hover tooltips)
                    │   └── Topology View (React.lazy -> @xyflow/react node graph)
                    ├── Route: /hubs (src/routes/hubs.tsx)
                    │   └── HubCard Grid (Approval/Revoke actions, connected device lists)
                    ├── Route: /schedules (src/routes/schedules.tsx)
                    │   ├── Schedule List & Status Toggles (Flexible ATS cron)
                    │   └── Schedule Modal Dialog (Preset selector, cron validator, JSON editor)
                    ├── Route: /settings (src/routes/settings.tsx)
                    │   ├── RoomsTab (Create/Delete rooms, floor plan image upload)
                    │   ├── DevicesTab (Unpaired nodes pairing, coordinate assignment)
                    │   └── HubsTab (Global device threshold presets)
                    └── Route: /login (src/routes/login.tsx)
                        └── Login Card (Username/password, role quick-login buttons)
```

---

## 3. Data & State Flows

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Dashboard State & Data Flow                        │
└─────────────────────────────────────────────────────────────────────────────┘

    [ Browser Client ]                                    [ HubGate V5 ]
            │                                                    │
            ├──── 1. Auth Gate (Root beforeLoad) ───────────────>│ GET /api/auth/me
            │<─── Cached User Object (staleTime 60s) ────────────┤
            │                                                    │
            ├──── 2. Live Polling (POLL_MS=3000) ───────────────>│ GET /api/rooms
            │                                                   │ GET /api/devices
            │                                                   │ GET /api/alerts
            │<─── placeholderData: keepPreviousData ─────────────┤
            │                                                    │
            ├──── 3. Telemetry History (15s polling) ───────────>│ GET /api/devices/{id}/history
            │<─── Downsampled Buckets + Min/Max Envelopes ───────┤
            │                                                    │
            ├──── 4. Hardware Command Dispatch ─────────────────>│ POST /api/devices/{id}/command
            │<─── { status: "queued", command_id } ──────────────┤
            │                                                    │
            │     [ Poll FSM: useCommandLifecycle 1.5s ]         │
            ├──── 5. Check Command Status ──────────────────────>│ GET /api/commands/{id}
            │<─── { status: "delivered", delivered_at } ─────────┤
            │                                                    │
            │     [ Invalidation Cascade ]                       │
            ├──── Invalidate: devices.all, rooms.all, alerts ───>│
```

1. **Authentication Session Flow**: Root route `beforeLoad` validates session via `ensureQueryData(queryKeys.auth.me())`. If null, redirects to `/login?redirect=...`.
2. **Server State Polling Flow**: Live views execute 3s polling (`POLL_MS`) for active telemetry, and 5s polling (`POLL_ALERTS_MS`) for root navigation badges. Cache-first policies (`keepPreviousData`, `staleTime: 10s`, `gcTime: 5m`) eliminate UI layout flashing.
3. **Multi-Panel Telemetry Rendering Flow**: `HistoryChart` passes downsampled telemetry points to `MultiPanelChartContainer`. X-axis timestamps are synchronized across three stacked panels. Dynamic 12% padded Y-axes auto-scale based on visible values, toggled to fixed electrical presets via panel headers.
4. **Command Dispatch Flow**: Commands dispatch through `useCommandLifecycle`, transitioning from `queuing` to `queued`, polling `GET /api/commands/{id}` every 1.5s, with a 12s client timeout and cache invalidation cascade upon delivery confirmation.
5. **Form Editing Flow**: Device threshold inputs in `Controls.tsx` track focus (`isEditingRef`) and input dirtiness (`isDirty`), preventing background telemetry refetches from overwriting uncommitted operator edits.

---

## 4. Multi-Panel ATS Telemetry: Custom SVG Engine vs Recharts

In late August 2026, an experimental migration to shadcn Recharts components was attempted (`openspec/changes/dashboard-full-shadcn-redesign-2026-08-29/`). As recorded in [workstream-shadcn-revert.md](workstream-shadcn-revert.md) (commit `35e0582`), Recharts was completely reverted due to:
- Excessive bundle size inflation (~120 kB increase).
- Inability to cleanly handle synchronized crosshairs across stacked, multi-panel layouts without heavy wrapper overhead.
- Difficulty styling custom telemetry outage hatch patterns for power dropouts.

**Current Custom SVG Architecture** (`src/components/device/chart/*`):
- **`MultiPanelChartContainer`**: Orchestrates global time coordinate projections (`timeToXCoord`), common time range calculations (`minTimeMs`, `maxTimeMs`), and outage region detection (`getOutages`).
- **`TelemetryPanel`**: Renders an individual SVG panel (PLN 180–240V, Genset 0–240V, Battery 10–14.5V, Temp 20–35°C, Humid 30–80%).
- **`computeYScale`**: Calculates independent linear scales with 12% padding above and below data bounds while enforcing domain safety floors.
- **Synchronized Cursor & Crosshair**: Hovering over any panel displays a vertical crosshair line and a single lifted tooltip across all panels at that precise epoch.

---

## 5. Production-Readiness Gap Analysis

### 5.1 Query Cache & Polling Management
- **Background Tab Battery / Connection Drain**: `index.tsx`, `room.$roomId.tsx`, `device.$deviceId.tsx`, and `useDeviceHistory.ts` configure `refetchIntervalInBackground: true`. Unattended tabs continuously poll HubGate every 3 to 15 seconds. Inactive tabs must pause polling and refresh on window focus (`refetchOnWindowFocus: true`).
- **Query Key Cardinality Bloat**: In `alerts.tsx`, `start_time` is computed from `Date.now()` rounded to the minute. Every 60 seconds, a new query key is registered. While old queries are garbage collected after `gcTime: 5m`, high filter permutation combinations consume heap memory.
- **Unmount Observer Cleanup**: While TanStack Query cleans up observers on unmount, views sharing global queries keep network sockets busy during rapid tab toggling.

### 5.2 Error Handling & Resilience
- **Unmounted ErrorBoundary**: `src/components/ErrorBoundary.tsx` is implemented but unused. Rendering errors in complex SVG charts or tables bubble straight to `RootError`, blanking the entire page and requiring a hard refresh.
- **Hard 401 Window Redirect Storms**: `src/lib/api.ts` line 42 triggers `window.location.href = /login` on any 401 response. When a session expires, multiple concurrent polling requests execute simultaneous hard reloads instead of a clean, single-flight client-side router transition.
- **Static Gateway Connection Badge**: The green pulsing badge in the top header declares "Live Gateway Connected" statically without checking network connectivity (`navigator.onLine`), server reachability, or query error states.
- **Native Browser `alert()` in Workflows**: `src/routes/schedules.tsx` uses blocking native `alert()` dialogs for error reporting and execution confirmations, stalling the JavaScript main thread.

### 5.3 State Architecture & Type Contract Synchronization
- **Orphaned Zustand Store**: `src/store/appStore.ts` (`sidebarOpen`, `selectedRoomId`) is completely unconsumed across the application (0 imports).
- **Unsynchronized Settings Navigation**: `src/routes/settings.tsx` initializes active tab state from search parameters on mount, but tab clicks update local `useState` without updating the URL, breaking deep linking and browser back/forward buttons.
- **Pydantic Model Discrepancies**:
  - `ScheduleResponse`: Backend returns `next_run: Optional[datetime]` and `next_runs: list[datetime]`, both of which are omitted from frontend `ScheduleResponse` in `src/types/api.ts`.
  - `DeviceResponse.status`: Backend Pydantic schema default is free string `status: str = "offline"`, whereas frontend type defines `'online' | 'offline' | 'pending'`. The backend router dynamically computes these exact three values, but the schema definition does not enforce the union.

### 5.4 Performance, Bundle Size & Accessibility
- **Bundle Weight**: Main application chunk `index-*.js` is **370.31 kB** (113.34 kB gzipped). `TopologyView-*.js` is **181.92 kB** (59.01 kB gzipped) lazy-loaded via `@xyflow/react`. `schedules-*.js` is **121.05 kB** (38.77 kB gzipped) due to date and cron utilities.
- **Tailwind 4 Sourcemap Warning**: Vite build issues `@tailwindcss/vite:generate:build [SOURCEMAP_BROKEN]`.
- **Accessibility (a11y) Gaps**:
  - Connected nodes table rows (`index.tsx`) use clickable `<tr onClick=...>` without keyboard focus (`tabIndex={0}`), `role="link"` or `role="button"`, or Enter/Space event handlers.
  - Alerts multi-select dropdown lacks ARIA combobox/listbox attributes, keyboard arrow navigation, and escape-to-close handling.

### 5.5 Test Coverage Disparity
- **Vitest Unit Coverage**: 89 tests across 10 test suites, with solid math and component coverage for `chartMath`, `Controls`, `HistoryChart`, `RoomCard`, and `useCommandLifecycle`.
  - **Zero coverage** for router routes (`__root`, `index`, `alerts`, `hubs`, `schedules`, `settings`, `map`, `login`), API client error handlers, and settings tabs.
- **Playwright E2E Coverage**: Contains only **1 single test** (`login.spec.ts: login page loads`). Zero E2E coverage for operational flows: dashboard live updates, alert filtering, floor map interactions, device control dispatches, or schedule creation.
