# AGENTS.md — gui-app

React 19.2.7 + TypeScript ~6.0.2 + Vite ^8.1.1 SPA for IoT smart-building monitoring (TanStack Query 5.101.2, oxlint 1.71). **Connected to live HubGate V5 backend via TanStack Query and Same-Origin Vite Proxy.**

## Ownership

- **gui-app/**: SPA source code — routes, TanStack Query hooks, Zustand UI store, build tooling
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
| `/map` | `map.tsx` | — | Interactive floor plan markers |
| `/hubs` | `hubs.tsx` | — | Edge hub presence grid: live online/offline cards, device roster per hub, admin approve/revoke actions |
| `/settings` | `settings.tsx` | `tab` | Rooms CRUD & live unapproved device pairing |
| `/room/$roomId` | `room.$roomId.tsx` | `range` | Room telemetry aggregate & device list |
| `/device/$deviceId` | `device.$deviceId.tsx` | `range` | Time-scaled telemetry chart (TS/AC/ATS) across 6h/24h/7d/30d in Jakarta Time (WIB) & dynamic Command Dispatch (AC IR / ATS) |

## Source Layout

```
src/
├── main.tsx              ← entry: createRoot → <App/> wrapped in ErrorBoundary
├── App.tsx               ← TanStack Router + QueryClientProvider setup
├── index.css             ← Tailwind 4 @import + @theme vars (dark)
├── routeTree.gen.ts      ← AUTO-GENERATED — never edit
├── components/
│   ├── ErrorBoundary.tsx ← class ErrorBoundary (catches render crashes; used at App root)
│   ├── RoomCard.tsx, StatusDot.tsx, FreshnessBadge.tsx, Sparkline.tsx, TopologyView.tsx
│   ├── device/           ← Controls.tsx, HistoryChart.tsx (split from device.$deviceId.tsx)
│   └── settings/         ← RoomsTab.tsx, DevicesTab.tsx, HubsTab.tsx (split from settings.tsx)
├── hooks/
│   └── useDeviceHistory.ts ← history query hook (wraps api + gap-aware chart logic)
├── routes/               ← 9 page components (see table above)
├── store/
│   └── appStore.ts       ← minimal Zustand store (sidebarOpen, selectedRoomId)
├── types/
│   └── api.ts            ← TypeScript interfaces matching HubGate V5 Pydantic models
├── __tests__/            ← vitest unit tests (jsdom, setup.ts)
├── e2e/                  ← playwright e2e tests (playwright.config.ts, webServer: vite :5173)
└── lib/
    ├── api.ts            ← centralized Fetch API client with error handling
    ├── queryClient.ts    ← shared QueryClient instance
    ├── queryKeys.ts      ← hierarchical query key factory for caching & invalidation
    ├── constants.ts      ← POLL_MS=3000, STALE_MS=2000, GAP_FLOOR_MIN=5 (single source of polling/gap constants)
    ├── chartUtils.ts     ← gap detection + offline shading helpers (used by HistoryChart)
    └── utils.ts          ← cn() = clsx + tailwind-merge
```

## State & Data Flow

- **Live Data Polling**: Dashboard, Room Detail, Device Detail, Map, and Alerts use TanStack Query hooks (`useQuery`) with 3s refetch intervals.
- **History Analytics**: `device.$deviceId.tsx` queries `GET /api/devices/{id}/history?range=6h|24h|7d|30d|all` with time-proportional X-axis scaling, Zod URL parameter synchronization, and Jakarta Time (`Asia/Jakarta` / WIB) display formatting. Chart is gap-aware: `GAP_FLOOR 5 min` + `10×median interval` threshold breaks lines (`M` vs `L`), shades offline spans (including leading window-start→first-point gap), renders isolated-point dots, and per-segment area fill (Grafana/uPlot pattern).
- **Air Conditioner Control**: `device.$deviceId.tsx` dispatches IR commands (`ON`, `OFF`, `SET_TEMP` 16–30°C) to dual units (`AC1`, `AC2`) via `sendDeviceCommand`.
- **Admin Actions**: Setting rooms, pairing devices, configuring thresholds, and uploading floor plans trigger TanStack Query mutations that invalidate relevant query keys.

## Work Guidance

- Add new route `.tsx` in `routes/` — TanStack Router plugin regenerates `routeTree.gen.ts` automatically
- Sort/filter state belongs in URL search params (Zod-validated), not component state
- Server state queries & mutations must use TanStack Query hooks and `queryKeys` factory
- `@/*` → `./src/*` for imports
- Always preserve `erasableSyntaxOnly: true` (no TS enums/namespaces) and `verbatimModuleSyntax: true` (`import type`)

## App-Root Tooling Scripts

- `tools/browser_test.mjs` — Playwright headless login→dashboard flow (needs Vite on :5173; dev creds hardcoded) — lives in `tools/`, not `clients/gui-app/`
- These are dev conveniences, not part of the build; keep them out of `src/`

## Stack Notes

- `package.json` pins `react@19.2.7`, `typescript@~6.0.2`, `vite@^8.1.1`, `@tanstack/react-query@5.101.2`, `oxlint@1.71`, `vitest@3.2.4`, `@playwright/test@1.62.1`; `npm run lint` = oxlint, `npm run build` = `tsc -b && vite build`
- `constants.ts` is the single source for polling/gap constants — do not duplicate `3000`/`2000`/`5` literals in components

## Verification

Rely on root AGENTS.md commands: `npm run lint`, `npm run build` (from gui-app/ directory); `npm run test` (vitest) and `npm run e2e` (playwright, needs Vite :5173)

