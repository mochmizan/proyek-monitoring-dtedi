# Spec: dashboard-scheduling

## Purpose

Dashboard scheduling UI for flexible ATS cron via shadcn primitives, leveraging `cron-parser` + `cronstrue`.

## ADDED Requirements

### Requirement: Scheduling view lists schedules with human preview
The system SHALL provide a Scheduling route that lists all schedules in a `Table` with device, hub, `cron_expr`, human-readable preview, payload badge, enabled state, and next-run time.

#### Scenario: Admin views schedules
- **WHEN** an admin navigates to the Scheduling route
- **THEN** the system fetches `GET /api/schedules` via TanStack Query and renders a `Table` with columns dev/hub/cron/human/enabled/next_run

#### Scenario: Human preview rendered
- **WHEN** a schedule has `cron_expr = "0 18 * * 0"`
- **THEN** the UI shows `cronstrue` output "At 6:00 PM, only on Sunday" alongside the raw cron

### Requirement: Create/edit schedule via Dialog with command Select
The system SHALL provide a `Dialog` form to create and edit schedules, with a `Select` for command presets and a cron `Input` with live validation/preview.

#### Scenario: Create warmup schedule
- **WHEN** an admin opens Create, picks hub/dev via `Select`, picks preset "Warmup (manual+on)" via command `Select`, enters `0 18 * * 0` and saves
- **THEN** the system calls `POST /api/schedules` with `payload={"mode":"manual","start_genset":"on"}` and invalidates the schedules query

#### Scenario: Cron validation feedback
- **WHEN** a user types an invalid cron `* * *` in the `Input`
- **THEN** the form shows a validation error from `cron-parser` and disables Save, showing no `cronstrue` preview

### Requirement: Enable/disable toggle
The system SHALL provide an enabled `Switch` per schedule row that toggles without opening the Dialog.

#### Scenario: Disable schedule
- **WHEN** an admin toggles the `Switch` off for an enabled schedule
- **THEN** the system calls `PATCH /api/schedules/{id}` with `{"enabled": false}` and the row reflects disabled state

### Requirement: Cron builder helpers (Popover + Calendar)
The system SHALL offer shadcn `Popover` + `Calendar` (react-day-picker) helpers to preview next runs for the entered cron in `Asia/Jakarta`.

#### Scenario: Preview next runs
- **WHEN** a valid cron is entered
- **THEN** the UI shows the next 3 fire times (local Jakarta + UTC) computed via the preview endpoint or local `cron-parser`, rendered in a `Popover` anchored to the cron input

#### Scenario: RBAC guard on UI
- **WHEN** an `operator` visits the Scheduling route
- **THEN** the create/edit/toggle controls are disabled or hidden and any write attempt is rejected with 403 via `QueryCache.onError`

### Requirement: shadcn + Tailwind 4 integration
The system SHALL use shadcn primitives (`Dialog`, `Select`, `Calendar`, `Popover`, `Table`, `Switch`, `Badge`, `Button`, `Input`, `Label`) with Tailwind 4 via `@tailwindcss/vite`, preserving `cn()` = `clsx + tailwind-merge` and dark `background:#09090b`.

#### Scenario: Build passes with shadcn
- **WHEN** `npm run build` (`tsc -b && vite build`) runs after shadcn init
- **THEN** the build succeeds, bundle grows by ~40-60 kB gzipped, and existing routes still render correctly

