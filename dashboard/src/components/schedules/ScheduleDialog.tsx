import React, { useState, useMemo, useEffect } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle, Loader2 } from "lucide-react"
import { queryKeys } from "@/lib/queryKeys"
import { createSchedule, updateSchedule } from "@/lib/api"
import { cn } from "@/lib/utils"
import { validateCron, describeCron, getNextRuns, formatNextRun } from "@/lib/cron"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import type { ScheduleResponse, ScheduleCreate, DeviceResponse } from "@/types/api"

export type PresetKey = "warmup" | "cooldown" | "sgm_on" | "sgm_off" | "reset" | "manual" | "auto" | "custom"

export const PRESETS: Record<PresetKey, { label: string; payload: Record<string, unknown> }> = {
  warmup: { label: "Warmup (manual + on) — bundled", payload: { mode: "manual", start_genset: "on" } },
  cooldown: { label: "Cooldown (auto)", payload: { mode: "auto" } },
  sgm_on: { label: "Start Genset (on)", payload: { start_genset: "on" } },
  sgm_off: { label: "Stop Genset (off)", payload: { start_genset: "off" } },
  reset: { label: "Reset (rst)", payload: { reset: "rst" } },
  manual: { label: "Mode manual", payload: { mode: "manual" } },
  auto: { label: "Mode auto", payload: { mode: "auto" } },
  custom: { label: "Custom JSON", payload: {} },
}

export function payloadToPreset(payload: Record<string, unknown>): PresetKey {
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

export interface ScheduleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editing: ScheduleResponse | null
  atsDevices?: DeviceResponse[]
  onSuccess?: () => void
}

export default function ScheduleDialog({
  open,
  onOpenChange,
  editing,
  atsDevices = [],
  onSuccess,
}: ScheduleDialogProps) {
  const queryClient = useQueryClient()

  const [devId, setDevId] = useState("")
  const [cronExpr, setCronExpr] = useState("0 18 * * 0")
  const [preset, setPreset] = useState<PresetKey>("warmup")
  const [customJson, setCustomJson] = useState('{"mode":"manual","start_genset":"on"}')
  const [enabled, setEnabled] = useState(true)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      if (editing) {
        setDevId(editing.dev_id)
        setCronExpr(editing.cron_expr)
        setPreset(payloadToPreset(editing.payload))
        setCustomJson(JSON.stringify(editing.payload, null, 2))
        setEnabled(editing.enabled)
      } else {
        setDevId(atsDevices[0]?.dev_id ?? "")
        setCronExpr("0 18 * * 0")
        setPreset("warmup")
        setCustomJson('{"mode":"manual","start_genset":"on"}')
        setEnabled(true)
      }
      setFormError(null)
      setFormSuccess(null)
    }
  }, [open, editing, atsDevices])

  const cronValidation = useMemo(() => validateCron(cronExpr), [cronExpr])
  const cronHuman = useMemo(() => describeCron(cronExpr), [cronExpr])
  const nextRuns = useMemo(() => (cronValidation.valid ? getNextRuns(cronExpr, 3) : []), [cronExpr, cronValidation.valid])

  const createMut = useMutation({
    mutationFn: (payload: ScheduleCreate) => createSchedule(payload),
    onSuccess: () => {
      setFormSuccess("Schedule created")
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })
      onSuccess?.()
      setTimeout(() => onOpenChange(false), 600)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<ScheduleCreate> & { enabled?: boolean } }) =>
      updateSchedule(id, payload as never),
    onSuccess: () => {
      setFormSuccess("Schedule updated")
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })
      onSuccess?.()
      setTimeout(() => onOpenChange(false), 500)
    },
    onError: (e: Error) => setFormError(e.message),
  })

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{editing ? `Edit schedule #${editing.id}` : "New ATS schedule"}</DialogTitle>
          <DialogDescription>Flexible cron (5 fields). Timezone canonical Asia/Jakarta. Bundled warmup payload bypasses PROMINI check_genset_mode.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {formError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex gap-2"><AlertTriangle className="h-4 w-4 shrink-0" /><span>{formError}</span></div>}
          {formSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex gap-2"><CheckCircle className="h-4 w-4 shrink-0" /><span>{formSuccess}</span></div>}

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
            <p className="text-[11px] text-zinc-500 mt-1">Warmup sends <code className="bg-zinc-950 px-1 rounded">{"{\"mode\":\"manual\",\"start_genset\":\"on\"}"}</code> via hub 2s poll → MQTT → bounded serial.</p>
          </div>

          {preset === "custom" && (
            <div>
              <Label className="mb-1.5 block">Custom JSON payload</Label>
              <textarea value={customJson} onChange={(e) => setCustomJson(e.target.value)} rows={3} placeholder='{"mode":"manual","start_genset":"on"}' className="w-full bg-zinc-950 border border-border rounded-md px-3 py-2 text-xs font-mono text-zinc-200 focus:outline-none focus:ring-2 focus:ring-ring" />
            </div>
          )}

          {preset !== "custom" && (
            <div className="bg-zinc-950 border border-zinc-800 rounded p-2.5 text-xs font-mono text-zinc-400">
              Payload: <span className="text-indigo-300">{JSON.stringify(PRESETS[preset].payload)}</span>
            </div>
          )}

          <div>
            <Label htmlFor="cron" className="mb-1.5 block">Cron expression *</Label>
            <Input id="cron" value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder="0 18 * * 0" className={cn(!cronValidation.valid && "border-red-500 focus-visible:ring-red-500")} />
            {!cronValidation.valid ? (
              <p className="text-xs text-red-400 mt-1">{cronValidation.error}</p>
            ) : (
              <p className="text-xs text-emerald-400 mt-1 flex items-center gap-1"><CheckCircle className="h-3 w-3" />{cronHuman}</p>
            )}
            <div className="flex flex-wrap gap-1 mt-2">
              {[
                ["Sun 18:00 warmup", "0 18 * * 0"],
                ["Daily 07:00", "0 7 * * *"],
                ["Mon/Thu 18:00", "0 18 * * 1,4"],
                ["Every 30m", "*/30 * * * *"],
              ].map(([label, expr]) => (
                <button key={expr} type="button" onClick={() => setCronExpr(expr)} className={cn("px-2 py-1 rounded border text-[11px] font-mono", cronExpr === expr ? "bg-indigo-600 border-indigo-500 text-white" : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200")}>{label}</button>
              ))}
            </div>
          </div>

          {cronValidation.valid && nextRuns.length > 0 && (
            <div className="bg-zinc-950 border border-zinc-800 rounded p-3 space-y-1">
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Next runs (WIB / UTC)</p>
              {nextRuns.map((d) => {
                const f = formatNextRun(d)
                return <div key={d.toISOString()} className="text-xs font-mono text-zinc-300">{f.jakarta} <span className="text-zinc-500">· {f.utc}</span></div>
              })}
              <p className="text-[11px] text-zinc-500">Computed client-side (Jakarta UTC+7). Server next_run_at may differ by seconds.</p>
            </div>
          )}

          <div className="flex items-center justify-between rounded border border-zinc-800 bg-zinc-950 p-3">
            <Label htmlFor="enabled" className="text-sm">Enabled (APScheduler job active)</Label>
            <Switch id="enabled" checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={createMut.isPending || updateMut.isPending || !cronValidation.valid} className="bg-indigo-600 hover:bg-indigo-500">
              {(createMut.isPending || updateMut.isPending) && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {editing ? "Save changes" : "Create schedule"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export { ScheduleDialog }
