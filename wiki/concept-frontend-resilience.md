---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-dashboard-spa.md, wiki/concept-frontend-navigation.md, wiki/concept-state-management.md, wiki/concept-downsampling-v2.md, wiki/concept-telemetry-pipeline.md, wiki/workstream-shadcn-revert.md]
sources: [dashboard/src/components/ErrorBoundary.tsx, dashboard/src/routes/__root.tsx, dashboard/src/lib/queryClient.ts, dashboard/src/lib/api.ts, dashboard/src/lib/constants.ts, dashboard/src/routes/alerts.tsx, dashboard/src/routes/device.$deviceId.tsx, dashboard/src/routes/schedules.tsx, dashboard/src/components/device/chart/MultiPanelChartContainer.tsx, dashboard/src/components/device/chart/PanelOutages.tsx, dashboard/src/components/FreshnessBadge.tsx]
updated: 2026-09-03
---

# Frontend Resilience & Error Architecture

The smsb dashboard SPA (`dashboard/`) operates as a real-time operational interface in mission-critical smart building environments. Resilience requires defensive handling across network transport drops, expired authentication sessions, malformed telemetry payloads, and client-side rendering crashes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Active Error Boundary Tree                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  <App>                                                                      │
│    └── <RouterProvider>                                                    │
│          └── RootRoute (errorComponent: RootError)                          │
│                ├── <RootLayout>                                             │
│                │     ├── <AppSidebar> (Floating Aside & Drawer - preserved) │
│                │     ├── Sticky Inset Header (SidebarTrigger & Gateway Indicator)│
│                │     └── Inset Canvas <ErrorBoundary> (Route Content Containment)│
│                │           └── <Outlet> (Child Route Component)             │
│                │                 ├── RoomCard Grid                          │
│                │                 ├── <ErrorBoundary> (SVG Chart Containment)│
│                │                 │     └── MultiPanelChartContainer         │
│                │                 ├── <ErrorBoundary> (Canvas Containment)   │
│                │                 │     └── TopologyView                     │
│                │                 └── Connected Nodes Table                  │
│                └── RootError (Fallback on fatal router boot crash)          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Error Boundary Hierarchy & Active Containment Architecture

React component rendering exceptions are defensively isolated across multiple containment layers to prevent localized formatting or SVG calculation crashes from bringing down the operational shell.

### 1.1 Root Router Error Component (`src/routes/__root.tsx`)

TanStack Router catches uncaught route loader and root-level exceptions via `RootError`:

```typescript
function RootError({ error }: { error: Error }) {
  return (
    <div className="w-full min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-6 text-center gap-4">
      <h1 className="text-xl font-bold text-zinc-100">Application Error</h1>
      <p className="text-sm text-zinc-400 max-w-md">{error.message || 'Unexpected error'}</p>
      <button
        onClick={() => window.location.reload()}
        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-sm font-medium cursor-pointer"
      >
        Reload
      </button>
    </div>
  );
}
```

### 1.2 Active `<ErrorBoundary>` Mounting Hierarchy (`src/components/ErrorBoundary.tsx`)

The application mounts a standardized, class-based `ErrorBoundary` across three critical containment boundaries:

```typescript
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info);
  }
  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };
  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-lg text-center space-y-3">
          <h2 className="text-sm font-semibold text-zinc-200">Something went wrong</h2>
          <p className="text-xs text-zinc-500">{this.state.error?.message ?? 'Unexpected error'}</p>
          <button
            onClick={this.handleReset}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-medium cursor-pointer"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

**Active Mounting Locations**:
1. **Route Level (`src/routes/__root.tsx`)**: Wraps `<Outlet />` within the inset canvas container in `<RootLayout>`. If any route component fails to render, the error is trapped inside the main content canvas. The `<AppSidebar>` navigation, sticky header with `<SidebarTrigger>`, and gateway connection status indicators remain interactive, allowing the operator to navigate away to other views without a full browser reload.
2. **Chart Level (`src/components/device/chart/MultiPanelChartContainer.tsx`)**: Wraps the SVG canvas. Malformed telemetry or invalid coordinate math renders a scoped retry widget instead of crashing the device detail page.
3. **Canvas Level (`src/components/map/TopologyView.tsx`)**: Wraps the topology interactive canvas, ensuring network graph layout failures do not disrupt facility map navigation.
- Unit verified via `dashboard/src/components/__tests__/ErrorBoundary.test.tsx` (4 test cases).

---

## 2. Query Retry Policies & Error Handlers

TanStack Query manages transport resilience across intermittent WiFi or mobile cellular connections common in facility maintenance.

### 2.1 Global Retry Policy (`src/lib/queryClient.ts`)

```typescript
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_MS,
      gcTime: 5 * 60 * 1000,
      placeholderData: keepPreviousData,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status === 401) return false;
        return failureCount < 1;
      },
    },
  },
});
```

- **Single Retry (`failureCount < 1`)**: Failed queries retry exactly once before transitioning to `error` state. This bounds retry cascades and prevents client-side request storming against an unresponsive backend.
- **Immediate 401 Abort**: Queries encountering HTTP 401 abort immediately without retrying, bypassing unnecessary authentication retry loops.
- **Cache Error Callbacks**: Query and mutation cache errors currently log to `console.error` without emitting user-facing toast alerts or telemetry sink events.

---

## 3. 401 Interceptors & Authentication Redirect Storms

Session termination handling is split between client-side router navigation guards and low-level fetch interceptors.

### 3.1 Centralized Root Session Gate (`src/routes/__root.tsx`)

Authentication verification runs in the root route `beforeLoad`:

```typescript
beforeLoad: async ({ context, location }) => {
  if (location.pathname === '/login') return;
  try {
    const user = await context.queryClient.ensureQueryData({
      queryKey: queryKeys.auth.me(),
      queryFn: fetchCurrentUser,
      staleTime: 60000,
    });
    if (!user) {
      throw redirect({ to: '/login', search: { redirect: location.href } });
    }
    return { user };
  } catch (error: unknown) {
    if (isRedirect(error)) throw error;
    throw redirect({ to: '/login', search: { redirect: location.href } });
  }
}
```

`fetchCurrentUser()` handles 401 responses cleanly by returning `null`:
```typescript
export async function fetchCurrentUser(): Promise<UserResponse | null> {
  const res = await fetch(`${BASE}/api/auth/me`, { credentials: 'same-origin' });
  if (res.status === 401) return null;
  return handleResponse<UserResponse>(res);
}
```

### 3.2 Hard Window Redirect Storm Vulnerability (`src/lib/api.ts`)

In `src/lib/api.ts`, `handleResponse()` executes an imperative browser reload when any other API call encounters a 401:

```typescript
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/login') {
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    }
    let errorMessage = `HTTP Error ${res.status}: ${res.statusText}`;
    // ...
    throw new ApiError(res.status, errorMessage);
  }
  return res.json() as Promise<T>;
}
```

**Resilience Failure Mode**:
1. When an authentication session expires or is cleared, active polling queries (on the overview route `/`, queries run on Tier 2 6s jittered intervals) hit 401 simultaneously.
2. Multiple asynchronous calls concurrently execute `window.location.href = ...`.
3. This triggers competing full-page browser reloads, bypassing the TanStack Router client navigation stack and causing visual screen thrashing.
4. Hard redirecting circumvents client-side query cache cleanup and prevents displaying session-expired notification banners.

---

## 4. Offline & Degraded Network UX

### 4.1 Mocked Gateway Status Indicator

The global header in `src/routes/__root.tsx` renders a persistent connection status badge:

```tsx
<div className="flex items-center gap-1.5 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
  <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
  <span className="text-xs font-semibold text-emerald-400">Live Gateway Connected</span>
</div>
```

**Operational Risk**:
- The badge is hardcoded with a static green pulsing indicator.
- It has no connection to `navigator.onLine`, browser network events (`online`/`offline`), or TanStack Query cache status (`isError`).
- If HubGate crashes, Nginx returns 502, or the client loses network access, the header continues to declare "Live Gateway Connected".

### 4.2 Telemetry Outage Hatch Rendering (`MultiPanelChartContainer.tsx` & `PanelOutages.tsx`)

The charting pipeline implements resilient telemetry gap detection:
- `chartUtils.getMedianIntervalMs`: Identifies expected telemetry frequency.
- `chartUtils.getGapThresholdMs`: Establishes an outage threshold (`Math.max(GAP_FLOOR_MS, median * 10)`).
- `PanelOutages.tsx`: Renders dark SVG diagonal-striped hatch patterns (`<pattern id="hatch-outage" ...>`) over time spans where telemetry was absent, clearly communicating power/communication dropouts to facility managers rather than drawing misleading linear interpolation lines.

### 4.3 Epoch-0 Sync Guards (`FreshnessBadge.tsx`)

When devices are newly provisioned or query cache timestamps are uninitialized (`dataUpdatedAt = 0` or `undefined`), `FreshnessBadge` guards against rendering epoch dates (e.g. "56 years ago") by rendering `Awaiting sync`:

```typescript
if (!dataUpdatedAt || dataUpdatedAt === 0) {
  return <span className="...">Awaiting sync</span>;
}
```

---

## 5. Scroll Restoration & Navigational Continuity

### 5.1 Non-Resetting Scroll on Filter/Page Transitions

In `src/routes/alerts.tsx`, updating filter parameters or turning pages uses `resetScroll: false`:

```typescript
const updateSearch = (newParams: Partial<z.infer<typeof alertsSearchSchema>>) => {
  navigate({
    search: (prev) => ({
      ...prev,
      ...newParams,
      page: newParams.page !== undefined ? newParams.page : 1,
    }),
    resetScroll: false,
  });
};
```

This prevents the viewport from jumping to the top of the page on every filter interaction or page turn.

### 5.2 Zero-Flicker Transitions via `keepPreviousData`

All paginated and polled views employ `placeholderData: keepPreviousData`. When an operator clicks page 2 in the alert history table:
1. The table continues displaying page 1 rows while page 2 is in flight.
2. A subtle opacity change or disabled state indicates loading.
3. Page 2 swaps in instantly once fetched, preventing content jumping and cumulative layout shift (CLS).

### 5.3 Error Presentation in Dialogs vs Window Alerts

In `src/routes/schedules.tsx`, schedule deletion and "run-now" commands employ native browser `alert()` dialogs:
```typescript
onError: (e: Error) => alert(e.message),
onSuccess: () => alert("Run-now queued to pending_commands"),
```
Native `alert()` blocks the main browser thread, halts background query polling while the dialog is open, and cannot be styled or tested cleanly in automated suites.
