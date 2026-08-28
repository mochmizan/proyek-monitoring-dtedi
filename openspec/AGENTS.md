# AGENTS.md — openspec

## Purpose

Spec-driven change proposals: why/what, capability specs (SHALL + WHEN/THEN), design decisions, tasks, and impact per change under `changes/<name>/`.

## Ownership

- **openspec/** owns change proposals and capability specs
- Owned by root AGENTS.md and the DOX framework; proposals are planning artifacts that may reference `server/`, `hub/`, `dashboard/`, `firmware/`

## Local Contracts

```
changes/<change-name>/
├── .openspec.yaml          # schema: spec-driven, created date
├── proposal.md             # Why / What Changes / Capabilities / Impact
├── design.md               # Context, Goals/Non-Goals, Decisions, Risks, Migration
├── tasks.md                # Checkbox tasks (verification included)
└── specs/<capability>/
    └── spec.md             # Requirements: SHALL + WHEN/THEN scenarios
```

- `changes/` pruned 2026-08-27 (`8f1e12e`) — prior proposals IMPLEMENTED & VERIFIED, archived in git (`git log --all -- openspec/changes/` / `git show 8f1e12e^:openspec/changes/`); specs retained in `docs/`; active: `changes/ats-flexible-schedule-2026-08-29/` (VPS `schedules` + dashboard `schedules`)

## Work Guidance

- Follow lifecycle: propose → design → spec → tasks → implement → verify
- Keep requirements in SHALL + WHEN/THEN scenario format; implementation must satisfy every scenario
- Update `.openspec.yaml` `created` date and relevant `spec.md` only as part of a change
- Cross-reference hardware work to actual sketches under `firmware/` (folder name must match `.ino`)
- Respect out-of-scope boundaries recorded in proposal/design (`hostapd`/`dnsmasq`, OverlayFS, `fsm_w_serial.ino` itself) unless superseded

## Verification

- Requirements verifiable via `spec.md` scenarios; `tasks.md` §5 lists bench tests
- Backend regression: `pytest` at root; no build tooling in `openspec/` itself — verify against component suites and hardware bench tests

## Child DOX Index

| Path | Scope |
|---|---|
| — | none |
