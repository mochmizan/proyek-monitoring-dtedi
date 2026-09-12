/**
 * Lightweight cron helpers — avoids external cron-parser/cronstrue deps.
 * 5-field standard cron (minute hour dom month dow), Asia/Jakarta canonical.
 * Server GET /api/schedules/preview is source of truth for next_runs;
 * client helpers are for inline validation + optimistic preview fallback.
 */

const CRON_FIELD_REGEX = /^[\d*,/\-\s]+$/

export type CronFrequency = "daily" | "weekdays" | "weekly" | "custom"

export interface BuilderState {
  frequency: CronFrequency
  time: string
  weekdays: number[]
  raw: string
}

export function buildCron(args: { frequency: CronFrequency; time: string; weekdays: number[]; raw?: string }): string {
  if (args.frequency === "custom") {
    return (args.raw ?? "").trim() || "0 18 * * 0"
  }
  const parts = (args.time || "18:00").split(":")
  const h = parseInt(parts[0] ?? "18", 10)
  const m = parseInt(parts[1] ?? "0", 10)
  const hh = Number.isFinite(h) ? Math.max(0, Math.min(23, h)) : 18
  const mm = Number.isFinite(m) ? Math.max(0, Math.min(59, m)) : 0
  if (args.frequency === "daily") return `${mm} ${hh} * * *`
  if (args.frequency === "weekdays") return `${mm} ${hh} * * 1-5`
  const w = [...args.weekdays].sort((a, b) => a - b)
  if (w.length === 0) return `${mm} ${hh} * * 0`
  return `${mm} ${hh} * * ${w.join(",")}`
}

export function parseCronToBuilderState(cron: string): BuilderState {
  const trimmed = cron.trim()
  const fields = trimmed.split(/\s+/)
  if (fields.length !== 5) {
    return { frequency: "custom", time: "18:00", weekdays: [0], raw: trimmed }
  }
  const minute = fields[0] as string
  const hour = fields[1] as string
  const dom = fields[2] as string
  const month = fields[3] as string
  const dow = fields[4] as string
  if (dom !== "*" || month !== "*") {
    return { frequency: "custom", time: "18:00", weekdays: [0], raw: trimmed }
  }
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) {
    return { frequency: "custom", time: "18:00", weekdays: [0], raw: trimmed }
  }
  const mm = minute.padStart(2, "0")
  const hh = hour.padStart(2, "0")
  const time = `${hh}:${mm}`
  if (dow === "*") return { frequency: "daily", time, weekdays: [], raw: trimmed }
  if (dow === "1-5") return { frequency: "weekdays", time, weekdays: [1, 2, 3, 4, 5], raw: trimmed }
  const weekdays: number[] = []
  let ok = true
  for (const part of dow.split(",")) {
    const n = parseInt(part, 10)
    if (Number.isNaN(n)) { ok = false; break }
    let v = n
    if (v === 7) v = 0
    if (v < 0 || v > 6) { ok = false; break }
    weekdays.push(v)
  }
  if (ok && weekdays.length > 0) {
    return { frequency: "weekly", time, weekdays: [...new Set(weekdays)].sort((a,b)=>a-b), raw: trimmed }
  }
  return { frequency: "custom", time: "18:00", weekdays: [0], raw: trimmed }
}

function parseField(field: string, min: number, max: number): Set<number> | null {
  const result = new Set<number>()
  if (field === "*") {
    for (let i = min; i <= max; i++) result.add(i)
    return result
  }
  const parts = field.split(",")
  for (const part of parts) {
    const stepSplit = part.split("/")
    const rangePart = stepSplit[0] as string
    const step = stepSplit[1] ? parseInt(stepSplit[1] as string, 10) : 1
    if (Number.isNaN(step) || step < 1) return null
    let rangeMin: number
    let rangeMax: number
    if (rangePart === "*") {
      rangeMin = min
      rangeMax = max
    } else if (rangePart.includes("-")) {
      const ab = rangePart.split("-")
      rangeMin = parseInt(ab[0] as string, 10)
      rangeMax = parseInt(ab[1] as string, 10)
      if (Number.isNaN(rangeMin) || Number.isNaN(rangeMax)) return null
    } else {
      const v = parseInt(rangePart, 10)
      if (Number.isNaN(v)) return null
      rangeMin = v
      rangeMax = v
    }
    if (rangeMin < min || rangeMax > max || rangeMin > rangeMax) return null
    for (let v = rangeMin; v <= rangeMax; v += step) result.add(v)
  }
  return result
}

export function validateCron(expr: string): { valid: boolean; error?: string } {
  const trimmed = expr.trim()
  if (!trimmed) return { valid: false, error: "Cron expression required" }
  if (trimmed.startsWith("@")) return { valid: false, error: "Shorthand @reboot etc not supported — use 5-field cron" }
  const fields = trimmed.split(/\s+/)
  if (fields.length !== 5) return { valid: false, error: `Expected 5 fields, got ${fields.length}` }
  if (trimmed.length > 64) return { valid: false, error: "Cron too long (max 64)" }
  if (!CRON_FIELD_REGEX.test(trimmed)) return { valid: false, error: "Invalid characters — use digits, *, ,, -, /" }
  const ranges: [number, number][] = [[0, 59],[0, 23],[1, 31],[1, 12],[0, 7]]
  for (let i = 0; i < 5; i++) {
    const f = fields[i] as string
    const mn = ranges[i]![0]
    const mx = ranges[i]![1]
    if (parseField(f, mn, mx) === null) return { valid: false, error: `Invalid field ${i + 1}: "${f}" out of range ${mn}-${mx}` }
  }
  return { valid: true }
}

export function describeCron(expr: string): string {
  const v = validateCron(expr)
  if (!v.valid) return v.error || "Invalid cron"
  const [minute, hour, dom, month, dow] = expr.trim().split(/\s+/) as [string, string, string, string, string]
  const dowNames = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]
  const monthNames = ["","January","February","March","April","May","June","July","August","September","October","November","December"]

  // Well-known frequency phrases
  if (expr.trim() === "* * * * *") return "Every minute"
  if (/^\*\/(\d+)$/.test(minute) && hour === "*" && dom === "*" && month === "*" && dow === "*") {
    return `Every ${minute.slice(2)} minutes`
  }
  if (minute === "0" && hour === "*" && dom === "*" && month === "*" && dow === "*") {
    return "Every hour, at minute 0"
  }
  if (minute === "0" && /^\*\/(\d+)$/.test(hour) && dom === "*" && month === "*" && dow === "*") {
    return `Every ${hour.slice(2)} hours, at minute 0`
  }

  const m = parseInt(minute, 10)
  const h = parseInt(hour, 10)
  const hasExactTime = !Number.isNaN(m) && !Number.isNaN(h) && String(m) === minute && String(h) === hour && m >= 0 && m <= 59 && h >= 0 && h <= 23

  if (hasExactTime) {
    const timeStr = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`

    // Daily: e.g. "0 0 * * *", "40 11 * * *"
    if (dom === "*" && month === "*" && dow === "*") {
      return `At ${timeStr}, every day`
    }

    // Weekdays: "0 18 * * 1-5"
    if (dom === "*" && month === "*" && (dow === "1-5" || dow === "1,2,3,4,5")) {
      return `At ${timeStr}, Monday through Friday`
    }

    // Weekends: "0 18 * * 0,6"
    if (dom === "*" && month === "*" && (dow === "0,6" || dow === "6,0" || dow === "0,7" || dow === "7,6" || dow === "6,7")) {
      return `At ${timeStr}, only on weekends`
    }

    // Specific weekdays: "0 18 * * 0", "0 18 * * 1,4"
    if (dom === "*" && month === "*" && dow !== "*") {
      const parts = dow.split(",")
      const validDows: string[] = []
      let ok = true
      for (const p of parts) {
        let n = parseInt(p, 10)
        if (Number.isNaN(n) || n < 0 || n > 7) { ok = false; break }
        if (n === 7) n = 0
        validDows.push(dowNames[n] ?? p)
      }
      if (ok && validDows.length > 0) {
        const dayStr = validDows.length === 2 ? `${validDows[0]} and ${validDows[1]}` : (validDows.length === 1 ? validDows[0] : `${validDows.slice(0, -1).join(", ")}, and ${validDows[validDows.length - 1]}`)
        return `At ${timeStr}, only on ${dayStr}`
      }
    }

    // Day of month: "0 18 1 * *"
    if (dom !== "*" && month === "*" && dow === "*") {
      return `At ${timeStr}, on day ${dom} of every month`
    }

    // Month & Day: "0 18 1 1 *"
    if (dom !== "*" && month !== "*" && dow === "*") {
      const mn = parseInt(month, 10)
      if (mn >= 1 && mn <= 12) {
        return `At ${timeStr}, on ${monthNames[mn]} ${dom}`
      }
    }
  }

  if (/^\*\/\d+/.test(minute) || /^\*\/\d+/.test(hour)) {
    return `Every ${minute} minute(s), every ${hour} hour(s) — ${expr}`
  }
  return `Cron ${expr} — every ${minute !== "*" ? `minute ${minute}` : "minute"}, hour ${hour}, day ${dom}, month ${month}, weekday ${dow}`
}

function matchesCron(date: Date, sets: Set<number>[]): boolean {
  const jakartaOffsetMs = 7 * 60 * 60 * 1000
  const j = new Date(date.getTime() + jakartaOffsetMs)
  const minute = j.getUTCMinutes()
  const hour = j.getUTCHours()
  const dom = j.getUTCDate()
  const month = j.getUTCMonth() + 1
  const dow = j.getUTCDay()
  const checks = [minute, hour, dom, month, dow]
  for (let i = 0; i < 5; i++) {
    const v = checks[i] as number
    const s = sets[i] as Set<number>
    if (i === 4 && s.has(7) && v === 0) continue
    if (!s.has(v)) return false
  }
  return true
}

/** @deprecated Prefer server GET /api/schedules/preview for authoritative next_runs (Asia/Jakarta ZoneInfo). Kept for offline fallback/tests. */
export function getNextRuns(cronExpr: string, count = 3, fromDate = new Date()): Date[] {
  if (!validateCron(cronExpr).valid) return []
  const fields = cronExpr.trim().split(/\s+/) as [string, string, string, string, string]
  const ranges: [number, number][] = [[0, 59],[0, 23],[1, 31],[1, 12],[0, 7]]
  const sets: Set<number>[] = []
  for (let i = 0; i < 5; i++) {
    const s = parseField(fields[i] as string, ranges[i]![0], ranges[i]![1])
    if (!s) return []
    sets.push(s)
  }
  const results: Date[] = []
  let cursor = new Date(fromDate.getTime() + 60_000)
  cursor.setSeconds(0, 0)
  const maxMinutes = 366 * 24 * 60
  for (let i = 0; i < maxMinutes && results.length < count; i++) {
    if (matchesCron(cursor, sets)) results.push(new Date(cursor))
    cursor = new Date(cursor.getTime() + 60_000)
  }
  return results
}

export function formatNextRun(date: Date): { jakarta: string; utc: string } {
  const jakartaStr = new Date(date.getTime()).toLocaleString("en-GB", { timeZone: "Asia/Jakarta", year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })
  const utcStr = date.toISOString().replace("T", " ").slice(0, 16) + " UTC"
  return { jakarta: `${jakartaStr} WIB`, utc: utcStr }
}
