---
type: concept
governed_by: AGENTS.md
links: [wiki/entity-dashboard-spa.md, wiki/entity-hubgate-v5.md, wiki/concept-telemetry-pipeline.md]
sources: [dashboard/src/App.tsx, dashboard/src/routes/__root.tsx, dashboard/src/lib/api.ts, dashboard/src/lib/queryClient.ts, dashboard/src/routes/hubs.tsx, dashboard/src/routes/schedules.tsx, dashboard/src/routes/settings.tsx, commit:b290e3c]
updated: 2026-09-02
---

# Frontend Navigation Architecture

The smsb dashboard SPA (`dashboard/`) implements a high-performance navigation architecture built on TanStack Router and TanStack Query. It combines intent-based preloading, background idle route warmup, viewport-top visual feedback, and streamlined authentication flow to provide near-instantaneous page transitions with zero visual flashing.

## 1. Intent Preloading (`defaultPreload: 'intent'`)

Router configuration in `dashboard/src/App.tsx` establishes intent-driven route chunk and data preloading:

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

- **Hover & Focus Trigger**: When a user hovers over or focuses a `<Link>` component (sidebar navigation, room breadcrumb, device link), TanStack Router detects user intent.
- **Debounced Preloading**: With `defaultPreloadDelay: 50`, if the pointer remains over the element for 50ms, the router initiates parallel asynchronous prefetching of both the JavaScript route component chunk and any associated route loader data.
- **Instant Activation**: By the time the user completes a physical click (typically 100–150ms after pointer enter), all assets and initial query caches are primed in browser memory, enabling a 0ms render transition.

## 2. Background Idle Route Warmup on Mount

To ensure instantaneous transitions even on the first navigation click of a session, `RootLayout` in `dashboard/src/routes/__root.tsx` executes background route warmup:

```typescript
useEffect(() => {
  if (!isLoginPage && currentUser) {
    const routes = ['/hubs', '/alerts', '/map', '/schedules', '/settings'];
    const preloadAll = () => {
      routes.forEach((to) => {
        router.preloadRoute({ to: to as any }).catch(() => {});
      });
    };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(preloadAll);
    } else {
      setTimeout(preloadAll, 1000);
    }
  }
}, [isLoginPage, !!currentUser, router]);
```

- **Non-Blocking Scheduling**: Uses `requestIdleCallback` (with a 1-second `setTimeout` fallback) to defer prefetching until after the initial dashboard view has completely painted and the main thread is idle.
- **Targeted Surface**: Prefetches the primary operational surfaces (`/hubs`, `/alerts`, `/map`, `/schedules`, `/settings`), warming Vite code splits and module dependencies into the browser HTTP/disk cache without contending for network bandwidth during initial login.

## 3. Viewport-Top Navigation Progress Indicator

To eliminate disruptive full-page loading spinners or blank layout flashes during network latency:

- **Pending State Detection**: Evaluates `isNavigating = useRouterState({ select: (s) => s.status === 'pending' })`.
- **Top Pinned Indicator**: When a navigation loader takes longer than `defaultPendingMs: 100`, a slim, high-visibility 1px indigo bar renders at the top of the viewport:
  ```tsx
  {isNavigating && <div className="fixed top-0 left-0 right-0 h-1 bg-indigo-500 z-50 animate-pulse" />}
  ```
- **Consistent Visual Anchor**: Present across both the dashboard authenticated shell and the standalone login layout, maintaining visual continuity while preserving the existing view content intact until the target route is ready.

## 4. Clean 401 Unauthenticated Routing & Cache Optimization

Prior iterations suffered from redundant authentication roundtrips and redirect loops: every child route's `beforeLoad` invoked `fetchCurrentUser()`, and 401 responses triggered React Query retry storms. The hardened navigation model streamlines session validation:

1. **Centralized Root `beforeLoad` Guard**:
   In `__root.tsx`, session verification is performed once at the root level using `ensureQueryData`:
   ```typescript
   const user = await context.queryClient.ensureQueryData({
     queryKey: queryKeys.auth.me(),
     queryFn: fetchCurrentUser,
     staleTime: 60000,
   });
   if (!user) {
     throw redirect({ to: '/login', search: { redirect: location.href } });
   }
   ```
2. **Defensive 401 Handling in API Layer**:
   In `src/lib/api.ts`, `fetchCurrentUser()` explicitly catches 401 status and returns `null` instead of throwing an unhandled `ApiError`:
   ```typescript
   export async function fetchCurrentUser(): Promise<UserResponse | null> {
     const res = await fetch(`${BASE}/api/auth/me`, { credentials: 'same-origin' });
     if (res.status === 401) return null;
     return handleResponse<UserResponse>(res);
   }
   ```
3. **No-Retry on 401 in QueryClient**:
   `dashboard/src/lib/queryClient.ts` customizes the global retry handler to never retry authentication failures:
   ```typescript
   retry: (failureCount, error) => {
     if (error instanceof ApiError && error.status === 401) return false;
     return failureCount < 1;
   }
   ```
4. **Child Route De-duplication**:
   Child routes (`/hubs`, `/schedules`) do not define redundant `beforeLoad` auth checks. Privileged routes (`/settings`) simply verify the cached user from `context.user` or `queryClient.getQueryData`, avoiding duplicate network roundtrips.
