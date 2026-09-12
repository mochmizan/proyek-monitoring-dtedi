import React, { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle, Loader2, Search } from "lucide-react"
import { queryKeys } from "@/lib/queryKeys"
import { createSchedule, updateSchedule } from "@/lib/api"
import { validateCron } from "@/lib/cron"
import { cronExprSchema, payloadSchema } from "@/lib/scheduleApi"
import { toast, parseApiError } from "@/lib/toast"
import { cn } from "@/lib/utils"
import CronBuilder from "@/components/schedules/CronBuilder"
import ATSForm from "@/components/schedules/PayloadForm/ATSForm"
import ACForm from "@/components/schedules/PayloadForm/ACForm"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import type { ScheduleResponse, ScheduleCreate, DeviceResponse } from "@/types/api"

// payloadToPreset removed


export interface ScheduleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editing: ScheduleResponse | null
  devices?: DeviceResponse[]
  atsDevices?: DeviceResponse[]
  onSuccess?: () => void
  existingSchedules?: ScheduleResponse[]
}

export default function ScheduleDialog({
  open,
  onOpenChange,
  editing,
  devices,
  atsDevices,
  onSuccess,
  existingSchedules = [],
}: ScheduleDialogProps) {
  const queryClient = useQueryClient()
  const allDevices = useMemo(() => devices ?? atsDevices ?? [], [devices, atsDevices])

  const [devId, setDevId] = useState("")
  const [cronExpr, setCronExpr] = useState("0 18 * * 0")
  const [payload, setPayload] = useState<Record<string, unknown>>({ mode: "manual", start_genset: "on" })
  const [enabled, setEnabled] = useState(true)
  const [formError, setFormError] = useState<string | null>(null)
  const [formSuccess, setFormSuccess] = useState<string | null>(null)
  const [filterTab, setFilterTab] = useState<"all" | "ATS" | "AC" | "ACC">("all")
  const [search, setSearch] = useState("")

  const devIdRef = useRef<HTMLButtonElement>(null)
  const cronRef = useRef<HTMLDivElement>(null)

  const selectedDevice = useMemo(() => allDevices.find((d) => d.dev_id === devId) ?? null, [allDevices, devId])
  const devType = (selectedDevice?.dev_type ?? "ATS").toUpperCase()

  const filteredDevices = useMemo(() => {
    let list = allDevices.filter((d) => d.is_active && d.status === "online" && ["ATS", "AC", "ACC"].includes((d.dev_type ?? "").toUpperCase()))
    if (filterTab !== "all") list = list.filter((d) => (d.dev_type ?? "").toUpperCase() === filterTab)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter((d) => d.dev_id.toLowerCase().includes(q) || (d.dev_name ?? "").toLowerCase().includes(q))
    }
    return list
  }, [allDevices, filterTab, search])

  const onlineATS = useMemo(() => allDevices.filter((d) => d.is_active && d.status === "online" && (d.dev_type ?? "").toUpperCase() === "ATS"), [allDevices])
  const onlineAC = useMemo(() => allDevices.filter((d) => d.is_active && d.status === "online" && (d.dev_type ?? "").toUpperCase() === "AC"), [allDevices])
  const onlineACC = useMemo(() => allDevices.filter((d) => d.is_active && d.status === "online" && (d.dev_type ?? "").toUpperCase() === "ACC"), [allDevices])

  const allDevicesRef = useRef(allDevices)
  allDevicesRef.current = allDevices

  const initializedKeyRef = useRef<string | null>(null)
  const prevDevTypeRef = useRef<string | null>(null)
  const editingId = editing?.id ?? null

  useEffect(() => {
    if (!open) {
      initializedKeyRef.current = null
      prevDevTypeRef.current = null
      return
    }

    const currentKey = editingId ? `edit-${editingId}` : "create"
    if (initializedKeyRef.current === currentKey) {
      return
    }
    initializedKeyRef.current = currentKey

    if (editing) {
      setDevId(editing.dev_id)
      setCronExpr(editing.cron_expr)
      setPayload(editing.payload ?? { mode: "manual", start_genset: "on" })
      setEnabled(editing.enabled)
      const found = allDevicesRef.current.find((d) => d.dev_id === editing.dev_id)
      prevDevTypeRef.current = (found?.dev_type ?? "ATS").toUpperCase()
    } else {
      const first =
        allDevicesRef.current.find((d) => d.is_active && d.status === "online" && ["ATS", "AC", "ACC"].includes((d.dev_type ?? "").toUpperCase())) ??
        allDevicesRef.current.find((d) => d.is_active && d.status === "online") ??
        allDevicesRef.current[0]
      const firstType = (first?.dev_type ?? "ATS").toUpperCase()
      const isFirstAC = firstType === "AC" || firstType === "ACC"
      setDevId(first?.dev_id ?? "")
      setCronExpr("0 18 * * 0")
      setPayload(isFirstAC ? { target: "AC1", action: "ON" } : { mode: "manual", start_genset: "on" })
      setEnabled(true)
      prevDevTypeRef.current = first ? firstType : null
    }
    setFormError(null)
    setFormSuccess(null)
    setSearch("")
    setFilterTab("all")
  }, [open, editingId, editing])

  useEffect(() => {
    if (open && !editing && !devId && allDevices.length > 0) {
      const first =
        allDevices.find((d) => d.is_active && d.status === "online" && ["ATS", "AC", "ACC"].includes((d.dev_type ?? "").toUpperCase())) ??
        allDevices.find((d) => d.is_active && d.status === "online") ??
        allDevices[0]
      if (first?.dev_id) {
        setDevId(first.dev_id)
        const firstType = (first.dev_type ?? "ATS").toUpperCase()
        if (firstType === "AC" || firstType === "ACC") {
          setPayload({ target: "AC1", action: "ON" })
        }
        prevDevTypeRef.current = firstType
      }
    }
  }, [open, editing, devId, allDevices])

  // when device changes, adapt payload shape
  useEffect(() => {
    if (!open || !devId) return
    if (prevDevTypeRef.current === null) {
      prevDevTypeRef.current = devType
      return
    }
    if (prevDevTypeRef.current !== devType) {
      prevDevTypeRef.current = devType
      if (devType === "AC" || devType === "ACC") {
        setPayload({ target: "AC1", action: "ON" })
      } else {
        setPayload({ mode: "manual", start_genset: "on" })
      }
    }
  }, [open, devId, devType])

  const createMut = useMutation({
    mutationFn: (body: ScheduleCreate) => createSchedule(body),
    onSuccess: () => {
      setFormSuccess("Schedule created")
      toast.success("Schedule created")
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })
      onSuccess?.()
      setTimeout(() => onOpenChange(false), 600)
    },
    onError: (e: unknown) => {
      const msg = parseApiError(e)
      setFormError(msg)
      toast.error("Create failed", { description: msg })
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ScheduleCreate> & { enabled?: boolean } }) =>
      updateSchedule(id, body as never),
    onSuccess: () => {
      setFormSuccess("Schedule updated")
      toast.success("Schedule updated")
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules.all })
      onSuccess?.()
      setTimeout(() => onOpenChange(false), 500)
    },
    onError: (e: unknown) => {
      const msg = parseApiError(e)
      setFormError(msg)
      toast.error("Update failed", { description: msg })
    },
  })

  const overlapHint = useMemo(() => {
    if (!devId || !cronExpr) return null
    const dup = existingSchedules.some((s) => s.dev_id === devId && s.cron_expr === cronExpr.trim() && s.id !== editing?.id)
    return dup ? "Same device already has identical cron — both will fire" : null
  }, [existingSchedules, devId, cronExpr, editing])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setFormSuccess(null)
    if (!devId) {
      setFormError("Select a device")
      devIdRef.current?.focus()
      return
    }
    const cronRes = cronExprSchema.safeParse(cronExpr.trim())
    if (!cronRes.success) {
      setFormError(cronRes.error.issues[0]?.message ?? "Invalid cron")
      cronRef.current?.focus()
      return
    }
    const payloadRes = payloadSchema.safeParse(payload)
    if (!payloadRes.success) {
      setFormError(payloadRes.error.issues[0]?.message ?? "Invalid payload")
      return
    }
    const vc = validateCron(cronExpr.trim())
    if (!vc.valid) {
      setFormError(vc.error ?? "Invalid cron")
      return
    }
    const body: ScheduleCreate = {
      dev_id: devId,
      cron_expr: cronExpr.trim(),
      payload: payloadRes.data as Record<string, unknown>,
      tz: "Asia/Jakarta",
      enabled,
    }
    if (editing) updateMut.mutate({ id: editing.id, body: body as never })
    else createMut.mutate(body)
  }

  const isAC = devType === "AC" || devType === "ACC"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{editing ? `Edit schedule #${editing.id.slice(0, 8)}` : "New schedule"}</DialogTitle>
          <DialogDescription>Visual builder generates 5-field cron (Asia/Jakarta). Device payload adapts to ATS vs AC.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {formError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex gap-2"><AlertTriangle className="h-4 w-4 shrink-0" /><span>{formError}</span></div>}
          {formSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex gap-2"><CheckCircle className="h-4 w-4 shrink-0" /><span>{formSuccess}</span></div>}

          <div>
            <Label className="mb-1.5 block">Device *</Label>
            <div className="flex gap-1 mb-2">
              {(["all", "ATS", "AC", "ACC"] as const).map((t) => (
                <Button key={t} type="button" size="sm" variant={filterTab === t ? "default" : "outline"} className={filterTab === t ? "h-7 px-2 text-xs bg-indigo-600" : "h-7 px-2 text-xs"} onClick={() => setFilterTab(t)}>
                  {t === "all" ? "All" : t} {t === "ATS" ? `(${onlineATS.length})` : t === "AC" ? `(${onlineAC.length})` : t === "ACC" ? `(${onlineACC.length})` : `(${onlineATS.length + onlineAC.length + onlineACC.length})`}
                </Button>
              ))}
            </div>
            <div className="relative mb-2">
              <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-zinc-500" />
              <Input placeholder="Search dev_name or dev_id" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-7 h-8 text-xs" />
            </div>
            <Select value={devId} onValueChange={setDevId}>
              <SelectTrigger ref={devIdRef} className={cn("w-full", !devId && "border-red-500")} aria-invalid={!devId}>
                <SelectValue placeholder="Select device (online & active only)" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {filteredDevices.length === 0 ? (
                    <SelectItem value="__none" disabled>
                      {filterTab === "ATS" ? "No online ATS — pair one in Settings" : filterTab === "AC" ? "No online AC — pair one" : "No online devices matching filter"}
                    </SelectItem>
                  ) : (
                    filteredDevices.map((d) => (
                      <SelectItem key={d.dev_id} value={d.dev_id}>
                        {(d.dev_name ? `${d.dev_name} (${d.dev_id})` : d.dev_id)} — {d.dev_type} · {d.hub_id ?? "?"}
                      </SelectItem>
                    ))
                  )}
                </SelectGroup>
              </SelectContent>
            </Select>
            {filteredDevices.length === 0 && <p className="text-[11px] text-amber-400 mt-1">No online devices for this filter. Pair and bring online first.</p>}
            {selectedDevice && <p className="text-[11px] text-zinc-500 mt-1">Selected {selectedDevice.dev_type} · {selectedDevice.status} · {selectedDevice.is_active ? "active" : "pending"}</p>}
          </div>

          <div ref={cronRef}>
            <Label className="mb-1.5 block">Schedule</Label>
            <CronBuilder value={cronExpr} onChange={setCronExpr} />
            {overlapHint && <p className="text-[11px] text-amber-400 mt-1">{overlapHint}</p>}
          </div>

          <div>
            <Label className="mb-1.5 block">Payload *</Label>
            {isAC ? (
              <ACForm value={payload} onChange={setPayload} />
            ) : (
              <ATSForm value={payload} onChange={setPayload} />
            )}
          </div>

          <div className="flex items-center justify-between rounded border border-zinc-800 bg-zinc-950 p-3">
            <Label htmlFor="enabled" className="text-sm">Enabled (APScheduler job active)</Label>
            <Switch id="enabled" checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={createMut.isPending || updateMut.isPending} className="bg-indigo-600 hover:bg-indigo-500">
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
