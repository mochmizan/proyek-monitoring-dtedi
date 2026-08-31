---
type: entity
governed_by: AGENTS.md
links: [wiki/concept-telemetry-pipeline.md, wiki/concept-time-conventions.md, wiki/workstream-flexible-scheduling.md, wiki/workstream-shadcn-revert.md]
sources: [dashboard/src/lib/queryClient.ts, dashboard/src/lib/constants.ts, dashboard/src/routes/, dashboard/AGENTS.md]
updated: 2026-08-31
---

# Dashboard SPA (dashboard/)

The smsb dashboard is a React 19 + TypeScript SPA (Vite 8) speaking same-origin `/api` to HubGate — Vite proxy in dev, Nginx 443 in prod, no CORS anywhere.

Routing is TanStack Router file-based (`src/routes/`: dashboard `/`, `/login`, `/alerts`, `/map`, `/hubs`, `/schedules`, `/settings`, `/room/$roomId`, `/device/$deviceId`); `routeTree.gen.ts` is generated. Server state is TanStack Query polling at `POLL_MS=3000` with cache-first defaults (global `keepPreviousData`, `gcTime 5m`, `refetchOnWindowFocus`, `STALE_MS 10s`) so navigating or refetching never blanks the UI. Client UI state is only Zustand `sidebarOpen`/`selectedRoomId`; sort/filter/range state lives in URL search params validated by Zod.

All wall-clock timestamps render `id-ID` with `timeZone: 'Asia/Jakarta'` and a `WIB` suffix; relative ages (FreshnessBadge, hub last-seen) are epoch diffs and timezone-free. `chartUtils.parseToDate` appends `Z` to naive ISO strings as a client-side defense.

Styling is Tailwind 4 via `@tailwindcss/vite` with the shadcn `new-york` primitives in `src/components/ui/*`, dark theme `#09090b`, primary `#6366f1`. The map route lazy-loads `@xyflow/react` (TopologyView ~182kB chunk). The `/schedules` route drives flexible cron warmup scheduling (see [workstream-flexible-scheduling.md](workstream-flexible-scheduling.md)).
