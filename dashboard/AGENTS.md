# AGENTS.md — dashboard

Parent: `AGENTS.md` (root) — DOX rail, stack, verification. This doc owns SPA-specific contracts.

## Purpose

React SPA for IoT smart-building monitoring. Live rooms/devices/alerts/map views polling HubGate V5 via same-origin `/api`.

## Ownership

- **dashboard/** owns SPA: routes, TanStack Query state, Zustand UI, build tooling.
- Root owns repo-wide rules, deployment, and cross-service contracts.

## Local Contracts

- **Stack**: React 19.2.7, TypeScript ~6.0.2, Vite 8.1.1, TanStack Router 1.170.17, TanStack Query 5.101.2, Zustand 5.0.14, Zod 4.4.3, Tailwind 4.3.2 (via `@tailwindcss/vite`), oxlint 1.71. `erasableSyntaxOnly:true` + `verbatimModuleSyntax:true` → `import type` only, no enums/namespaces. `@/*` → `./src/*`. Clean UTF-8 encoding maintained throughout (no mojibake).
- **Routes** (`src/routes/` → `routeTree.gen.ts` auto-generated, never edit): `/` (`index.tsx`), `/login`, `/alerts`, `/map`, `/hubs`, `/schedules`, `/settings`, `/room/$roomId`, `/device/$deviceId`.
- **Navigation & Preloading**: `App.tsx` configures `defaultPreload: 'intent'` with `defaultPreloadDelay: 50`, `defaultPendingMs: 100`, and `defaultPendingMinMs: 200`. Background idle route warmup runs in `__root.tsx` via `requestIdleCallback` (preloading `/hubs`, `/alerts`, `/map`, `/schedules`, `/settings` when authenticated). Top navigation progress bar displays on pending route transitions (`useRouterState({ select: (s) => s.status === 'pending' })`). Modal dialogs are split and lazy-loaded on demand (e.g. `ScheduleDialog` loaded via `React.lazy(() => import('@/components/schedules/ScheduleDialog'))` in `schedules.tsx`).
- **Server state & Centralized Constants**: TanStack Query via `src/lib/api.ts` + `src/lib/queryKeys.ts` factory + `src/lib/queryClient.ts` + `src/lib/scheduleApi.ts`. All polling intervals, stale durations, and timeouts are centralized in `src/lib/constants.ts` (`POLL_FAST_MS=3000`, `POLL_ALERTS_BADGE_MS=5000`, `POLL_HISTORY_REALTIME_MS=15000`, `POLL_SPARKLINES_MS=30000`, `POLL_COMMAND_STATUS_MS=1500`, `STALE_TELEMETRY_MS=10000`, `STALE_SPARKLINES_MS=25000`, `STALE_METADATA_MS=60000`, `COMMAND_DELIVERY_TIMEOUT_MS=12000`, `COMMAND_AUTO_DISMISS_MS=4000`, `GAP_FLOOR_MIN=5`). Polling policy strictly enforces `refetchIntervalInBackground: false` across all live views (`index.tsx`, `room.$roomId.tsx`, `device.$deviceId.tsx`, `useDeviceHistory.ts`), cleanly suspending polling in inactive background tabs. Root alert badge polling in `__root.tsx` uses `POLL_ALERTS_BADGE_MS` and is gated with `enabled: !isLoginPage && !!currentUser`. Device detail metadata uses decoupled `queryKeys.devices.detail(devId)` (`staleTime: STALE_METADATA_MS`, `refetchInterval: false`, `refetchOnWindowFocus: true`) with focus/dirty guarded form sync in `Controls.tsx` (`isEditingRef` + `isDirty`) to prevent background refetches from overwriting active user input. Telemetry history uses `useDeviceHistory(deviceId, timeRange)` with range-adaptive polling (15s for `6h`/`24h`, `false` / manual for `7d`/`30d`). Command dispatch uses `useCommandLifecycle` hook polling `GET /api/commands/{command_id}` every 1.5s with 12s timeout and double-dispatch lock (`isPending`). ATS telemetry renders via `HistoryChart` 3-panel stacked layout (PLN Grid + Genset + Starter Battery DC with 11.8V warning / 11.2V critical threshold guides, independent Y-axes with chart panel header toggles controlling Auto Scale switching between dynamic 12% padded `computeYScale` and fixed preset ranges `PRESET_SCALES` rather than hiding series, synchronized X-axis across panels, and lifted crosshair/tooltip). `queryClient.ts` defaults: `placeholderData: keepPreviousData` (no blank refetch), `gcTime 5m`, `refetchOnWindowFocus: true`, retry predicate disables retries on HTTP 401 (`error instanceof ApiError && error.status === 401`). Mutations invalidate relevant keys. `FreshnessBadge` treats `dataUpdatedAt=0`/undefined as `Awaiting sync` (epoch-0 guard). `schedules` via `queryKeys.schedules` flexible cron `Asia/Jakarta`.
- **Pagination & Event Lists**: Standardized accessible `<Pagination>` component (`src/components/ui/pagination.tsx`) with First/Prev/Numbered/Next/Last navigation, dynamic ellipsis, items range summary (`Showing X–Y of Z`), and disabled loading states. Full-page `/alerts` stores `page` in URL search params validated via Zod (`page: z.number().int().positive().catch(1)`), fetches with `PAGE_SIZE=15` (`limit` and `offset`), uses `resetScroll: false` on `navigate` search updates to preserve scroll position, and uses `placeholderData: keepPreviousData` to prevent layout collapse during page turns. Device detail (`/device/$deviceId`) alert history paginates with `DEVICE_ALERT_PAGE_SIZE=10`, local `alertPage` state reset on device change, and `keepPreviousData`.
- **Room View & AC Telemetry**: `room.$roomId.tsx` provides full telemetry cards for TS, ATS, and AC nodes. AC cards render ambient room temp, humidity, plus AC1/AC2 power status (ON/OFF) and target setpoints. Floor plan marker tooltips render ambient temp/humidity and dual AC operational status on hover.
- **Dynamic Room Cards & Two-Pass Sparklines**: `RoomCard.tsx` is a pure presentation component (no internal `useQuery(fetchRoomMap)`). Supports 4 permutations: Section A (TS/AC Math.max instant readings + 6h room sparklines), Section B (ATS power state badge + <=11.8V warning / <=11.2V critical battery badges), Section A+B stacked, and Section C ("No sensors paired" placeholder). `index.tsx` fetches sparklines via single batch `queryKeys.rooms.sparklines('6h', 24)` (`refetchInterval: 30000`, `staleTime: 25000`), displays a responsive 4-per-row grid defaulting to 8 rooms with a centered glyph-only expand/collapse control when rooms > 8.
- **Client UI state**: React component state and URL search params via TanStack Router (no global client store needed).
- **Auth & Error Containment**: `fetchCurrentUser` in `src/lib/api.ts` returns `null` on 401 without hard window redirects; `beforeLoad` in `__root.tsx` performs client-side router redirect to `/login?redirect=...`; `<ErrorBoundary>` mounting hierarchy: mounted around `<Outlet />` in `src/routes/__root.tsx`, around the SVG chart canvas in `MultiPanelChartContainer.tsx`, and around the interactive canvas in `TopologyView.tsx`, isolating render exceptions from whole-page blanking; `QueryCache.onError` handles unhandled fetch failures.
- **Same-origin**: Vite proxy `/api`→`127.0.0.1:8000` (dev); Nginx `443`→`127.0.0.1:8000` (prod). No CORS.
- **Build**: `src/main.tsx` → `App.tsx` (Router + QueryClientProvider), `src/index.css` Tailwind 4 `@theme` (`--color-background:#09090b` `--color-primary:#6366f1`), `components.json` `new-york` shadcn, `src/types/api.ts` matches HubGate Pydantic models (including `CommandStatusResponse`), `src/lib/utils.ts` `cn()` = `clsx + tailwind-merge`, `src/components/ui/*` + `src/lib/cron.ts` cron helpers. Vite build leverages Rollup `manualChunks` code splitting: `vendor-react` (react, react-dom, scheduler), `vendor-tanstack` (Query & Router), `vendor-ui` (Radix UI, Lucide icons, Tailwind utilities), and `vendor-charts` (Recharts, XYFlow).
 
## Work Guidance
 
- Add route file in `src/routes/` — plugin regenerates `routeTree.gen.ts`.
- Sort/filter/range/page state for full views in URL search params with Zod `validateSearch` + `Route.useSearch()` (use `resetScroll: false` on `navigate` search updates to preserve scroll position on filter/page changes); not component state.
- Server state only via Query hooks + `queryKeys` factory; use `constants.ts` for `POLL_MS`/`STALE_MS`/`GAP_FLOOR_MIN`/`POLL_ALERTS_MS`.
- Command dispatch should use `useCommandLifecycle` to handle queuing, delivery status polling against `GET /api/commands/{command_id}`, timeout fallbacks, retry, and `CommandStatusBadge` feedback.
- Forms editing server-backed configuration (e.g. threshold config in `Controls.tsx`) must guard against background query refetch overwrites using `isDirty` state and focus tracking `isEditingRef`.
- Keep `src/components/` and `src/hooks/` splits (e.g., `device/HistoryChart`, `device/Controls`, `device/CommandStatusBadge`, `settings/RoomsTab`, `useDeviceHistory`, `useCommandLifecycle`).
- Wall-clock timestamps render `id-ID` + `timeZone: 'Asia/Jakarta'` + `' WIB'` everywhere (server stores UTC): `chartUtils.ts`, `dateUtils.ts`, `alerts.tsx`, `device.$deviceId.tsx`, `index.tsx`. Relative ages (`FreshnessBadge`, `hubs.tsx formatRelative`) use epoch diff - no TZ.
- Use `just` runner: `just dev` / `just lint` / `just build` / `just test`; do not add enums.
 
## Verification
 
- `npm run lint` in `dashboard/` — oxlint, 0 errors, 21 fast-refresh warnings.
- `npm run build` in `dashboard/` — `tsc -b && vite build` (hidden sourcemap, verified manualChunks asset splitting).
- `npm run test -- --run` — vitest (116 passing tests across 13 suites in `src/**/__tests__/`).
- `npx playwright test --list` / `npm run e2e` — playwright 1.62.1 (`e2e/`, needs Vite `:5173`).

## Child DOX Index

None — no further children under `dashboard/`.
