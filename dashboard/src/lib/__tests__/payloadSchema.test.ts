import { describe, it, expect } from "vitest"
import { atsPayloadSchema, acPayloadSchema, payloadSchema } from "../scheduleApi"

describe("atsPayloadSchema", () => {
  it("accepts warmup bundled", () => {
    expect(atsPayloadSchema.safeParse({ mode: "manual", start_genset: "on" }).success).toBe(true)
  })
  it("accepts single mode", () => {
    expect(atsPayloadSchema.safeParse({ mode: "auto" }).success).toBe(true)
  })
  it("rejects empty", () => {
    expect(atsPayloadSchema.safeParse({}).success).toBe(false)
  })
  it("rejects extra keys", () => {
    expect(atsPayloadSchema.safeParse({ mode: "auto", foo: "bar" }).success).toBe(false)
  })
  it("rejects invalid enum", () => {
    expect(atsPayloadSchema.safeParse({ mode: "invalid" }).success).toBe(false)
  })
})

describe("acPayloadSchema", () => {
  it("accepts ON", () => {
    expect(acPayloadSchema.safeParse({ target: "AC1", action: "ON" }).success).toBe(true)
  })
  it("accepts SET_TEMP with temp", () => {
    expect(acPayloadSchema.safeParse({ target: "AC1", action: "SET_TEMP", temp: 24 }).success).toBe(true)
  })
  it("rejects SET_TEMP missing temp", () => {
    expect(acPayloadSchema.safeParse({ target: "AC1", action: "SET_TEMP" }).success).toBe(false)
  })
  it("rejects temp when not SET_TEMP", () => {
    expect(acPayloadSchema.safeParse({ target: "AC1", action: "ON", temp: 24 }).success).toBe(false)
  })
  it("rejects temp out of range", () => {
    expect(acPayloadSchema.safeParse({ target: "AC1", action: "SET_TEMP", temp: 10 }).success).toBe(false)
    expect(acPayloadSchema.safeParse({ target: "AC1", action: "SET_TEMP", temp: 40 }).success).toBe(false)
  })
  it("rejects missing target", () => {
    expect(acPayloadSchema.safeParse({ action: "ON" }).success).toBe(false)
  })
})

describe("payloadSchema union", () => {
  it("accepts ATS", () => {
    expect(payloadSchema.safeParse({ mode: "manual", start_genset: "on" }).success).toBe(true)
  })
  it("accepts AC", () => {
    expect(payloadSchema.safeParse({ target: "AC2", action: "OFF" }).success).toBe(true)
  })
  it("rejects empty", () => {
    expect(payloadSchema.safeParse({}).success).toBe(false)
  })
  it("rejects unknown shape", () => {
    expect(payloadSchema.safeParse({ foo: "bar" }).success).toBe(false)
  })
})
