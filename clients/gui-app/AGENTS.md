# AGENTS.md — gui-app

React 19 + TypeScript 6.0 + Vite 8 SPA for IoT smart-building monitoring. **Connected to live HubGate V5 backend via TanStack Query and Same-Origin Vite Proxy.**

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
| `/settings` | `settings.tsx` | `tab` | Rooms CRUD & live unapproved device pairing |
| `/room/$roomId` | `room.$roomId.tsx` | `range` | Room telemetry aggregate & device list |
| `/device/$deviceId` | `device.$deviceId.tsx` | `range` | Time-scaled telemetry chart (TS/AC/ATS) across 6h/24h/7d/30d in Jakarta Time (WIB) & dynamic Command Dispatch (AC IR / ATS) |

## Source Layout

```
src/
├── main.tsx              ← entry: createRoot → <App/>
├── App.tsx               ← TanStack Router + QueryClientProvider setup
├── index.css             ← Tailwind 4 @import + @theme vars (dark)
├── routeTree.gen.ts      ← AUTO-GENERATED — never edit
├── routes/               ← 8 page components (see table above)
├── store/
│   └── appStore.ts       ← minimal Zustand store (sidebarOpen, selectedRoomId)
├── types/
│   └── api.ts            ← TypeScript interfaces matching HubGate V5 Pydantic models
└── lib/
    ├── api.ts            ← centralized Fetch API client with error handling
    ├── queryClient.ts    ← shared QueryClient instance
    ├── queryKeys.ts      ← hierarchical query key factory for caching & invalidation
    ├── mockData.ts       ← fallback mock fixtures for standalone testing
    └── utils.ts          ← cn() = clsx + tailwind-merge
```

## State & Data Flow

- **Live Data Polling**: Dashboard, Room Detail, Device Detail, Map, and Alerts use TanStack Query hooks (`useQuery`) with 3s refetch intervals.
- **History Analytics**: `device.$deviceId.tsx` queries `GET /api/devices/{id}/history?range=6h|24h|7d|30d|all` with time-proportional X-axis scaling, Zod URL parameter synchronization, and Jakarta Time (`Asia/Jakarta` / WIB) display formatting.
- **Air Conditioner Control**: `device.$deviceId.tsx` dispatches IR commands (`ON`, `OFF`, `SET_TEMP` 16–30°C) to dual units (`AC1`, `AC2`) via `sendDeviceCommand`.
- **Admin Actions**: Setting rooms, pairing devices, configuring thresholds, and uploading floor plans trigger TanStack Query mutations that invalidate relevant query keys.

## Work Guidance

- Add new route `.tsx` in `routes/` — TanStack Router plugin regenerates `routeTree.gen.ts` automatically
- Sort/filter state belongs in URL search params (Zod-validated), not component state
- Server state queries & mutations must use TanStack Query hooks and `queryKeys` factory
- `@/*` → `./src/*` for imports
- Always preserve `erasableSyntaxOnly: true` (no TS enums/namespaces) and `verbatimModuleSyntax: true` (`import type`)

## App-Root Tooling Scripts

- `browser_test.mjs` — Playwright headless login→dashboard flow (needs Vite on :5173; dev creds hardcoded)
- `capture_all_ranges.mjs`, `capture_device_graph.mjs` — screenshot capture utilities for device history ranges (output to untracked screenshot dirs)
- These are dev conveniences, not part of the build; keep them out of `src/`

## Verification

Rely on root AGENTS.md commands: `npm run lint`, `npm run build` (from gui-app/ directory)

