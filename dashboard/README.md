# dashboard — SMSB SPA

React SPA for HubGate V5, same-origin via Vite proxy (`/api` → `127.0.0.1:8000` dev) / Nginx `443` → `127.0.0.1:8000` prod (no CORS).

## Stack

React 19.2.7, Vite 8, TanStack Router 1.170.17, TanStack Query 5.101.2, Zustand 5.0.14, Zod 4.4.3, Tailwind 4.3.2 (`@tailwindcss/vite`), oxlint 1.71.

## Structure

- `src/routes/` — file routes (`routeTree.gen.ts` auto-generated, never edit)
- `src/lib/` — `api.ts`, `queryKeys.ts`, `queryClient.ts`, `scheduleApi.ts`, `constants.ts`, `cron.ts`
- `src/components/` — `ui/*` (shadcn), `device/*`, `schedules/*`, `settings/*`, layout
- `src/hooks/` — `useDeviceHistory`, `useCommandLifecycle`, etc.

## Dev

```powershell
npm --prefix dashboard ci
npm run dev              # Vite :5173, proxy /api → 8000
npm run build            # tsc -b && vite build
npm run lint             # oxlint
npm run test -- --run    # vitest (150 tests, 20 suites)
# from repo root via justfile:
just dev / just lint / just build / just test
```

See root `README.md` for architecture overview and `dashboard/AGENTS.md` for full DOX contracts (polling tiers, layout, pagination, auth).
