# AGENTS.md â€” gui-app

React 19.2.7 + TypeScript ~6.0.2 + Vite ^8.1.1 SPA for IoT smart-building monitoring (TanStack Query 5.101.2, oxlint 1.71). **Connected to live HubGate V5 backend via TanStack Query and Same-Origin Vite Proxy.**

## Ownership

- **gui-app/**: SPA source code â€” routes, TanStack Query hooks, Zustand UI store, build tooling
- Owned by root AGENTS.md for repo-wide rules, commands, stack, and verification

## Architecture

**Server State**: Managed via TanStack Query (`@tanstack/react-query`) with centralized API client (`src/lib/api.ts`) and query keys (`src/lib/queryKeys.ts`).
- Live views (Dashboard, Room Detail, Device Detail, Map, Alerts) poll every 3 seconds (`refetchInterval: 3000`, `staleTime: 2000`).
- Mutations (Rooms CRUD, Device Pairing/Unpairing, Threshold Updates, Commands, Auth) automatically invalidate relevant query keys.

**Client UI State**: Minimal Zustand store (`src/store/appStore.ts`) strictly for local UI state (`sidebarOpen`, `selectedRoomId`).

**Auth & Route Protection**:
- Session verification via `GET /api/auth/me` in TanStack Router `beforeLoad`.
- Unauthenticated access redirects to `/login?redirect=...`.
- Settings view guarded for `admin` role only.

**Same-Origin Flow**:
- Dev: Vite dev-server proxy in `vite.config.ts` proxies `/api` and `/static` to `http://127.0.0.1:8000`.
- Prod: Nginx serves static SPA assets at `/` and reverse-proxies `/api` to Uvicorn on the same origin (`SameSite=Lax` cookies).

## Routes & Search Params

| Route | File | Search Params | Notes |
|---|---|---|---|
| `/` | `index.tsx` | `sortBy`, `sortOrder` | Live room & device status with dynamic auto-discovery |
| `/login` | `login.tsx` | `redirect` | Argon2id session authentication |
| `/alerts` | `alerts.tsx` | `rooms[]`, `devices[]`, `severity`, `timeRange` | Multi-filter alert log |
| `/map` | `map.tsx` | â€” | Interactive floor plan markers |
| `/hubs` | `hubs.tsx` | â€” | Edge hub presence grid: live online/offline cards, device roster per hub, admin approve/revoke actions |
| `/settings` | `settings.tsx` | `tab` | Rooms CRUD & live unapproved device pairing |
| `/room/$roomId` | `room.$roomId.tsx` | `range` | Room telemetry aggregate & device list |
| `/device/$deviceId` | `device.$deviceId.tsx` | `range` | Time-scaled telemetry chart (TS/AC/ATS) across 6h/24h/7d/30d in Jakarta Time (WIB) & dynamic Command Dispatch (AC IR / ATS) |

## Source Layout

```
src/
â”œâ”€â”€ main.tsx              â† entry: createRoot â†’ <App/> wrapped in ErrorBoundary
â”œâ”€â”€ App.tsx               â† TanStack Router + QueryClientProvider setup
â”œâ”€â”€ index.css             â† Tailwind 4 @import + @theme vars (dark)
â”œâ”€â”€ routeTree.gen.ts      â† AUTO-GENERATED â€” never edit
â”œâ”€â”€ components/
â”‚   â”œâ”€â”€ ErrorBoundary.tsx â† class ErrorBoundary (catches render crashes; used at App root)
â”‚   â”œâ”€â”€ RoomCard.tsx, StatusDot.tsx, FreshnessBadge.tsx, Sparkline.tsx, TopologyView.tsx
â”‚   â”œâ”€â”€ device/           â† Controls.tsx, HistoryChart.tsx (split from device.$deviceId.tsx)
â”‚   â””â”€â”€ settings/         â† RoomsTab.tsx, DevicesTab.tsx, HubsTab.tsx (split from settings.tsx)
â”œâ”€â”€ hooks/
â”‚   â””â”€â”€ useDeviceHistory.ts â† history query hook (wraps api + gap-aware chart logic)
â”œâ”€â”€ routes/               â† 9 page components (see table above)
â”œâ”€â”€ store/
â”‚   â””â”€â”€ appStore.ts       â† minimal Zustand store (sidebarOpen, selectedRoomId)
â”œâ”€â”€ types/
â”‚   â””â”€â”€ api.ts            â† TypeScript interfaces matching HubGate V5 Pydantic models
â”œâ”€â”€ __tests__/            â† vitest unit tests (jsdom, setup.ts)
â”œâ”€â”€ e2e/                  â† playwright e2e tests (playwright.config.ts, webServer: vite :5173)
â””â”€â”€ lib/
    â”œâ”€â”€ api.ts            â† centralized Fetch API client with error handling
    â”œâ”€â”€ queryClient.ts    â† shared QueryClient instance
    â”œâ”€â”€ queryKeys.ts      â† hierarchical query key factory for caching & invalidation
    â”œâ”€â”€ constants.ts      â† POLL_MS=3000, STALE_MS=2000, GAP_FLOOR_MIN=5 (single source of polling/gap constants)
    â”œâ”€â”€ chartUtils.ts     â† gap detection + offline shading helpers (used by HistoryChart)
    â””â”€â”€ utils.ts          â† cn() = clsx + tailwind-merge
```

## State & Data Flow

- **Live Data Polling**: Dashboard, Room Detail, Device Detail, Map, and Alerts use TanStack Query hooks (`useQuery`) with 3s refetch intervals.
- **History Analytics**: `device.$deviceId.tsx` queries `GET /api/devices/{id}/history?range=6h|24h|7d|30d|all` with time-proportional X-axis scaling, Zod URL parameter synchronization, and Jakarta Time (`Asia/Jakarta` / WIB) display formatting. Chart is gap-aware: `GAP_FLOOR 5 min` + `10Ã—median interval` threshold breaks lines (`M` vs `L`), shades offline spans (including leading window-startâ†’first-point gap), renders isolated-point dots, and per-segment area fill (Grafana/uPlot pattern).
- **Air Conditioner Control**: `device.$deviceId.tsx` dispatches IR commands (`ON`, `OFF`, `SET_TEMP` 16â€“30Â°C) to dual units (`AC1`, `AC2`) via `sendDeviceCommand`.
- **Admin Actions**: Setting rooms, pairing devices, configuring thresholds, and uploading floor plans trigger TanStack Query mutations that invalidate relevant query keys.

## Work Guidance

- Add new route `.tsx` in `routes/` â€” TanStack Router plugin regenerates `routeTree.gen.ts` automatically
- Sort/filter state belongs in URL search params (Zod-validated), not component state
- Server state queries & mutations must use TanStack Query hooks and `queryKeys` factory
- `@/*` â†’ `./src/*` for imports
- Always preserve `erasableSyntaxOnly: true` (no TS enums/namespaces) and `verbatimModuleSyntax: true` (`import type`)

## App-Root Tooling Scripts

- `tools/browser_test.mjs` â€” Playwright headless loginâ†’dashboard flow (needs Vite on :5173; dev creds hardcoded) â€” lives in `tools/`, not `dashboard/`
- These are dev conveniences, not part of the build; keep them out of `src/`

## Stack Notes

- `package.json` pins `react@19.2.7`, `typescript@~6.0.2`, `vite@^8.1.1`, `@tanstack/react-query@5.101.2`, `oxlint@1.71`, `vitest@3.2.4`, `@playwright/test@1.62.1`; `npm run lint` = oxlint, `npm run build` = `tsc -b && vite build`
- `constants.ts` is the single source for polling/gap constants â€” do not duplicate `3000`/`2000`/`5` literals in components

## Verification

Rely on root AGENTS.md commands: `npm run lint`, `npm run build` (from gui-app/ directory); `npm run test` (vitest) and `npm run e2e` (playwright, needs Vite :5173)

