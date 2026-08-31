---
type: concept
governed_by: AGENTS.md
links: [wiki/concept-telemetry-pipeline.md, wiki/entity-hubgate-v5.md, wiki/entity-dashboard-spa.md]
sources: [server/schemasv5.py, dashboard/src/lib/chartUtils.ts, dashboard/src/routes/alerts.tsx, server/test_alert_tz.py, commit:acd4f00]
updated: 2026-08-31
---

# Time conventions

Storage is UTC everywhere: server writes `now_utc` (or `_hub_created_at` epoch for WAL replay), the Pi works in epochs, the firmware gets `<T,unixtime>`.

Serialization follows the UtcDateTime contract (schemasv5, 2026-08-31): response-model datetime fields pass through `AfterValidator` that attaches UTC to naive values, so JSON always carries `Z`/`+00:00`. Before this, SQLite's naive datetimes serialized bare (`"2026-08-31T05:41:07"`) and browsers' `new Date()` parsed them as LOCAL time — a double shift that made 05:41 UTC display as "05:41 WIB" instead of "12:41 WIB". The history endpoint had always been correct because it constructs aware datetimes; `chartUtils.parseToDate` additionally appends `Z` client-side as defense-in-depth.

Rendering is `id-ID` + `timeZone: 'Asia/Jakarta'` + `WIB` suffix on every wall clock (chart axes/tooltips, alerts table, device pages, dashboard). Relative ages (`FreshnessBadge`, hub last-seen) are epoch diffs — timezone-free by construction, with an epoch-0 guard so a not-yet-fetched query shows "Awaiting sync" instead of "Updated 56 years ago". APScheduler cron runs in Asia/Jakarta via `CANONICAL_TZ`.
