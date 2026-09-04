/**
 * Re-export schedule helpers for explicit import path per task spec.
 * Actual implementation lives in api.ts (same-origin fetch + Zod cron validation).
 */
export {
  fetchSchedules,
  fetchSchedule,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  runNowSchedule,
  previewScheduleCron,
} from "./api"

import { z } from "zod"
import { validateCron } from "./cron"

export const cronExprSchema = z
  .string()
  .trim()
  .min(1, "Cron required")
  .max(64, "Cron too long (max 64)")
  .refine((v) => !v.startsWith("@"), { message: "Shorthand @ not supported" })
  .refine((v) => v.split(/\s+/).length === 5, { message: "Cron must have 5 fields (minute hour dom month dow)" })
  .refine((v) => validateCron(v).valid, { message: "Invalid cron expression" })

export const atsPayloadSchema = z
  .object({
    mode: z.enum(["auto", "manual"]).optional(),
    start_genset: z.enum(["on", "off"]).optional(),
    reset: z.literal("rst").optional(),
  })
  .strict()
  .refine((v) => Object.keys(v).length >= 1, { message: "ATS payload requires at least one field" })

export const acPayloadSchema = z
  .object({
    target: z.enum(["AC1", "AC2"]),
    action: z.enum(["ON", "OFF", "SET_TEMP"]),
    temp: z.number().int().min(16).max(30).optional(),
  })
  .strict()
  .superRefine((val, ctx) => {
    if (val.action === "SET_TEMP" && val.temp === undefined) {
      ctx.addIssue({ code: "custom", message: "temp required (16-30) when action is SET_TEMP", path: ["temp"] })
    }
    if (val.action !== "SET_TEMP" && val.temp !== undefined) {
      ctx.addIssue({ code: "custom", message: "temp only allowed when action is SET_TEMP", path: ["temp"] })
    }
  })

export const payloadSchema = z.union([atsPayloadSchema, acPayloadSchema])

export const scheduleCreateSchema = z.object({
  dev_id: z.string().min(1, "Device required"),
  hub_id: z.string().nullable().optional(),
  cron_expr: cronExprSchema,
  payload: payloadSchema,
  tz: z.string().default("Asia/Jakarta"),
  enabled: z.boolean().default(true),
})

export const scheduleUpdateSchema = z.object({
  dev_id: z.string().min(1).optional(),
  hub_id: z.string().nullable().optional(),
  cron_expr: cronExprSchema.optional(),
  payload: payloadSchema.optional(),
  tz: z.string().optional(),
  enabled: z.boolean().optional(),
})

export type CronFrequency = "daily" | "weekdays" | "weekly" | "custom"
export type BuilderState = import("./cron").BuilderState
export { buildCron, parseCronToBuilderState } from "./cron"
export type AtsPayload = z.infer<typeof atsPayloadSchema>
export type AcPayload = z.infer<typeof acPayloadSchema>
export type Payload = z.infer<typeof payloadSchema>
