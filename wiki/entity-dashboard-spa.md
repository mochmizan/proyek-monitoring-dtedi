---
type: entity
governed_by: AGENTS.md
links: [wiki/concept-frontend-navigation.md, wiki/concept-downsampling-v2.md, wiki/concept-telemetry-pipeline.md, wiki/concept-time-conventions.md, wiki/concept-command-path.md, wiki/workstream-flexible-scheduling.md, wiki/workstream-shadcn-revert.md]
sources: [dashboard/src/App.tsx, dashboard/src/routes/__root.tsx, dashboard/src/lib/queryClient.ts, dashboard/src/lib/constants.ts, dashboard/src/hooks/useCommandLifecycle.ts, dashboard/src/hooks/useDeviceHistory.ts, dashboard/src/components/device/HistoryChart.tsx, dashboard/src/components/device/Controls.tsx, dashboard/src/routes/, dashboard/AGENTS.md, commit:b290e3c]
updated: 2026-09-02
---

# Dashboard SPA (dashboard/)

The smsb dashboard is a React 19 + TypeScript SPA (Vite 8) speaking same-origin `/api` to HubGate — Vite proxy in dev, Nginx 443 in prod, no CORS anywhere.

Routing is TanStack Router file-based (`src/routes/`: dashboard `/`, `/login`, `/alerts`, `/map`, `/hubs`, `/schedules`, `/settings`, `/room/$roomId`, `/device/$deviceId`); `routeTree.gen.ts` is generated. Navigation employs intent preloading (`defaultPreload: 'intent'`, 50ms delay), background idle route warmup on mount via `requestIdleCallback`, and a top-of-viewport progress indicator (see [concept-frontend-navigation.md](concept-frontend-navigation.md)). Server state is TanStack Query polling at `POLL_MS=3000` on live list views with cache-first defaults (global `keepPreviousData`, `gcTime 5m`, `refetchOnWindowFocus`, `STALE_MS 10s`) so navigating or refetching never blanks the UI. Client UI state is only Zustand `sidebarOpen`/`selectedRoomId`; sort/filter/range state lives in URL search params validated by Zod.

Device detail views (`/device/$deviceId`) decouple metadata polling from live telemetry via `queryKeys.devices.detail(devId)` (`staleTime: 60s`, `refetchInterval: false`, `refetchOnWindowFocus: true`), protected by focus and dirty guards (`isEditingRef` + `isDirty`) in `Controls.tsx` so background refetches never overwrite uncommitted threshold inputs. Telemetry history uses `useDeviceHistory` with range-adaptive polling (15s for 6h/24h, static/manual for 7d/30d) and a manual refresh trigger. ATS telemetry renders via `HistoryChart` with a 3-panel stacked layout (PLN Grid AC, Genset AC, and DC Starter Battery with 11.8V warning and 11.2V critical threshold guides), independent auto-scaled Y-axes with 12% padding (`computeYScale`), synchronized X-axis time coordinates, lifted tooltip, and panel header auto-scale toggles (dynamic auto-scale vs fixed preset scale).

Hardware command dispatch uses `useCommandLifecycle` to coordinate state across `idle`, `queuing`, `queued`, `delivered`, `timeout`, and `error`. It polls `GET /api/commands/{command_id}` every 1.5s until `delivered_at` is confirmed by HubBrain, enforces a 12s timeout fallback with manual retry, and locks controls against double dispatch (`isPending`).

All wall-clock timestamps render `id-ID` with `timeZone: 'Asia/Jakarta'` and a `WIB` suffix; relative ages (FreshnessBadge, hub last-seen) are epoch diffs and timezone-free. `chartUtils.parseToDate` appends `Z` to naive ISO strings as a client-side defense.

Styling is Tailwind 4 via `@tailwindcss/vite` with the shadcn `new-york` primitives in `src/components/ui/*`, dark theme `#09090b`, primary `#6366f1`. The map route lazy-loads `@xyflow/react` (TopologyView ~182kB chunk). The `/schedules` route drives flexible cron warmup scheduling (see [workstream-flexible-scheduling.md](workstream-flexible-scheduling.md)).
