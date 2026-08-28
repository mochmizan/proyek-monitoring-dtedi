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

export const cronExprSchema = z
  .string()
  .trim()
  .min(1, "Cron required")
  .refine((v) => v.split(/\s+/).length === 5, { message: "Cron must have 5 fields (minute hour dom month dow)" })
  .refine((v) => !v.startsWith("@"), { message: "Shorthand @ not supported" })
  .refine((v) => /^[\d*,/\-\s]+$/.test(v), { message: "Invalid cron characters" })

export const scheduleCreateSchema = z.object({
  dev_id: z.string().min(1, "Device required"),
  hub_id: z.string().nullable().optional(),
  cron_expr: cronExprSchema,
  payload: z.record(z.string(), z.unknown()).refine((p) => Object.keys(p).length > 0, { message: "Payload required" }),
  tz: z.string().default("Asia/Jakarta"),
  enabled: z.boolean().default(true),
})
