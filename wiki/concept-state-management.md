---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-dashboard-spa.md, wiki/concept-frontend-navigation.md, wiki/concept-frontend-resilience.md, wiki/concept-command-path.md, wiki/concept-telemetry-pipeline.md, wiki/workstream-flexible-scheduling.md]
sources: [dashboard/src/lib/queryClient.ts, dashboard/src/lib/queryKeys.ts, dashboard/src/lib/constants.ts, dashboard/src/lib/api.ts, dashboard/src/types/api.ts, dashboard/src/store/appStore.ts, dashboard/src/hooks/useCommandLifecycle.ts, dashboard/src/hooks/useDeviceHistory.ts, dashboard/src/components/device/Controls.tsx, dashboard/src/routes/schedules.tsx, dashboard/src/routes/index.tsx, dashboard/src/routes/alerts.tsx, dashboard/src/routes/settings.tsx, server/schemasv5.py, server/app/routers/schedules.py, server/app/routers/devices.py]
updated: 2026-09-03
---

# Frontend State Management Architecture

The smsb dashboard SPA (`dashboard/`) structures client state across three operational layers: server state managed by TanStack Query v5, navigational and filter state encoded into URL search parameters via TanStack Router with Zod validation, and local ephemeral UI state in React components. Client-global store state is defined in Zustand but remains isolated from active views.

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
│ • Hubs & Approvals            │ • Settings active tab         │ • Zustand UI │
│ • Flexible ATS Schedules      │ • Map view mode (plan/topo)   │   (orphaned) │
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

## 2. Polling Lifecycle Contracts & Memory Management

Telemetry monitoring requires continuous real-time data sync without WebSocket infrastructure. The SPA executes periodic HTTP polling bounded by route lifecycle and application state:

| Surface | Query Key | Interval | Background Tab (`refetchIntervalInBackground`) | Stale Time | Invalidation / Guard |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Root Bell Badge** | `alerts.list({ limit: 100 })` | `5,000ms` (`POLL_ALERTS_MS`) | `false` | `10s` | `enabled: !isLoginPage && !!currentUser` |
| **Dashboard Overview** | `rooms.list()`, `devices.list('all')`, `alerts.list(...)` | `3,000ms` (`POLL_MS`) | `true` (unthrottled) | `10s` | Active route `/` |
| **Dashboard Sparklines** | `rooms.sparklines('6h', 24)` | `30,000ms` | `false` (default) | `25s` | Single-pass batch query |
| **Room Detail** | `rooms.list()`, `rooms.map(roomId)`, `alerts.list(...)` | `3,000ms` (`POLL_MS`) | `true` (unthrottled) | `10s` | Active route `/room/$roomId` |
| **Device Detail** | `devices.detail(id)` | `false` (manual) | N/A | `60s` | Protected by `isEditingRef` & `isDirty` |
| **Device Telemetry** | `devices.history(id, range)` | `15,000ms` (`6h`/`24h`) or `false` (`7d`/`30d`) | `true` (unthrottled) | `10s` | Range-adaptive via `useDeviceHistory` |
| **Alerts Audit Table** | `alerts.list(filterHash)` | `3,000ms` (`POLL_MS`) | `false` | `10s` | Active route `/alerts` |
| **Hubs Management** | `hubs.list()` | `3,000ms` (`POLL_MS`) | `false` (default) | `10s` | Active route `/hubs` |
| **Hardware Command** | `GET /api/commands/{id}` | `1,500ms` | Managed via `setInterval` | N/A | `useCommandLifecycle` active state |

### 2.1 Background Tab Throttling Discrepancy

A divergent polling policy exists across routes regarding background tab execution:
- `__root.tsx`, `alerts.tsx`, and `map.tsx` explicitly set `refetchIntervalInBackground: false`. When an operator minimizes the browser or navigates to another application tab, polling suspends cleanly.
- In contrast, `index.tsx`, `room.$roomId.tsx`, `device.$deviceId.tsx`, and `useDeviceHistory.ts` explicitly configure `refetchIntervalInBackground: true`.
- **Operational Impact**: An unattended browser tab left open on `/`, `/room/1`, or `/device/dev-ats` continues firing network requests every 3 to 15 seconds indefinitely. This places continuous egress load on the client network and keeps database worker connections engaged on HubGate.

### 2.2 Query Key Cardinality Churn in Alerts

In `dashboard/src/routes/alerts.tsx`, the `start_time` query parameter is computed dynamically:
```typescript
const nowMinuteMs = Math.floor(Date.now() / 60000) * 60000;
if (selectedTimeRange === '6h') {
  startTimeIso = new Date(nowMinuteMs - 6 * 3600 * 1000).toISOString();
}
```
Because `startTimeIso` is embedded directly into the query key (`queryKeys.alerts.list({ ..., start_time: startTimeIso })`), every 60 seconds the query key string changes. TanStack Query instantiates a brand new cache entry every minute. While unused entries are purged after `gcTime: 5m`, combining this rolling key with filter permutations (room selections, device filters, severity, and pagination) multiplies active cache entries in browser memory.

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

### 3.3 Orphaned Zustand Store (`src/store/appStore.ts`)

The project contains a standalone Zustand store definition:
```typescript
import { create } from 'zustand';

interface AppUiState {
  sidebarOpen: boolean;
  selectedRoomId: string | null;
  setSidebarOpen: (open: boolean) => void;
  setSelectedRoomId: (id: string | null) => void;
}

export const useAppStore = create<AppUiState>((set) => ({
  sidebarOpen: true,
  selectedRoomId: null,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setSelectedRoomId: (id) => set({ selectedRoomId: id }),
}));
```

**Implementation Status**:
- `useAppStore` has zero imports across `dashboard/src/`.
- The sidebar in `src/routes/__root.tsx` is fixed (`w-64`) with no toggle control.
- Room selection is governed by path navigation (`/room/$roomId`), rendering `selectedRoomId` unreferenced.

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
3. **Delivered**: When `fetchCommandStatus` returns `status: "delivered"`, the hook stops polling, records `deliveredAt`, triggers `onSuccess(cmdId)`, and invalidates `devices.all`, `rooms.all`, and `alerts.all`. An auto-dismiss timer cleans the state after 8 seconds.
4. **Timeout Fallback**: If delivery confirmation is not received within `12,000ms`, the poll timer is aborted, status transitions to `timeout`, and a retry callback is primed.
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
| **`AlertResponse.timestamp`** | `UtcDateTime` (`_ensure_utc` validator enforces ISO 8601 with `Z`) | `timestamp: string` | Compatible; frontend `parseToDate` handles legacy unadorned strings defensively. |
