import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { queryKeys } from "@/lib/queryKeys"
import { previewScheduleCron } from "@/lib/api"
import { validateCron, describeCron, buildCron, parseCronToBuilderState, formatNextRun } from "@/lib/cron"
import type { CronFrequency } from "@/lib/cron"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { CheckCircle, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react"

const WEEKDAYS = [
  { label: "Mon", value: 1 },
  { label: "Tue", value: 2 },
  { label: "Wed", value: 3 },
  { label: "Thu", value: 4 },
  { label: "Fri", value: 5 },
  { label: "Sat", value: 6 },
  { label: "Sun", value: 0 },
]

export interface CronBuilderProps {
  value: string
  onChange: (cron: string) => void
  disabled?: boolean
}

export default function CronBuilder({ value, onChange, disabled }: CronBuilderProps) {
  const initial = parseCronToBuilderState(value)
  const [frequency, setFrequency] = useState<CronFrequency>(initial.frequency)
  const [time, setTime] = useState(initial.time)
  const [weekdays, setWeekdays] = useState<number[]>(initial.weekdays)
  const [raw, setRaw] = useState(initial.raw)
  const [showRaw, setShowRaw] = useState(initial.frequency === "custom")

  // sync when external value changes (edit mode)
  useEffect(() => {
    const s = parseCronToBuilderState(value)
    setFrequency(s.frequency)
    setTime(s.time)
    setWeekdays(s.weekdays)
    setRaw(s.raw)
    setShowRaw(s.frequency === "custom")
  }, [value])

  const emit = (freq: CronFrequency, t: string, wd: number[], r: string) => {
    const cron = buildCron({ frequency: freq, time: t, weekdays: wd, raw: r })
    onChange(cron)
  }

  const handleFreq = (v: CronFrequency) => {
    setFrequency(v)
    if (v === "weekdays") {
      const wd = [1, 2, 3, 4, 5]
      setWeekdays(wd)
      setShowRaw(false)
      emit(v, time, wd, raw)
    } else if (v === "daily") {
      setShowRaw(false)
      emit(v, time, [], raw)
    } else if (v === "weekly") {
      const wd = weekdays.length ? weekdays : [0]
      setWeekdays(wd)
      setShowRaw(false)
      emit(v, time, wd, raw)
    } else {
      setShowRaw(true)
      emit(v, time, weekdays, raw)
    }
  }

  const handleTime = (v: string) => {
    setTime(v)
    if (frequency !== "custom") emit(frequency, v, weekdays, raw)
  }

  const toggleWeekday = (d: number) => {
    let next: number[]
    if (weekdays.includes(d)) next = weekdays.filter((x) => x !== d)
    else next = [...weekdays, d].sort((a, b) => a - b)
    if (frequency === "daily" || frequency === "weekdays") return
    setWeekdays(next)
    emit(frequency, time, next, raw)
  }

  const handleRaw = (v: string) => {
    setRaw(v)
    onChange(v)
  }

  const cronForPreview = frequency === "custom" ? raw : value
  const isValid = validateCron(cronForPreview).valid
  const validation = validateCron(cronForPreview)

  const { data: preview } = useQuery({
    queryKey: queryKeys.schedules.preview(cronForPreview, "Asia/Jakarta"),
    queryFn: () => previewScheduleCron(cronForPreview, "Asia/Jakarta"),
    enabled: isValid && !!cronForPreview,
    staleTime: 30000,
    gcTime: 60000,
  })

  const human = preview?.human ?? (isValid ? describeCron(cronForPreview) : null)
  const nextRuns = preview?.next_runs ?? null

  return (
    <div className="space-y-3 rounded border border-zinc-800 bg-zinc-950 p-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="mb-1.5 block text-xs uppercase tracking-wider text-zinc-400">Frequency</Label>
          <Select value={frequency} onValueChange={(v) => handleFreq(v as CronFrequency)} disabled={disabled}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="daily">Daily</SelectItem>
                <SelectItem value="weekdays">Weekdays (Mon-Fri)</SelectItem>
                <SelectItem value="weekly">Weekly</SelectItem>
                <SelectItem value="custom">Custom</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="mb-1.5 block text-xs uppercase tracking-wider text-zinc-400">Time (WIB 24h)</Label>
          <Input type="time" value={time} onChange={(e) => handleTime(e.target.value)} disabled={disabled || frequency === "custom"} step={60} />
        </div>
      </div>

      {frequency === "weekly" && (
        <div>
          <Label className="mb-1.5 block text-xs uppercase tracking-wider text-zinc-400">Weekdays</Label>
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAYS.map((d) => {
              const active = weekdays.includes(d.value)
              return (
                <Button key={d.value} type="button" size="sm" variant={active ? "default" : "outline"} className={active ? "bg-indigo-600 hover:bg-indigo-500 h-7 px-2.5 text-xs" : "h-7 px-2.5 text-xs"} onClick={() => toggleWeekday(d.value)} disabled={disabled}>
                  {d.label}
                </Button>
              )
            })}
          </div>
        </div>
      )}
      {frequency === "weekdays" && (
        <p className="text-[11px] text-zinc-500">Monday through Friday at {time} WIB</p>
      )}

      <div>
        <button type="button" onClick={() => setShowRaw((v) => !v)} className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300">
          {showRaw ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />} Raw cron (advanced)
        </button>
        {showRaw && (
          <div className="mt-2">
            <Input value={raw} onChange={(e) => handleRaw(e.target.value)} placeholder="0 18 * * 0" disabled={disabled} className={validation.valid ? "" : "border-red-500"} />
            {!validation.valid && <p className="text-xs text-red-400 mt-1">{validation.error}</p>}
            <p className="text-[11px] text-zinc-500 mt-1">5 fields: minute hour dom month dow — e.g. <code className="bg-zinc-900 px-1 rounded">0 7 * * *</code></p>
          </div>
        )}
      </div>

      <div className="rounded bg-zinc-900 border border-zinc-800 p-2.5 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-zinc-300">{cronForPreview}</span>
          {isValid ? <CheckCircle className="h-3 w-3 text-emerald-500" /> : <AlertTriangle className="h-3 w-3 text-amber-500" />}
          <span className="text-[11px] text-zinc-500 ml-auto">Asia/Jakarta</span>
        </div>
        {isValid && human && <p className="text-xs text-emerald-400">{human}</p>}
        {isValid && nextRuns && nextRuns.length > 0 && (
          <div className="space-y-0.5">
            {nextRuns.slice(0, 3).map((d) => {
              const dt = new Date(d)
              const f = formatNextRun(dt)
              return <div key={d} className="text-[11px] font-mono text-zinc-400">{f.jakarta} <span className="text-zinc-600">· {f.utc}</span></div>
            })}
          </div>
        )}
        {isValid && !preview && nextRuns === null && <p className="text-[11px] text-zinc-500">Loading preview…</p>}
        {!isValid && <p className="text-xs text-red-400">{validation.error}</p>}
      </div>
    </div>
  )
}
