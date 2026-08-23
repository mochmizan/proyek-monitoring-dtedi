## Context

Three prior changes shipped: backend hardening + ATS command relay, auth/RBAC, and field firmware alignment. The frontend mockup (Vite + React + TanStack Router + Zustand) still runs entirely on simulated data per the original master handoff doc. HubBrain forwards telemetry via a single HTTPS POST per reading with no retry/buffering. `event_log` exists in the schema but has never been written to. This change closes all of that in one consolidated pass, per explicit request to combine remaining work into a single change rather than three sequential ones.

## Goals / Non-Goals

**Goals:** reach feature parity with the original mockup's navigation (Dashboard, Map, Alerts, Settings) against real data; make the edge daemon resilient to WAN outages; get a working production deployment.

**Non-Goals:** Telegram alert push (optional in original scope, deferred), Grafana/analytics, multi-VPS HA, AC/IR command relay beyond generalizing the topic-dispatch bug (AC's full command surface mirrors ATS's existing pattern and isn't being redesigned here).

## Decisions

**Same-origin frontend/API serving is mandatory, not a style choice.** Browsers do not attach `SameSite=Lax` cookies to cross-origin `fetch`/XHR requests — only to top-level same-site navigations. Since the session cookie from the auth change is `SameSite=Lax` (chosen deliberately over `None` to keep CSRF protection), a frontend served from a different origin than the API would silently fail to authenticate on every background request, even though a manual page navigation might appear to work. Serving both through the same Nginx origin sidesteps this category of bug entirely rather than requiring `SameSite=None; Secure` plus exact-origin CORS with credentials on every request — the latter is more moving parts for a project already running on one VPS.

**Floor plan images on local disk, not object storage.** Consistent with the project's running theme: one campus VPS, no new infrastructure for a 4-room deployment. Nginx already serves static assets; a room's floor plan is one small image file.

**Threshold evaluation runs synchronously inside the ingest request handler, not a separate worker.** At this telemetry volume (a handful of rooms, low frequency), adding a background worker/queue to do what a few comparisons and a conditional insert can do inline is unjustified complexity — same reasoning that ruled out TimescaleDB/Redis earlier in this project.

**Debounce and hysteresis are evaluated per (device, condition) pair, tracked via the alert log's own open/resolved state** — an alert is "open" if the most recent row for that device/condition has no `resolved_at`; a new breach within the debounce window is suppressed by checking the most recent alert's timestamp for that device/condition before inserting.

**Edge offline cache uses SQLite WAL mode**, matching the original brainstorm research and general practice for a single-writer embedded cache that must survive a power cut without corruption; paced replay (small delay between records) avoids a reconnect flooding HubGate with a large backlog burst.

**Command dispatch topic resolution**: HubBrain looks up the target device's `dev_type` (already available from its whitelist sync data) and builds the topic as `{HUB_NAME}/{dev_type_lowercase}/command`, replacing the single hardcoded ATS-specific topic string. This generalizes to AC and any future type without new per-type code.

**Sensor NaN handling**: skip publishing that telemetry cycle entirely when a read fails, rather than substitute a sentinel value. A missing data point is an honest gap (visible as a stale "last seen" timestamp on the dashboard); a fabricated zero reading is not.

**Local test stack uses Docker Compose with official Postgres and Eclipse Mosquitto images**, not a shared dev server or SQLite substitute — the goal is parity with production's actual database engine and broker auth posture (`allow_anonymous false`), so bugs specific to Postgres or to authenticated MQTT are caught locally instead of first appearing on the VPS or the physical Pi. Mock publishers are plain Python scripts using `paho-mqtt`, reusing the same payload-shape logic as the real schemas, rather than a bespoke simulator — kept intentionally simple since their only job is to produce valid `TSData`/`ATSData`/`ACData` JSON on demand.

**Pi backup is a deployment gate, not just a one-time recommendation.** Framing it as a requirement in `production-deployment` (rather than a one-off task that gets done once and forgotten) means every future change that touches the physical Pi — not just this one — has to pass through the same check, since this is the second time in this project a Pi backup was recommended and its completion was never actually confirmed.

**ATS serial protocol: the hardware team's direct communication wins over a generated report.** Two accounts of the Wemos-Arduino serial format existed: the teammate's original WhatsApp spec, and a later "verification" report's differing table. The report is disqualified as an independent source of truth here — its AC/IR firmware section was separately confirmed to be entirely fabricated, and its own ATS table is internally inconsistent (mixing `<M,auto>`, which matches the teammate's format, with `<C,SGM_ON>`, which doesn't) — the signature of a document partly grounded in real code and partly pattern-filled. Rather than trusting either account blindly, the spec designates the teammate's format canonical and makes direct code inspection (not report-reading) a hard requirement before this is considered resolved.

## Risks / Trade-offs

- **[Risk]** Same-origin serving means a frontend redeploy and a backend redeploy are more coupled operationally (both go through the same Nginx/VPS flow) than fully independent deployments would be. **Accepted**: appropriate at this project's scale; independent deploy pipelines are overhead this doesn't need.
- **[Risk]** Synchronous threshold evaluation adds a small amount of latency to the telemetry ingest request. **Mitigation**: the evaluation is a handful of comparisons against already-fetched device config, not a heavy computation; negligible at this data rate.
- **[Trade-off]** Consolidating six capabilities into one change is a larger single unit to review/test than three smaller ones would have been — explicitly accepted per request; tasks.md orders work so rooms/pairing lands before anything that depends on it (map, frontend), keeping the sequence sane even within one change.

## Migration Plan

1. Database: add `rooms`, `device_threshold_config`, `floor_plan_markers` (or equivalent columns), ensure `event_log` matches the alert schema needed; run via the existing additive-migration pattern.
2. Backend: rooms/pairing/map/alerts endpoints; synchronous threshold evaluation wired into the existing ingest path.
3. Firmware: NaN skip-publish fix on temperature/AC nodes (small, independent of the rest).
4. HubBrain: SQLite offline cache + paced replay; generalized command-topic resolution.
5. Frontend: replace Zustand simulation with TanStack Query against the now-complete backend; wire login/route guards to real auth.
6. **Gate**: verify a Raspberry Pi backup exists before step 7.
7. **Gate**: run the full pipeline against the local Docker test stack (mock publishers → local HubBrain → local HubGate → local Postgres → frontend) and confirm it passes before step 8.
8. Deployment: Nginx same-origin config, real `.env`, run migrations, cut over — VPS first, physical Pi update last (per the backup gate above).

Rollback: each layer (DB, backend, firmware, edge, frontend, deploy config) can be reverted independently via version control; the additive-migration pattern means a backend rollback doesn't require reversing the schema changes unless a specific migration is also rolled back deliberately.
