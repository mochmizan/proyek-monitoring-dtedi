# AGENTS.md — dashboard

Parent: `AGENTS.md` (root) — DOX rail, stack, verification. This doc owns SPA-specific contracts.

## Purpose

React SPA for IoT smart-building monitoring. Live rooms/devices/alerts/map views polling HubGate V5 via same-origin `/api`.

## Ownership

- **dashboard/** owns SPA: routes, TanStack Query state, Zustand UI, build tooling.
- Root owns repo-wide rules, deployment, and cross-service contracts.

## Local Contracts

- **Stack**: React 19.2.7, TypeScript ~6.0.2, Vite 8.1.1, TanStack Router 1.170.17, TanStack Query 5.101.2, Zustand 5.0.14, Zod 4.4.3, Tailwind 4.3.2 (via `@tailwindcss/vite`), oxlint 1.71. `erasableSyntaxOnly:true` + `verbatimModuleSyntax:true` → `import type` only, no enums/namespaces. `@/*` → `./src/*`.
- **Routes** (`src/routes/` → `routeTree.gen.ts` auto-generated, never edit): `/` (`index.tsx`), `/login`, `/alerts`, `/map`, `/hubs`, `/schedules`, `/settings`, `/room/$roomId`, `/device/$deviceId`.
- **Server state**: TanStack Query via `src/lib/api.ts` + `src/lib/queryKeys.ts` factory + `src/lib/queryClient.ts` + `src/lib/scheduleApi.ts`. Live views poll `POLL_MS=3000` / `STALE_MS=10000` from `src/lib/constants.ts` (`GAP_FLOOR_MIN=5` for chart gaps). `queryClient.ts` defaults: `placeholderData: keepPreviousData` (no blank refetch), `gcTime 5m`, `refetchOnWindowFocus: true`, `retry 1`. Mutations invalidate relevant keys. `FreshnessBadge` treats `dataUpdatedAt=0`/undefined as `Awaiting sync` (epoch-0 guard). `schedules` via `queryKeys.schedules` flexible cron `Asia/Jakarta`.
- **Client UI state**: Zustand `src/store/appStore.ts` only `sidebarOpen` / `selectedRoomId`.
- **Auth & errors**: `GET /api/auth/me` session check in `beforeLoad`; 401 redirect to `/login?redirect=…`; `ErrorBoundary` (`src/components/ErrorBoundary.tsx`) at App root + `QueryCache.onError`.
- **Same-origin**: Vite proxy `/api`→`127.0.0.1:8000` (dev); Nginx `443`→`127.0.0.1:8000` (prod). No CORS.
- **Build**: `src/main.tsx` → `App.tsx` (Router + QueryClientProvider), `src/index.css` Tailwind 4 `@theme` (`--color-background:#09090b` `--color-primary:#6366f1`), `components.json` `new-york` shadcn, `src/types/api.ts` matches HubGate Pydantic models, `src/lib/utils.ts` `cn()` = `clsx + tailwind-merge`, `src/components/ui/*` + `src/lib/cron.ts` cron helpers.

## Work Guidance

- Add route file in `src/routes/` — plugin regenerates `routeTree.gen.ts`.
- Sort/filter/range state in URL search params with Zod `validateSearch` + `Route.useSearch()`; not component state.
- Server state only via Query hooks + `queryKeys` factory; use `constants.ts` for `POLL_MS`/`STALE_MS`/`GAP_FLOOR_MIN`.
- Keep `src/components/` and `src/hooks/` splits (e.g., `device/HistoryChart`, `settings/RoomsTab`, `useDeviceHistory`).
- Wall-clock timestamps render `id-ID` + `timeZone: 'Asia/Jakarta'` + `' WIB'` everywhere (server stores UTC): `chartUtils.ts`, `alerts.tsx`, `device.$deviceId.tsx`, `index.tsx`. Relative ages (`FreshnessBadge`, `hubs.tsx formatRelative`) use epoch diff - no TZ.
- Use `just` runner: `just dev` / `just lint` / `just build` / `just test`; do not add enums.

## Verification

- `npm run lint` in `dashboard/` — oxlint, 0 errors.
- `npm run build` in `dashboard/` — `tsc -b && vite build` (hidden sourcemap).
- `npm run test -- --run` — vitest 3 (jsdom, `src/__tests__/`).
- `npx playwright test --list` / `npm run e2e` — playwright 1.62.1 (`e2e/`, needs Vite `:5173`).

## Child DOX Index

None — no further children under `dashboard/`.
