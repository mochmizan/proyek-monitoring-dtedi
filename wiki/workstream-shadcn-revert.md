---
type: workstream
governed_by: AGENTS.md
links: [wiki/entity-dashboard-spa.md]
sources: [openspec/changes/dashboard-full-shadcn-redesign-2026-08-29/, commit:e14576d, commit:35e0582, commit:3c8c6c5]
updated: 2026-08-31
---

# shadcn redesign attempt and revert

**Status: full redesign reverted (35e0582); targeted perf/a11y polish retained.**

A full 6-phase shadcn migration spec (openspec `dashboard-full-shadcn-redesign-2026-08-29`, e14576d) added chart/field/toggle-group/input-group/empty primitives, but the result regressed the bespoke look; the whole change was reverted in 35e0582 (39 files, chart/empty/field/textarea/toggle-group components removed; the openspec spec itself is retained as documentation).

What survived is the Emil/Vercel audit polish (9b1d8e8..3c8c6c5): explicit transition properties on button/tabs/sheet, 700ms tooltip delay, `prefers-reduced-motion` overrides, staggered list entrance, `content-visibility` rows, single-pass status filtering with memoized derivations, and lazy-loading `TopologyView` (181kB split out of the 363kB index). The lesson baked into dashboard/AGENTS.md: incremental additions yes, full redesign no.
