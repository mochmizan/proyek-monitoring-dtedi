---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-dashboard-spa.md, wiki/concept-frontend-navigation.md, wiki/concept-frontend-resilience.md, wiki/concept-command-path.md, wiki/concept-telemetry-pipeline.md, wiki/workstream-flexible-scheduling.md]
sources: [dashboard/src/lib/queryClient.ts, dashboard/src/lib/queryKeys.ts, dashboard/src/lib/constants.ts, dashboard/src/lib/dateUtils.ts, dashboard/src/lib/api.ts, dashboard/src/lib/sidebarStore.ts, dashboard/src/types/api.ts, dashboard/src/hooks/useCommandLifecycle.ts, dashboard/src/hooks/useDeviceHistory.ts, dashboard/src/components/device/Controls.tsx, dashboard/src/routes/schedules.tsx, dashboard/src/routes/index.tsx, dashboard/src/routes/alerts.tsx, dashboard/src/routes/settings.tsx, dashboard/vite.config.ts, dashboard/src/App.tsx, server/schemasv5.py, server/app/routers/schedules.py, server/app/routers/devices.py]
updated: 2026-09-26
---

# Frontend State Management Architecture

The smsb dashboard SPA (`dashboard/`) structures client state across three operational layers: server state managed by TanStack Query v5, navigational and filter state encoded into URL search parameters via TanStack Router with Zod validation, and local ephemeral UI state in React components alongside persistent layout preferences in Zustand (`sidebarStore`).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            Frontend State Topology                           │
├───────────────────────────────┬───────────────────────────────┬──────────────┤
│      Server Cache State       │      Navigational State       │ Local UI     │
│       (TanStack Query)        │      (URL Search Params)      │ (React/Store)│
├───────────────────────────────┼───────────────────────────────┼──────────────┤
│ • Rooms & Sparklines          │ • Table sorting (sortBy, asc) │ • Input focus│
│ • Devices & Pairing           │ • Severity & status filters   │ • Dirty flag │
│ • Multi-panel Telemetry       │ • Active time range (6h/24h)  │ • Dialog open│
│ • Alerts & Thresholds         │ • Pagination (page 1..N)      │ • Command FSM│
│ • Hubs & Approvals            │ • Settings active tab         │ • Persistent │
│ • Flexible ATS Schedules      │ • Map view mode (plan/topo)   │  sidebarStore│
└───────────────────────────────┴───────────────────────────────┴──────────────┘
```

---

## 1. Server State Topology (TanStack Query v5)

Server state encompasses all data ingested from the HubGate V5 API (`/api/*`). The query pipeline is standardized around a centralized `QueryClient` (`src/lib/queryClient.ts`) and a hierarchical query key factory (`src/lib/queryKeys.ts`).

### 1.1 Global Cache Defaults

Global query behavior is established in `src/lib/queryClient.ts`:

- **`staleTime: STALE_MS` (10,000ms)**: Telemetry and metadata payloads remain fresh for 10 seconds. In-flight route navigations within this window reuse cached payloads without triggering network fetches.
- **`gcTime: 5 * 60 * 1000` (5 minutes)**: Unused query caches are retained in browser heap memory for 5 minutes before garbage collection runs.
- **`placeholderData: keepPreviousData`**: Retains previous data across query key transitions, preventing UI layout collapses, blank loading flashes, or scroll resets when query parameters change (e.g., table pagination or filter adjustments).
- **`refetchOnWindowFocus: true`**: Resynchronizes telemetry when an operator switches back to the dashboard tab.
- **`retry` predicate**: Retries once on generic network errors (`failureCount < 1`), but immediately aborts without retrying on HTTP 401 unauthenticated errors (`error instanceof ApiError && error.status === 401`).

### 1.2 Query Key Factory Hierarchy

Query keys are defined as typed tuples in `src/lib/queryKeys.ts`:

```typescript
export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    me: () => [...queryKeys.auth.all, 'me'] as const,
  },
  devices: {
    all: ['devices'] as const,
    list: (status?: string) => [...queryKeys.devices.all, 'list', { status }] as const,
    detail: (id: string) => [...queryKeys.devices.all, 'detail', id] as const,
    history: (id: string, range?: string) => [...queryKeys.devices.all, 'history', id, { range }] as const,
    pending: () => [...queryKeys.devices.all, 'pending'] as const,
    active: () => [...queryKeys.devices.all, 'active'] as const,
  },
  rooms: {
    all: ['rooms'] as const,
    list: () => [...queryKeys.rooms.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.rooms.all, 'detail', id] as const,
    map: (id: string) => [...queryKeys.rooms.all, 'map', id] as const,
    sparklines: (range = '6h', maxPoints = 24) => ['rooms', 'sparklines', range, maxPoints] as const,
  },
  alerts: {
    all: ['alerts'] as const,
    list: (filters?: Record<string, unknown>) => [...queryKeys.alerts.all, 'list', filters] as const,
  },
  hubs: {
    all: ['hubs'] as const,
    list: () => [...queryKeys.hubs.all, 'list'] as const,
  },
  schedules: {
    all: ['schedules'] as const,
    list: (filters?: Record<string, unknown>) => [...queryKeys.schedules.all, 'list', filters] as const,
    detail: (id: string) => [...queryKeys.schedules.all, 'detail', id] as const,
    preview: (cron: string, tz?: string) => [...queryKeys.schedules.all, 'preview', cron, tz] as const,
  },
  commands: {
    all: ['commands'] as const,
    detail: (id: string) => [...queryKeys.commands.all, 'detail', id] as const,
  },
};
```

This tiered naming enables precise scoped invalidation (e.g., `queryClient.invalidateQueries({ queryKey: queryKeys.devices.detail(devId) })`) alongside sweeping domain invalidations (e.g., `queryClient.invalidateQueries({ queryKey: queryKeys.devices.all })`).

---

## 2. Polling Lifecycle Contracts & 4-Tier Architecture

Telemetry monitoring requires continuous real-time data sync without WebSocket infrastructure. The SPA executes periodic HTTP polling governed by a **Strict 4-Tier Polling Architecture** with anti-stampede jitter ($\pm 15\%$ via `src/lib/jitter.ts`) and enforces the **Cache Harmony Invariant** (`staleTime >= refetchInterval`):

| Tier / Surface | Target Query Keys | Polling Cadence (`refetchInterval`) | Cache Stale Time (`staleTime`) | Background Tab (`refetchIntervalInBackground`) | Synchronization Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Ephemeral Commands** | `GET /api/commands/{id}` (via `useCommandLifecycle`) | `1,500ms` (Fixed, no jitter) | `0ms` | Paused on `visibilitychange: hidden` | 12s downlink ceiling; auto-aborts on `delivered`, `ACK`, `failed`, `rejected`, `timeout` |
| **Tier 2: Alerts & Critical Status** | `alerts.list(...)`, `rooms.list()` (Overview `/`), `rooms.map(...)` | `6,000ms` ($\pm 15\%$ jitter) | `6,000ms` | `false` (globally inherited) | Synchronized with ESP8266 5s publish interval + 1s network transit |
| **Tier 3: Operational Presence** | `devices.list('all')`, `hubs.list()`, `devices.active()`, `devices.history` (6h/24h) | `15,000ms` ($\pm 15\%$ jitter) | `15,000ms` | `false` (globally inherited) | Synchronized with APScheduler 15s presence sweeper (`PRESENCE_INTERVAL_SECONDS = 15`) |
| **Tier 4: Analytical Trends** | `rooms.sparklines('6h', 24)` | `60,000ms` ($\pm 15\%$ jitter) | `60,000ms` | `false` (globally inherited) | 6-hour CTE downsampled envelopes; cuts 95% of heavy aggregation queries |
| **Static Reference Metadata** | `rooms.list()` (in `/room/$id`, `/device/$id`, `DevicesTab`), `devices.detail(id)` | **Disabled (`false`)** | `300,000ms` (5 minutes) | N/A | Static facility configuration; refetches solely on window focus or mutation invalidation |

### 2.1 Background Tab Polling Suspension Contract (`refetchIntervalInBackground: false`)

To prevent battery drain, client network saturation, and backend connection starvation, all live queries across the SPA enforce an active contract of `refetchIntervalInBackground: false`:
- Unified across `index.tsx`, `room.$roomId.tsx`, `device.$deviceId.tsx`, `useDeviceHistory.ts`, `alerts.tsx`, `hubs.tsx`, and `__root.tsx`.
- Whenever an operator minimizes the browser or switches to another tab, all periodic background network requests are halted immediately.
- Upon returning to the tab, TanStack Query's `refetchOnWindowFocus: true` automatically triggers a fresh synchronization fetch, ensuring zero staleness with zero idle resource waste.

### 2.2 Query Key Stability & Cardinality Protection Contract

In earlier iterations, dynamic minute-bucketed ISO timestamps were embedded into query keys (e.g. `start_time: startTimeIso`), generating a new cache key every 60 seconds and causing memory bloat.

In the current active contract:
- Dynamic time calculation is decoupled from the query key.
- Query keys use a static `timeRange` descriptor (`'6h' | '24h' | '7d' | '30d'`), ensuring that the query key remains stable:
  ```typescript
  queryKeys.alerts.list({ rooms, devices, severity, status, timeRange, page })
  ```
- Precise UTC boundary resolution (`startTimeIso = computeStartTimeFromRange(timeRange)`) is deferred strictly to the execution of `queryFn` via `dateUtils.ts`.
- Cache entry cardinality is strictly bounded by active user filter combinations, completely eliminating rolling-minute cache fragmentation.

### 2.3 Observer Unmount Cleanup

When a user navigates between routes, TanStack Query automatically cleans up query observer timers once a component unmounts. However, shared queries like `rooms.list()` that are mounted across multiple routes (e.g. `/` and `/room/$roomId`) retain their active polling timers seamlessly during transitions without teardown and reconstruction cycles.

---

## 3. Client UI State & The Zustand Layer

Client UI state is partitioned between URL search parameters, local React component state, and an isolated Zustand store.

### 3.1 URL Search Parameters as Navigational Source of Truth

Per `dashboard/AGENTS.md`, table sorting, filters, time ranges, and pagination reside in URL search parameters validated by Zod schemas:
- **Alerts Table** (`alertsSearchSchema`): `rooms: string[]`, `devices: string[]`, `severity: enum`, `status: enum`, `timeRange: enum`, `page: number`. Navigation uses `resetScroll: false` to preserve viewport position across filter toggles.
- **Dashboard Table** (`dashboardSearchSchema`): `sortBy: enum(['name', 'type', 'room', 'devId', 'status', 'created'])`, `sortOrder: enum(['asc', 'desc'])`.
- **Device Detail** (`deviceSearchSchema`): `range: enum(['6h', '24h', '7d', '30d'])`.
- **Floor Map** (`mapSearchSchema`): `view: enum(['floor-plan', 'topology'])`.
- **Settings Tabs** (`settingsSearchSchema`): `tab: enum(['rooms', 'devices', 'thresholds'])`.

### 3.2 Settings Tab Navigation Desynchronization

In `src/routes/settings.tsx`, the route defines `settingsSearchSchema` to parse `?tab=rooms|devices|thresholds`. However, the page implementation handles tab switching exclusively through local React state:
```typescript
const search = Route.useSearch() as { tab?: 'rooms' | 'devices' | 'thresholds' };
const [activeTab, setActiveTab] = useState<'rooms' | 'devices' | 'thresholds'>(search.tab ?? 'rooms');

// Tab click handler:
onClick={() => setActiveTab('devices')}
```
Clicking tabs alters local state without invoking `router.navigate({ search: { tab: 'devices' } })`. As a result:
- The browser URL remains unchanged.
- Browser back/forward navigation between tabs fails.
- Hard page refreshing reverts the view back to the initial URL query or `'rooms'`.

### 3.3 Persistent UI Layout State (`src/lib/sidebarStore.ts`)

UI layout preferences are managed by a centralized Zustand store configured with persistence middleware:

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface SidebarState {
  isCollapsed: boolean
  isMobileOpen: boolean
  toggleCollapsed: () => void
  setCollapsed: (collapsed: boolean) => void
  toggleMobile: () => void
  setMobileOpen: (open: boolean) => void
  closeMobile: () => void
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      isCollapsed: false,
      isMobileOpen: false,
      toggleCollapsed: () => set((s) => ({ isCollapsed: !s.isCollapsed })),
      setCollapsed: (isCollapsed) => set({ isCollapsed }),
      toggleMobile: () => set((s) => ({ isMobileOpen: !s.isMobileOpen })),
      setMobileOpen: (isMobileOpen) => set({ isMobileOpen }),
      closeMobile: () => set({ isMobileOpen: false }),
    }),
    {
      name: 'smsb-sidebar-pref',
      partialize: (state) => ({ isCollapsed: state.isCollapsed }),
    }
  )
)
```

**Implementation Architecture & State Partitioning**:
- **Persistence Boundary**: The `partialize` filter ensures that only `isCollapsed` is persisted to `localStorage` under key `'smsb-sidebar-pref'`, preserving the user's desktop sidebar dimension across page reloads and browser sessions.
- **Ephemeral State**: Mobile drawer open state (`isMobileOpen`) is intentionally excluded from persistence, guaranteeing the drawer initializes closed on fresh loads.
- **Consumers & Integrations**:
  - `AppSidebar.tsx`: Reads `isCollapsed` to dynamically toggle between `w-[260px]` and `w-[68px]`, and binds `isMobileOpen` to Radix UI `DialogPrimitive`.
  - `SidebarNav.tsx`: Switches navigation item rendering to compact glyph-only mode with Radix UI tooltips when collapsed.
  - `SidebarTrigger.tsx`: Provides the header collapse toggle button.
  - `useSidebarKeyboard.ts`: Global keyboard hook listening for `Cmd+B` / `Ctrl+B` shortcut, with automatic suppression when focused within inputs or textareas.
- **Test Verification**: Unit verified with full coverage in `dashboard/src/lib/__tests__/sidebarStore.test.ts` (state toggling, direct setters, localStorage persistence roundtrips). The previously orphaned `appStore.ts` has been completely deleted from the codebase.

---

## 4. Cache Invalidation & Form Synchronization

### 4.1 Mutation Invalidation Cascades

When write operations occur, mutations execute targeted or cascading cache invalidations:

- **Threshold Updates** (`updateThresholds`): Invalidates `queryKeys.devices.all` and `queryKeys.alerts.all`.
- **Hub Approvals & Revocations** (`approveHub`, `revokeHub`): Invalidates `queryKeys.hubs.all`.
- **Room Modifications** (`createRoom`, `updateRoom`, `deleteRoom`): Invalidates `queryKeys.rooms.all`.
- **Schedule Changes** (`createSchedule`, `updateSchedule`, `deleteSchedule`): Invalidates `queryKeys.schedules.all`.
- **Command Delivery** (`useCommandLifecycle`): Upon confirmed delivery, invalidates `devices.all`, `rooms.all`, and `alerts.all`.

### 4.2 Background Refetch Form Protection (`Controls.tsx`)

Background polling introduces the hazard of overwriting uncommitted user inputs when telemetry or device metadata refetches. In `src/components/device/Controls.tsx`, form state is protected by a dual guard:

```typescript
const isEditingRef = useRef(false);
const [isDirty, setIsDirty] = useState(false);

useEffect(() => {
  if (isDirty || isEditingRef.current) return;
  if (warningVal !== undefined && criticalVal !== undefined) {
    setWarningThreshold(warningVal.toString());
    setCriticalThreshold(criticalVal.toString());
  }
}, [warningVal, criticalVal, hysteresisVal, debounceVal, isATS, isDirty]);
```

1. **Focus Tracking (`isEditingRef`)**: Set to `true` on input `onFocus` and `false` on `onBlur`. Prevents input fields currently focused by the operator from being overwritten during background query refreshes.
2. **Dirty Tracking (`isDirty`)**: Set to `true` on `onChange` when local input differs from server state. Persists across blur events until the operator explicitly clicks "Save" or "Reset to Current".
3. **Decoupled Metadata Stale Time**: In `device.$deviceId.tsx`, `queryKeys.devices.detail(devId)` uses `staleTime: 60_000` and `refetchInterval: false`, decoupling static device threshold metadata from the 3s live telemetry polling.

---

## 5. Command Lifecycle & Hardware Dispatch Coordination

Hardware command dispatch (controlling ATS generator start/stop, auto/manual mode, and AC setpoints) requires coordination between HTTP requests, asynchronous LoRa/MQTT radio delivery, and UI status reporting.

This lifecycle is governed by the custom hook `useCommandLifecycle` (`src/hooks/useCommandLifecycle.ts`):

```
┌──────┐ sendCommand() ┌─────────┐ HTTP 200 OK ┌────────┐ Poll 1.5s ┌───────────┐
│ idle │──────────────>│ queuing │─────────────>│ queued │──────────>│ delivered │
└──────┘               └─────────┘              └────────┘           └───────────┘
                            │                        │
                            │ HTTP Error             │ Timeout (12s)
                            v                        v
                       ┌─────────┐              ┌─────────┐
                       │  error  │              │ timeout │
                       └─────────┘              └─────────┘
```

1. **Queuing**: Dispatcher calls `POST /api/devices/{dev_id}/command`. State transitions to `queuing`, disabling buttons to prevent double-clicks (`isPending = true`).
2. **Queued**: If the response returns status `queued` with a `command_id`, the hook records `queuedAt = new Date()`, starts an elapsed-time seconds counter, and begins polling `GET /api/commands/{command_id}` every `1,500ms`.
3. **Dispatched**: When `fetchCommandStatus` returns `status: "dispatched"`, the hook stops polling, records the legacy `deliveredAt` timestamp field, triggers `onSuccess(cmdId)`, and invalidates `devices.all`, `rooms.all`, and `alerts.all`. The UI describes this as local MQTT broker acceptance and does not claim field-device execution. An auto-dismiss timer cleans the state after 8 seconds.
4. **Timeout Fallback**: If broker-dispatch confirmation is not received within `12,000ms`, the poll timer is aborted, status transitions to `timeout`, and a retry callback is primed.
5. **Memory Safety**: `useCommandLifecycle` tracks `isMountedRef` and cleans all active `setInterval` and `setTimeout` references on unmount.

---

## 6. Optimistic Updates vs Pessimistic Invalidation

The dashboard SPA currently relies almost exclusively on **pessimistic mutation workflows**:

1. Client fires mutation (`useMutation`).
2. Client waits for HTTP response.
3. On success, `onSuccess` calls `queryClient.invalidateQueries`.
4. UI waits for the subsequent `GET` query to resolve before updating visual states.

### 6.1 Gaps and Opportunities

- **Schedule Enabled Toggle** (`src/routes/schedules.tsx`):
  Toggling a schedule calls `updateMut.mutate({ id, payload: { enabled: !s.enabled } })`. During the network roundtrip, the switch toggle provides no intermediate feedback or instant visual latching. An optimistic update with `onMutate`, `cancelQueries`, `setQueryData`, and rollback `onError` would eliminate visual latency.
- **Threshold Configuration** (`Controls.tsx` & `HubsTab.tsx`):
  Currently updates local input immediately, but relies on full query invalidation for status badge verification.
- **Device Pairing / Unpairing** (`DevicesTab.tsx`):
  Relies entirely on full list refetch, causing a momentary table reload rather than optimistically updating row status.

---

## 7. Type Contract Synchronization (Backend Pydantic vs Frontend TypeScript)

Frontend data models in `src/types/api.ts` mirror HubGate backend Pydantic schemas (`server/schemasv5.py`, `server/app/routers/schedules.py`, `server/app/routers/devices.py`), but with specific structural discrepancies:

| Model / Field | Backend Pydantic Contract | Frontend TypeScript Contract | Drift & Impact |
| :--- | :--- | :--- | :--- |
| **`ScheduleResponse.next_runs`** | `next_runs: list[datetime] = Field(default_factory=list)` | Missing in `src/types/api.ts` | Frontend cannot read precomputed upcoming runs without invoking local client-side cron calculation. |
| **`ScheduleResponse.next_run`** | `next_run: Optional[datetime] = None` | `next_run_at?: string \| null` | Naming discrepancy: backend exposes both `next_run` and `next_run_at`. |
| **`DeviceResponse.status`** | `status: str = "offline"` (computed dynamically as `"pending"` \| `"online"` \| `"offline"`) | `status?: 'online' \| 'offline' \| 'pending'` | Frontend restricts to string union; backend schema defines free string, but router dynamically assigns `'pending' \| 'online' \| 'offline'`. |
| **`DeviceResponse.threshold_config`** | `ThresholdConfigSchema` (`warning: float`, `critical: float`, `hysteresis: float = 0.5`, `debounce_seconds: int = 60`) | `ThresholdConfig` (`warning: number`, `critical: number`, `hysteresis: number`, `debounce_seconds: number`) | Aligned across JSON serialization. |
| **AlertResponse.timestamp** | `UtcDateTime` (`_ensure_utc` validator enforces ISO 8601 with `Z`) | `timestamp: string` | Compatible; frontend `parseToDate` handles legacy unadorned strings defensively. |

---

## 8. Asset Splitting, Chunking & Preloading Architecture

To eliminate bundle bloat, accelerate initial page paint times, and prevent heavy secondary libraries from delaying telemetry rendering, the dashboard build is optimized across three mechanisms:

### 8.1 Rollup `manualChunks` Partitioning (`dashboard/vite.config.ts`)
The Vite configuration defines deterministic vendor chunk splitting based on dependency boundaries:
- **`vendor-react`**: Core React runtime (`react`, `react-dom`, `scheduler`).
- **`vendor-tanstack`**: Client cache and routing engine (`@tanstack/react-query`, `@tanstack/query-core`, `@tanstack/react-router`, `@tanstack/router-core`).
- **`vendor-ui`**: Design system primitives and icon libraries (`@radix-ui/*`, `lucide-react`, `class-variance-authority`, `tailwind-merge`, `clsx`).
- **`vendor-charts`**: Data visualization libraries (`recharts`, `@xyflow/*`).

This partitioning ensures that long-lived vendor packages remain immutably cached by client browsers across application code releases, cutting redeployment download sizes.

### 8.2 Lazy-Loaded Route Modals (`ScheduleDialog`)
Complex interactive dialogs and form trees with secondary dependencies are decoupled from their parent route chunks via dynamic `React.lazy` imports:
```typescript
// dashboard/src/routes/schedules.tsx
const ScheduleDialog = React.lazy(() => import("@/components/schedules/ScheduleDialog"));
```
This isolates cron preview calculations, tabbed schedule editors, and dialog markup from the main schedule list bundle, loading them on-demand only when an operator opens the creation or modification modal.

### 8.3 Intent-Based Preloading & Background Route Warmup
- **Hover Preloading**: `dashboard/src/App.tsx` configures the router with:
  ```typescript
  export const router = createRouter({
    routeTree,
    context: { queryClient },
    defaultPreload: 'intent',
    defaultPreloadDelay: 50,
    defaultPendingMs: 100,
    defaultPendingMinMs: 200,
  });
  ```
  When an operator hovers over navigation links for $\ge 50\text{ms}$, TanStack Router speculatively initiates route chunk downloading and query prefetching.
- **Idle Route Warmup**: Once authenticated, `dashboard/src/routes/__root.tsx` invokes `requestIdleCallback` to preload frequently navigated secondary views (`/hubs`, `/alerts`, `/map`, `/schedules`, `/settings`), guaranteeing instantaneous zero-latency page transitions during active operations.
