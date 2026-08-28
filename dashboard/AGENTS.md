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
- **Server state**: TanStack Query via `src/lib/api.ts` + `src/lib/queryKeys.ts` factory + `src/lib/queryClient.ts` + `src/lib/scheduleApi.ts`. Live views poll `POLL_MS=3000` / `STALE_MS=2000` from `src/lib/constants.ts` (`GAP_FLOOR_MIN=5` for chart gaps). Mutations invalidate relevant keys. `schedules` via `queryKeys.schedules` flexible cron `Asia/Jakarta`.
- **Client UI state**: Zustand `src/store/appStore.ts` only `sidebarOpen` / `selectedRoomId`.
- **Auth & errors**: `GET /api/auth/me` session check in `beforeLoad`; 401 redirect to `/login?redirect=…`; `ErrorBoundary` (`src/components/ErrorBoundary.tsx`) at App root + `QueryCache.onError`.
- **Same-origin**: Vite proxy `/api`→`127.0.0.1:8000` (dev); Nginx `443`→`127.0.0.1:8000` (prod). No CORS.
- **Build**: `src/main.tsx` → `App.tsx` (Router + QueryClientProvider), `src/index.css` Tailwind 4 `@theme inline` (`--color-background:#09090b` `--color-primary:#6366f1` `--color-accent:#14b8a6` `--color-chart-1..5` `--color-popover` `--radius:0.625rem` `--font-mono:"Fragment Mono"` `--font-serif:"Source Serif 4"` + `Inter` import, tokens `--ease-out/--ease-in-out` + `.button:active scale(0.97)` + `.tooltip transform-origin:var(--transform-origin)` + stagger `fadeIn` + `prefers-reduced-motion` + hover guard), `components.json` `new-york` shadcn `rsc:false`, `src/types/api.ts` matches HubGate Pydantic models, `src/lib/utils.ts` `cn()` = `clsx + tailwind-merge`, `src/components/ui/*` (chart/separator/alert/skeleton/tooltip/avatar/empty/input-group/field/toggle-group + calendar/select/dialog etc) + `src/lib/cron.ts` cron helpers.
- **Design system (dashboard-full-shadcn-redesign-2026-08-29)**: semantic tokens only (`bg-background/bg-card/text-muted-foreground/border` forbids `bg-red-500/bg-blue/text-white/dark:`), typography roles Display `font-serif` / Body `Inter` / Data `font-mono`, Card composition `CardHeader/Title/Description/Content/Footer` + `Separator` for rules + `Skeleton` for loading (not `animate-pulse`) + `Alert` for callouts + `Badge` for status/type + `Avatar+AvatarFallback` + `Dialog/Sheet` always `Title` + `SelectItem→SelectGroup` + `TabsTrigger→TabsList` + `ToggleGroup type="single"` for 2-7 choices + `FieldGroup/Field/InputGroup` with `data-invalid/aria-invalid` + `TooltipProvider` origin-aware + `Empty` for zero states + spacing `gap-*` not `space-y-*` + sizing `size-*` not `w-*/h-*` + icons in `Button/TabsTrigger` use `data-icon` not `size-4` + motion press/tooltip per emil tokens; `schedules` polished only.

## Work Guidance

- Add route file in `src/routes/` — plugin regenerates `routeTree.gen.ts`.
- Sort/filter/range state in URL search params with Zod `validateSearch` + `Route.useSearch()`; not component state.
- Server state only via Query hooks + `queryKeys` factory; use `constants.ts` for `POLL_MS`/`STALE_MS`/`GAP_FLOOR_MIN`.
- Keep `src/components/` and `src/hooks/` splits (e.g., `device/HistoryChart`, `settings/RoomsTab`, `useDeviceHistory`).
- Use `just` runner: `just dev` / `just lint` / `just build` / `just test`; do not add enums.

## Verification

- `npm run lint` in `dashboard/` — oxlint, 0 errors.
- `npm run build` in `dashboard/` — `tsc -b && vite build` (hidden sourcemap).
- `npm run test -- --run` — vitest 3 (jsdom, `src/__tests__/`).
- `npx playwright test --list` / `npm run e2e` — playwright 1.62.1 (`e2e/`, needs Vite `:5173`).

## Child DOX Index

None — no further children under `dashboard/`.
