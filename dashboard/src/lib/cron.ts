/**
 * Lightweight cron helpers — avoids external cron-parser/cronstrue deps.
 * 5-field standard cron (minute hour dom month dow), Asia/Jakarta canonical.
 */

const CRON_FIELD_REGEX = /^[\d*,/\-\s]+$/

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
      const [a, b] = rangePart.split("-")
      rangeMin = parseInt(a as string, 10)
      rangeMax = parseInt(b as string, 10)
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
  if (!CRON_FIELD_REGEX.test(trimmed)) return { valid: false, error: "Invalid characters — use digits, *, ,, -, /" }
  const ranges: [number, number][] = [
    [0, 59],
    [0, 23],
    [1, 31],
    [1, 12],
    [0, 7],
  ]
  for (let i = 0; i < 5; i++) {
    const f = fields[i] as string
    const [min, max] = ranges[i] as [number, number]
    if (parseField(f, min, max) === null) return { valid: false, error: `Invalid field ${i + 1}: "${f}" out of range ${min}-${max}` }
  }
  return { valid: true }
}

// Simple human preview — covers common patterns used in ATS scheduling.
export function describeCron(expr: string): string {
  const v = validateCron(expr)
  if (!v.valid) return v.error || "Invalid cron"
  const [minute, hour, dom, month, dow] = expr.trim().split(/\s+/) as [string, string, string, string, string]

  const dowNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
  const monthNames = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

  // Exact presets
  if (expr.trim() === "0 18 * * 0") return "At 6:00 PM, only on Sunday"
  if (expr.trim() === "0 18 * * 1,4") return "At 6:00 PM, only on Monday and Thursday"
  if (expr.trim() === "* * * * *") return "Every minute"

  // Daily at fixed time: "M H * * *"
  if (dom === "*" && month === "*" && dow === "*") {
    const m = parseInt(minute, 10)
    const h = parseInt(hour, 10)
    if (!Number.isNaN(m) && !Number.isNaN(h) && String(m) === minute && String(h) === hour) {
      const ampm = h >= 12 ? "PM" : "AM"
      const h12 = h % 12 === 0 ? 12 : h % 12
      const mm = String(m).padStart(2, "0")
      return `At ${h12}:${mm} ${ampm}, every day`
    }
  }

  // Weekly
  if (dom === "*" && month === "*") {
    const m = parseInt(minute, 10)
    const h = parseInt(hour, 10)
    if (!Number.isNaN(m) && !Number.isNaN(h) && String(m) === minute && String(h) === hour && dow !== "*") {
      const dows = dow.split(",").map((d) => {
        let n = parseInt(d, 10)
        if (n === 7) n = 0
        return dowNames[n] ?? d
      })
      const ampm = h >= 12 ? "PM" : "AM"
      const h12 = h % 12 === 0 ? 12 : h % 12
      const mm = String(m).padStart(2, "0")
      return `At ${h12}:${mm} ${ampm}, only on ${dows.join(", ")}`
    }
  }

  // Monthly day
  if (month === "*" && dow === "*" && dom !== "*") {
    return `At ${hour}:${minute.padStart(2, "0")}, on day ${dom} of the month`
  }

  if (month !== "*" && /^\d+$/.test(month)) {
    const mn = parseInt(month, 10)
    return `At ${hour}:${minute.padStart(2, "0")}, in ${monthNames[mn] ?? month} (day ${dom}, dow ${dow})`
  }

  return `Cron ${expr} — every ${minute !== "*" ? `minute ${minute}` : "minute"}, hour ${hour}, day ${dom}, month ${month}, weekday ${dow}`
}

function matchesCron(date: Date, sets: Set<number>[]): boolean {
  // Use Jakarta time (UTC+7, no DST) for display consistency
  const jakartaOffsetMs = 7 * 60 * 60 * 1000
  const j = new Date(date.getTime() + jakartaOffsetMs)
  const minute = j.getUTCMinutes()
  const hour = j.getUTCHours()
  const dom = j.getUTCDate()
  const month = j.getUTCMonth() + 1
  const dow = j.getUTCDay() // 0 Sun
  const checks = [minute, hour, dom, month, dow]
  for (let i = 0; i < 5; i++) {
    const v = checks[i] as number
    const s = sets[i] as Set<number>
    // Dow: 7 also means Sunday
    if (i === 4 && s.has(7) && v === 0) continue
    if (!s.has(v)) return false
  }
  return true
}

export function getNextRuns(cronExpr: string, count = 3, fromDate = new Date()): Date[] {
  if (!validateCron(cronExpr).valid) return []
  const fields = cronExpr.trim().split(/\s+/) as [string, string, string, string, string]
  const ranges: [number, number][] = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 7]]
  const sets: Set<number>[] = []
  for (let i = 0; i < 5; i++) {
    const s = parseField(fields[i] as string, ranges[i]![0], ranges[i]![1])
    if (!s) return []
    sets.push(s)
  }
  const results: Date[] = []
  // start at next minute boundary
  let cursor = new Date(fromDate.getTime() + 60_000)
  cursor.setSeconds(0, 0)
  // Jakarta offset for iteration limit guard
  const maxMinutes = 366 * 24 * 60 // 1 year
  for (let i = 0; i < maxMinutes && results.length < count; i++) {
    if (matchesCron(cursor, sets)) {
      results.push(new Date(cursor))
      // step at least 1 minute; after match, advance 1 min to find next
    }
    cursor = new Date(cursor.getTime() + 60_000)
  }
  return results
}

export function formatNextRun(date: Date): { jakarta: string; utc: string } {
  const jakarta = new Date(date.getTime())
  // Display Jakarta as UTC+7
  const jakartaStr = jakarta.toLocaleString("en-GB", {
    timeZone: "Asia/Jakarta",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
  const utcStr = date.toISOString().replace("T", " ").slice(0, 16) + " UTC"
  return { jakarta: `${jakartaStr} WIB`, utc: utcStr }
}
