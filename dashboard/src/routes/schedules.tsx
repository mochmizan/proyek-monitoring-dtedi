import { createFileRoute, redirect } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useState, useMemo } from "react"
import { z } from "zod"
import { Clock, CalendarClock, Plus, Pencil, Trash2, Play, AlertTriangle, CheckCircle, Loader2 } from "lucide-react"
import { queryKeys } from "@/lib/queryKeys"
import { fetchCurrentUser, fetchDevices, fetchSchedules, createSchedule, updateSchedule, deleteSchedule, runNowSchedule } from "@/lib/api"
import { cn } from "@/lib/utils"
import { validateCron, describeCron, getNextRuns, formatNextRun } from "@/lib/cron"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import type { ScheduleResponse, ScheduleCreate } from "@/types/api"

// ------------------------------------------------------------------
// Search validation — filter state lives in URL
// ------------------------------------------------------------------
const schedulesSearchSchema = z.object({
  dev_id: z.string().optional(),
  enabled: z.enum(["all", "true", "false"]).catch("all").optional(),
})

export const Route = createFileRoute("/schedules")({
  validateSearch: (search) => schedulesSearchSchema.parse(search),
  beforeLoad: async ({ context }) => {
    try {
      const user = await context.queryClient.ensureQueryData({
        queryKey: queryKeys.auth.me(),
        queryFn: fetchCurrentUser,
      })
      if (!user) throw redirect({ to: "/login" })
    } catch {
      throw redirect({ to: "/login" })
    }
  },
  component: SchedulesPage,
})

// ------------------------------------------------------------------
// Command presets — canonical bundled warmup bypasses check_genset_mode
// ------------------------------------------------------------------
type PresetKey = "warmup" | "cooldown" | "sgm_on" | "sgm_off" | "reset" | "manual" | "auto" | "custom"

const PRESETS: Record<PresetKey, { label: string; payload: Record<string, unknown> }> = {
  warmup: { label: "Warmup (manual + on) — bundled", payload: { mode: "manual", start_genset: "on" } },
  cooldown: { label: "Cooldown (auto)", payload: { mode: "auto" } },
  sgm_on: { label: "Start Genset (on)", payload: { start_genset: "on" } },
  sgm_off: { label: "Stop Genset (off)", payload: { start_genset: "off" } },
  reset: { label: "Reset (rst)", payload: { reset: "rst" } },
  manual: { label: "Mode manual", payload: { mode: "manual" } },
  auto: { label: "Mode auto", payload: { mode: "auto" } },
  custom: { label: "Custom JSON", payload: {} },
}

function payloadToPreset(payload: Record<string, unknown>): PresetKey {
  const keys = Object.keys(payload)
  if (keys.length === 0) return "custom"
  if (payload.mode === "manual" && payload.start_genset === "on" && keys.length === 2) return "warmup"
  if (payload.mode === "auto" && keys.length === 1) return "auto"
  if (payload.mode === "manual" && keys.length === 1) return "manual"
  if (payload.start_genset === "on" && keys.length === 1) return "sgm_on"
  if (payload.start_genset === "off" && keys.length === 1) return "sgm_off"
  if (payload.reset === "rst" && keys.length === 1) return "reset"
  if (payload.mode === "auto" && Object.keys(payload).length === 1) return "cooldown"
  return "custom"
}

function formatPayloadBadge(payload: Record<string, unknown>): string {
  if (!payload || Object.keys(payload).length === 0) return "—"
  return Object.entries(payload)
    .map(([k, v]) => `${k}:${String(v)}`)
    .join(" · ")
}

// ------------------------------------------------------------------
// Page
// ------------------------------------------------------------------
function SchedulesPage() {
  const queryClient = useQueryClient()
  const { dev_id: filterDevId, enabled: filterEnabled } = Route.useSearch() as { dev_id?: string; enabled?: "all" | "true" | "false" }
  const navigate = Route.useNavigate()

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchCurrentUser,
    staleTime: 60000,
  })
  const role = currentUser?.role ?? "viewer"
  const isAdmin = role === "admin"
  const canWrite = isAdmin
  const canRead = role === "admin" || role === "operator"

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.list("all"),
    queryFn: () => fetchDevices("all"),
  })
  const atsDevices = devices.filter((d) => d.dev_type === "ATS")

  const enabledParam = filterEnabled === "true" ? true : filterEnabled === "false" ? false : undefined

  const { data: schedules = [], isPending, isFetching, error } = useQuery({
    queryKey: queryKeys.schedules.list({ dev_id: filterDevId, enabled: enabledParam }),
    queryFn: () => fetchSchedules({ dev_id: filterDevId || undefined, enabled: enabledParam }),
    enabled: canRead,
  })

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<ScheduleResponse | null>(null)
  const [devId, setDevId] = useState("")
  const [cronExpr, setCronExpr] = useState("0 18 * * 0")
  const [preset, setPreset] = useState<PresetKey>("warmup")
  const [customJson, setCustomJson] = useState('{"mode":"manual","start_genset":"on"}')
  const [enabled, setEnabled] = useState(true)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)

  const cronValidation = useMemo(() => validateCron(cronExpr), [cronExpr])
  const cronHuman = useMemo(() => describeCron(cronExpr), [cronExpr])
  const nextRuns = useMemo(() => (cronValidation.valid ? getNextRuns(cronExpr, 3) : []), [cronExpr, cronValidation.valid])

  const resetForm = () => {
    setEditing(null)
    setDevId("")
    setCronExpr("0 18 * * 0")
    setPreset("warmup")
    setCustomJson('{"mode":"manual","start_genset":"on"}')
    setEnabled(true)
    setFormError(null)
    setFormSuccess(null)
  }

  const openCreate = () => {
    resetForm()
    setDialogOpen(true)
  }

  const openEdit = (s: ScheduleResponse) => {
    setEditing(s)
    setDevId(s.dev_id)
    setCronExpr(s.cron_expr)
    setPreset(payloadToPreset(s.payload))
    setCustomJson(JSON.stringify(s.payload, null, 2))
    setEnabled(s.enabled)
    setFormError(null)
    setFormSuccess(null)
    setDialogOpen(true)
  }

  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })

  const createMut = useMutation({
    mutationFn: (payload: ScheduleCreate) => createSchedule(payload),
    onSuccess: () => {
      setFormSuccess("Schedule created")
      invalidate()
      setTimeout(() => setDialogOpen(false), 600)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<ScheduleCreate> & { enabled?: boolean } }) =>
      updateSchedule(id, payload as never),
    onSuccess: () => {
      setFormSuccess("Schedule updated")
      invalidate()
      setTimeout(() => setDialogOpen(false), 500)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSchedule(id),
    onSuccess: () => invalidate(),
    onError: (e: Error) => alert(e.message),
  })

  const runNowMut = useMutation({
    mutationFn: (id: string) => runNowSchedule(id),
    onSuccess: () => alert("Run-now queued to pending_commands"),
    onError: (e: Error) => alert(e.message),
  })

  const toggleEnabled = (s: ScheduleResponse) => {
    if (!canWrite) return
    updateMut.mutate({ id: s.id, payload: { enabled: !s.enabled } })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setFormSuccess(null)
    if (!devId) {
      setFormError("Select an ATS device")
      return
    }
    if (!cronValidation.valid) {
      setFormError(cronValidation.error || "Invalid cron")
      return
    }
    let payload: Record<string, unknown>
    if (preset === "custom") {
      try {
        payload = JSON.parse(customJson) as Record<string, unknown>
        if (!payload || typeof payload !== "object" || Object.keys(payload).length === 0) {
          setFormError("Custom JSON must be a non-empty object")
          return
        }
      } catch {
        setFormError("Custom JSON invalid — must be valid JSON")
        return
      }
    } else {
      payload = PRESETS[preset]?.payload ?? {}
    }
    // derive hub_id from selected device if known
    const dev = atsDevices.find((d) => d.dev_id === devId)
    const hubId = dev?.hub_id ?? null
    const body: ScheduleCreate = {
      dev_id: devId,
      hub_id: hubId,
      cron_expr: cronExpr.trim(),
      payload,
      tz: "Asia/Jakarta",
      enabled,
    }
    if (editing) {
      updateMut.mutate({ id: editing.id, payload: body as never })
    } else {
      createMut.mutate(body)
    }
  }

  if (!canRead) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <AlertTriangle className="size-8 text-amber-500" />
        <p className="text-sm text-muted-foreground">Operator or Admin role required to view schedules.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-card-foreground flex items-center gap-2 font-serif tracking-tight">
            <CalendarClock className="size-6 text-primary" data-icon="inline-start" />
            ATS Schedules
          </h1>
          <p className="text-xs text-muted-foreground mt-1">VPS-authoritative flexible cron — APScheduler fans out via pending_commands (Asia/Jakarta).</p>
        </div>
        {canWrite && (
          <Button onClick={openCreate}>
            <Plus data-icon="inline-start" />
            New Schedule
          </Button>
        )}
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6 flex flex-wrap gap-4">
          <div className="min-w-[200px]">
              <Label className="mb-1.5 block text-xs uppercase tracking-wider text-muted-foreground">Device filter</Label>
            <Select value={filterDevId ?? "__all"} onValueChange={(v) => navigate({ search: (p) => ({ ...p, dev_id: v === "__all" ? undefined : v }) })}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="All devices" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="__all">All devices</SelectItem>
                  {atsDevices.map((d) => (
                    <SelectItem key={d.dev_id} value={d.dev_id}>
                      {d.dev_name ? `${d.dev_name} (${d.dev_id})` : d.dev_id}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[160px]">
              <Label className="mb-1.5 block text-xs uppercase tracking-wider text-muted-foreground">Enabled</Label>
            <Select value={filterEnabled ?? "all"} onValueChange={(v) => navigate({ search: (p) => ({ ...p, enabled: v as never }) })}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="true">Enabled</SelectItem>
                  <SelectItem value="false">Disabled</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          {isFetching && <span className="self-end text-xs text-muted-foreground flex items-center gap-1"><Loader2 className="size-3 animate-spin" data-icon="inline-start" />Refreshing</span>}
        </CardContent>
      </Card>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs p-3 rounded flex items-center gap-2">
          <AlertTriangle className="size-4" data-icon="inline-start" />
          <span>{(error as Error).message}</span>
        </div>
      )}

      {/* Table */}
      <Card className="overflow-hidden">
        <CardHeader className="border-b">
          <CardTitle className="text-sm uppercase tracking-wider text-muted-foreground">Schedules ({schedules.length})</CardTitle>
          <CardDescription className="text-xs">Cron preview via local parser; next runs in Asia/Jakarta + UTC. Server next_run_at shown when available.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isPending ? (
            <div className="p-8 text-center text-muted-foreground text-sm flex items-center justify-center gap-2"><Loader2 className="size-4 animate-spin" data-icon="inline-start" />Loading schedules…</div>
          ) : schedules.length === 0 ? (
            <div className="p-10 text-center flex flex-col items-center gap-2">
              <Clock className="size-8 text-muted-foreground" data-icon="inline-start" />
              <p className="text-sm text-muted-foreground">No schedules yet</p>
              <p className="text-xs text-muted-foreground max-w-sm">Create a schedule such as weekly warmup <code className="bg-muted px-1 rounded">0 18 * * 0</code> with bundled payload manual+on to bypass the PROMINI guard.</p>
              {canWrite && <Button size="sm" onClick={openCreate} className="mt-2">Create first schedule</Button>}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Device</TableHead>
                    <TableHead>Hub</TableHead>
                    <TableHead>Cron</TableHead>
                    <TableHead>Human</TableHead>
                    <TableHead>Payload</TableHead>
                    <TableHead>Next run</TableHead>
                    <TableHead>Enabled</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {schedules.map((s) => {
                    const human = s.human ?? describeCron(s.cron_expr)
                    const nextLocal = s.next_run_at ? formatNextRun(new Date(s.next_run_at)).jakarta : null
                    return (
                      <TableRow key={s.id}>
                        <TableCell className="font-mono text-xs">{s.dev_id}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{s.hub_id ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs bg-muted rounded px-2 py-1 border inline-block mt-2">{s.cron_expr}</TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[220px] truncate" title={human}>{human}</TableCell>
                        <TableCell><Badge variant="secondary" className="font-mono text-[10px]">{formatPayloadBadge(s.payload)}</Badge></TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {nextLocal ?? (getNextRuns(s.cron_expr, 1)[0] ? formatNextRun(getNextRuns(s.cron_expr, 1)[0] as Date).jakarta : "—")}
                        </TableCell>
                        <TableCell>
                          <Switch checked={s.enabled} onCheckedChange={() => toggleEnabled(s)} disabled={!canWrite} aria-label={`Toggle ${s.dev_id}`} />
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button size="icon" variant="ghost" onClick={() => runNowMut.mutate(s.id)} disabled={!canWrite} title="Run now (queue pending_commands)">
                              <Play data-icon="inline-start" />
                            </Button>
                            <Button size="icon" variant="ghost" onClick={() => openEdit(s)} disabled={!canWrite} title="Edit">
                              <Pencil data-icon="inline-start" />
                            </Button>
                            <Button size="icon" variant="ghost" onClick={() => { if (window.confirm(`Delete schedule #${s.id} ${s.cron_expr}?`)) deleteMut.mutate(s.id) }} disabled={!canWrite} title="Delete" className="text-destructive hover:text-destructive">
                              <Trash2 data-icon="inline-start" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dialog create/edit */}
      <Dialog open={dialogOpen} onOpenChange={(o) => { setDialogOpen(o); if (!o) resetForm() }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit schedule #${editing.id}` : "New ATS schedule"}</DialogTitle>
            <DialogDescription>Flexible cron (5 fields). Timezone canonical Asia/Jakarta. Bundled warmup payload bypasses PROMINI check_genset_mode.</DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {formError && <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs p-3 rounded flex gap-2"><AlertTriangle className="size-4 shrink-0" data-icon="inline-start" /><span>{formError}</span></div>}
            {formSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex gap-2"><CheckCircle className="size-4 shrink-0" data-icon="inline-start" /><span>{formSuccess}</span></div>}

            <div>
              <Label className="mb-1.5 block">ATS Device *</Label>
              <Select value={devId} onValueChange={setDevId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select ATS device" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {atsDevices.length === 0 ? (
                      <SelectItem value="__none" disabled>No ATS devices found — pair one first</SelectItem>
                    ) : (
                      atsDevices.map((d) => (
                        <SelectItem key={d.dev_id} value={d.dev_id}>
                          {d.dev_name ? `${d.dev_name} (${d.dev_id})` : d.dev_id} — hub {d.hub_id ?? "?"}
                        </SelectItem>
                      ))
                    )}
                  </SelectGroup>
                </SelectContent>
              </Select>
              {atsDevices.length === 0 && <p className="text-[11px] text-amber-400 mt-1">No ATS devices. Pair an ATS device in Settings first.</p>}
            </div>

            <div>
              <Label className="mb-1.5 block">Command preset</Label>
              <Select value={preset} onValueChange={(v) => setPreset(v as PresetKey)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {Object.entries(PRESETS).map(([k, v]) => (
                      <SelectItem key={k} value={k}>
                        {v.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground mt-1">Warmup sends <code className="bg-muted px-1 rounded">{"{\"mode\":\"manual\",\"start_genset\":\"on\"}"}</code> via hub 2s poll → MQTT → bounded serial.</p>
            </div>

            {preset === "custom" && (
              <div>
                <Label className="mb-1.5 block">Custom JSON payload</Label>
                <textarea value={customJson} onChange={(e) => setCustomJson(e.target.value)} rows={3} placeholder='{"mode":"manual","start_genset":"on"}' className="w-full bg-muted border rounded-md px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
            )}

            {preset !== "custom" && (
              <div className="bg-muted border rounded p-2.5 text-xs font-mono text-muted-foreground">
                Payload: <span className="text-primary">{JSON.stringify(PRESETS[preset].payload)}</span>
              </div>
            )}

            <div>
              <Label htmlFor="cron" className="mb-1.5 block">Cron expression *</Label>
              <Input id="cron" value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder="0 18 * * 0" className={cn(!cronValidation.valid && "border-red-500 focus-visible:ring-red-500")} />
              {!cronValidation.valid ? (
                <p className="text-xs text-destructive mt-1">{cronValidation.error}</p>
              ) : (
                <p className="text-xs text-emerald-400 mt-1 flex items-center gap-1"><CheckCircle className="size-3" data-icon="inline-start" />{cronHuman}</p>
              )}
              <div className="flex flex-wrap gap-1 mt-2">
                {[
                  ["Sun 18:00 warmup", "0 18 * * 0"],
                  ["Daily 07:00", "0 7 * * *"],
                  ["Mon/Thu 18:00", "0 18 * * 1,4"],
                  ["Every 30m", "*/30 * * * *"],
                ].map(([label, expr]) => (
                  <button key={expr} type="button" onClick={() => setCronExpr(expr)} className={cn("px-2 py-1 rounded border text-[11px] font-mono", cronExpr === expr ? "bg-primary border-primary text-primary-foreground" : "bg-card border text-muted-foreground hover:text-foreground")}>{label}</button>
                ))}
              </div>
            </div>

            {cronValidation.valid && nextRuns.length > 0 && (
              <div className="bg-muted border rounded p-3 flex flex-col gap-1">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Next runs (WIB / UTC)</p>
                {nextRuns.map((d) => {
                  const f = formatNextRun(d)
                  return <div key={d.toISOString()} className="text-xs font-mono text-foreground">{f.jakarta} <span className="text-muted-foreground">· {f.utc}</span></div>
                })}
                <p className="text-[11px] text-muted-foreground">Computed client-side (Jakarta UTC+7). Server next_run_at may differ by seconds.</p>
              </div>
            )}

            <div className="flex items-center justify-between rounded border bg-muted p-3">
              <Label htmlFor="enabled" className="text-sm">Enabled (APScheduler job active)</Label>
              <Switch id="enabled" checked={enabled} onCheckedChange={setEnabled} />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
              <Button type="submit" disabled={createMut.isPending || updateMut.isPending || !cronValidation.valid}>
                {(createMut.isPending || updateMut.isPending) && <Loader2 data-icon="inline-start" className="animate-spin" />}
                {editing ? "Save changes" : "Create schedule"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
