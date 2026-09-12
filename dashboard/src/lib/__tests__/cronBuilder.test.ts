import { describe, it, expect } from "vitest"
import { buildCron, parseCronToBuilderState, describeCron } from "../cron"

describe("buildCron", () => {
  it("daily 07:30 -> 30 7 * * *", () => {
    expect(buildCron({ frequency: "daily", time: "07:30", weekdays: [] })).toBe("30 7 * * *")
  })
  it("weekdays 18:00 -> 0 18 * * 1-5", () => {
    expect(buildCron({ frequency: "weekdays", time: "18:00", weekdays: [] })).toBe("0 18 * * 1-5")
  })
  it("weekly Sun 18:00 -> 0 18 * * 0", () => {
    expect(buildCron({ frequency: "weekly", time: "18:00", weekdays: [0] })).toBe("0 18 * * 0")
  })
  it("weekly Mon,Thu 18:00 -> 0 18 * * 1,4", () => {
    expect(buildCron({ frequency: "weekly", time: "18:00", weekdays: [1, 4] })).toBe("0 18 * * 1,4")
  })
  it("custom passthrough", () => {
    expect(buildCron({ frequency: "custom", time: "18:00", weekdays: [], raw: "*/30 * * * *" })).toBe("*/30 * * * *")
  })
  it("weekly sorts weekdays", () => {
    expect(buildCron({ frequency: "weekly", time: "07:00", weekdays: [4, 1] })).toBe("0 7 * * 1,4")
  })
})

describe("parseCronToBuilderState round-trip", () => {
  const cases: [string, string][] = [
    ["0 7 * * *", "daily"],
    ["30 7 * * *", "daily"],
    ["0 18 * * 1-5", "weekdays"],
    ["0 18 * * 0", "weekly"],
    ["0 18 * * 1,4", "weekly"],
  ]
  for (const [cron, freq] of cases) {
    it(`${cron} -> ${freq}`, () => {
      const s = parseCronToBuilderState(cron)
      expect(s.frequency).toBe(freq)
      const rebuilt = buildCron(s)
      expect(rebuilt).toBe(cron)
    })
  }
  it("custom for */30", () => {
    const s = parseCronToBuilderState("*/30 * * * *")
    expect(s.frequency).toBe("custom")
    expect(s.raw).toBe("*/30 * * * *")
  })
  it("custom for dom non-*", () => {
    const s = parseCronToBuilderState("0 18 1 * *")
    expect(s.frequency).toBe("custom")
  })
  it("parses 7 as Sunday", () => {
    const s = parseCronToBuilderState("0 18 * * 7")
    expect(s.frequency).toBe("weekly")
    expect(s.weekdays).toEqual([0])
  })
})

describe("describeCron 24-hour descriptions", () => {
  it("formats daily 00:00 correctly", () => {
    expect(describeCron("0 0 * * *")).toBe("At 00:00, every day")
  })
  it("formats daily 11:40 correctly", () => {
    expect(describeCron("40 11 * * *")).toBe("At 11:40, every day")
  })
  it("formats weekly Sunday 18:00 correctly", () => {
    expect(describeCron("0 18 * * 0")).toBe("At 18:00, only on Sunday")
  })
  it("formats weekly Mon,Thu 18:00 correctly", () => {
    expect(describeCron("0 18 * * 1,4")).toBe("At 18:00, only on Monday and Thursday")
  })
  it("formats weekdays 18:00 correctly", () => {
    expect(describeCron("0 18 * * 1-5")).toBe("At 18:00, Monday through Friday")
  })
  it("formats every minute correctly", () => {
    expect(describeCron("* * * * *")).toBe("Every minute")
  })
  it("formats every 10 minutes correctly", () => {
    expect(describeCron("*/10 * * * *")).toBe("Every 10 minutes")
  })
  it("formats every hour correctly", () => {
    expect(describeCron("0 * * * *")).toBe("Every hour, at minute 0")
  })
})

