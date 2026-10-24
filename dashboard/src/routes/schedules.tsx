import React, { useState, Suspense } from "react"
import { createFileRoute } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { z } from "zod"
import { Clock, CalendarClock, Plus, Pencil, Trash2, Play, AlertTriangle, Loader2 } from "lucide-react"
import { queryKeys } from "@/lib/queryKeys"
import { fetchCurrentUser, fetchDevices, fetchSchedules, updateSchedule, deleteSchedule, runNowSchedule } from "@/lib/api"
import { describeCron, formatNextRun } from "@/lib/cron"
import { POLL_TIER2_ALERTS_MS, STALE_TIER2_ALERTS_MS } from "@/lib/constants"
import { getJitteredInterval } from "@/lib/jitter"
import { toast, parseApiError } from "@/lib/toast"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import type { ScheduleResponse, ScheduleCreate } from "@/types/api"

const ScheduleDialog = React.lazy(() => import("@/components/schedules/ScheduleDialog"))

const schedulesSearchSchema = z.object({
  dev_id: z.string().optional(),
  enabled: z.enum(["all", "true", "false"]).catch("all").optional(),
})

export const Route = createFileRoute("/schedules")({
  validateSearch: (search) => schedulesSearchSchema.parse(search),
  component: SchedulesPage,
})

function formatPayloadBadge(payload: Record<string, unknown>): string {
  if (!payload || Object.keys(payload).length === 0) return "—"
  return Object.entries(payload).map(([k, v]) => `${k}:${String(v)}`).join(" · ")
}

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
  const isAdmin = role === "admin" || role === "root" || role === "super_admin"
  const canWrite = isAdmin
  const canRead = isAdmin || role === "operator"

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.list("all"),
    queryFn: () => fetchDevices("all"),
    staleTime: STALE_TIER2_ALERTS_MS,
    refetchInterval: () => getJitteredInterval(POLL_TIER2_ALERTS_MS),
  })
  const schedulableDevices = devices.filter((d) => ["ATS", "AC", "ACC"].includes((d.dev_type ?? "").toUpperCase()))

  const enabledParam = filterEnabled === "true" ? true : filterEnabled === "false" ? false : undefined

  const listKey = queryKeys.schedules.list({ dev_id: filterDevId, enabled: enabledParam })

  const { data: schedules = [], isPending, isFetching, error } = useQuery({
    queryKey: listKey,
    queryFn: () => fetchSchedules({ dev_id: filterDevId || undefined, enabled: enabledParam }),
    enabled: canRead,
    staleTime: STALE_TIER2_ALERTS_MS,
    refetchInterval: () => getJitteredInterval(POLL_TIER2_ALERTS_MS),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: true,
  })

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<ScheduleResponse | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ScheduleResponse | null>(null)

  const openCreate = () => { setEditing(null); setDialogOpen(true) }
  const openEdit = (s: ScheduleResponse) => { setEditing(s); setDialogOpen(true) }

  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<ScheduleCreate> & { enabled?: boolean } }) =>
      updateSchedule(id, payload as never),
    onMutate: async ({ id, payload }) => {
      await queryClient.cancelQueries({ queryKey: listKey })
      const prev = queryClient.getQueryData<ScheduleResponse[]>(listKey)
      queryClient.setQueryData<ScheduleResponse[]>(listKey, (old) =>
        old ? old.map((s) => (s.id === id ? { ...s, ...payload, payload: (payload as Record<string, unknown>).payload ? (payload as unknown as { payload: Record<string, unknown> }).payload as unknown as Record<string, unknown> : s.payload } : s)) : old
      )
      return { prev }
    },
    onError: (e: unknown, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(listKey, ctx.prev)
      toast.error("Update failed", { description: parseApiError(e) })
    },
    onSuccess: () => toast.success("Schedule updated"),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteSchedule(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: listKey })
      const prev = queryClient.getQueryData<ScheduleResponse[]>(listKey)
      queryClient.setQueryData<ScheduleResponse[]>(listKey, (old) => old ? old.filter((s) => s.id !== id) : old)
      return { prev }
    },
    onError: (e: unknown, _id, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(listKey, ctx.prev)
      toast.error("Delete failed", { description: parseApiError(e) })
    },
    onSuccess: () => toast.success("Schedule deleted"),
    onSettled: () => queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all }),
  })

  const runNowMut = useMutation({
    mutationFn: (id: string) => runNowSchedule(id),
    onSuccess: () => {
      toast.success("Queued to pending_commands")
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })
    },
    onError: (e: unknown) => toast.error("Run-now failed", { description: parseApiError(e) }),
  })

  const toggleEnabled = (s: ScheduleResponse) => {
    if (!canWrite) return
    updateMut.mutate({ id: s.id, payload: { enabled: !s.enabled } })
  }

  if (!canRead) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <AlertTriangle className="h-8 w-8 text-amber-500" />
        <p className="text-sm text-zinc-400">Operator or Admin role required to view schedules.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-2">
            <CalendarClock className="h-6 w-6 text-indigo-400" />
            Schedules
          </h1>
          <p className="text-xs text-zinc-500 mt-1">VPS-authoritative flexible cron — APScheduler fans out via pending_commands (Asia/Jakarta).</p>
        </div>
        {canWrite && (
          <Button onClick={openCreate} className="bg-indigo-600 hover:bg-indigo-500">
            <Plus className="h-4 w-4" />
            New Schedule
          </Button>
        )}
      </div>

      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="pt-6 flex flex-wrap gap-4">
          <div className="min-w-[200px]">
            <Label className="mb-1.5 block text-xs uppercase tracking-wider text-zinc-400">Device filter</Label>
            <Select value={filterDevId ?? "__all"} onValueChange={(v) => navigate({ search: (p) => ({ ...p, dev_id: v === "__all" ? undefined : v }) })}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="All devices" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="__all">All devices</SelectItem>
                  {schedulableDevices.map((d) => (
                    <SelectItem key={d.dev_id} value={d.dev_id}>
                      {d.dev_name ? `${d.dev_name} (${d.dev_id})` : d.dev_id} — {d.dev_type}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[160px]">
            <Label className="mb-1.5 block text-xs uppercase tracking-wider text-zinc-400">Enabled</Label>
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
          {isFetching && <span className="self-end text-xs text-zinc-500 flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" />Refreshing</span>}
        </CardContent>
      </Card>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          <span>{(error as Error).message}</span>
        </div>
      )}

      <Card className="bg-zinc-900 border-zinc-800 overflow-hidden">
        <CardHeader className="border-b border-zinc-800">
          <CardTitle className="text-sm uppercase tracking-wider text-zinc-400">Schedules ({schedules.length})</CardTitle>
          <CardDescription className="text-xs">Human from server preview when available; next run in Asia/Jakarta WIB + UTC. Polling every ~6s.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isPending ? (
            <div className="p-8 text-center text-zinc-500 text-sm flex items-center justify-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Loading schedules…</div>
          ) : schedules.length === 0 ? (
            <div className="p-10 text-center flex flex-col items-center gap-2">
              <Clock className="h-8 w-8 text-zinc-600" />
              <p className="text-sm text-zinc-400">No schedules yet</p>
              <p className="text-xs text-zinc-600 max-w-sm">Create a schedule such as weekly warmup <code className="bg-zinc-950 px-1 rounded">0 18 * * 0</code> with bundled payload manual+on.</p>
              {canWrite && <Button size="sm" onClick={openCreate} className="mt-2">Create first schedule</Button>}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
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
                    const nextLocal = s.next_run_at ? formatNextRun(new Date(s.next_run_at)).jakarta : "—"
                    return (
                      <TableRow key={s.id} className="border-zinc-800">
                        <TableCell className="font-mono text-xs text-zinc-200">{s.dev_id}</TableCell>
                        <TableCell className="font-mono text-xs text-zinc-500">{s.hub_id ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs bg-zinc-950 rounded px-2 py-1 border border-zinc-800 inline-block mt-2">{s.cron_expr}</TableCell>
                        <TableCell className="text-xs text-zinc-400 max-w-[220px] truncate" title={human}>{human}</TableCell>
                        <TableCell><Badge variant="secondary" className="font-mono text-[10px]">{formatPayloadBadge(s.payload)}</Badge></TableCell>
                        <TableCell className="text-xs text-zinc-500">{nextLocal}</TableCell>
                        <TableCell>
                          <Switch checked={s.enabled} onCheckedChange={() => toggleEnabled(s)} disabled={!canWrite} aria-label={`Toggle ${s.dev_id}`} />
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button size="icon" variant="ghost" onClick={() => runNowMut.mutate(s.id)} disabled={!canWrite} title="Run now (queue pending_commands)">
                              <Play className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" onClick={() => openEdit(s)} disabled={!canWrite} title="Edit">
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button size="icon" variant="ghost" onClick={() => setDeleteTarget(s)} disabled={!canWrite} title="Delete" className="text-red-400 hover:text-red-300">
                              <Trash2 className="h-3.5 w-3.5" />
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

      {dialogOpen && (
        <Suspense fallback={null}>
          <ScheduleDialog
            open={dialogOpen}
            onOpenChange={setDialogOpen}
            editing={editing}
            devices={devices}
            existingSchedules={schedules}
            onSuccess={invalidate}
          />
        </Suspense>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete schedule?</DialogTitle>
            <DialogDescription>This will remove the APScheduler job and cannot be undone. {deleteTarget ? `${deleteTarget.cron_expr} → ${deleteTarget.dev_id}` : ""}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button className="bg-red-600 hover:bg-red-500" onClick={() => { if (deleteTarget) { deleteMut.mutate(deleteTarget.id); setDeleteTarget(null) } }} disabled={deleteMut.isPending}>
              {deleteMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
