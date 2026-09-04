let counter = 0
type Toast = { id: number; title: string; description?: string; variant?: "default" | "destructive" }

const listeners = new Set<(t: Toast) => void>()

function emit(t: Toast) {
  for (const l of listeners) l(t)
  // also fallback to console
  if (t.variant === "destructive") console.error(`[toast] ${t.title} ${t.description ?? ""}`)
  else console.log(`[toast] ${t.title} ${t.description ?? ""}`)
}

export const toast = {
  success: (title: string, opts?: { description?: string }) => emit({ id: ++counter, title, description: opts?.description, variant: "default" }),
  error: (title: string, opts?: { description?: string }) => emit({ id: ++counter, title, description: opts?.description, variant: "destructive" }),
  info: (title: string, opts?: { description?: string }) => emit({ id: ++counter, title, description: opts?.description }),
  subscribe: (fn: (t: Toast) => void) => { listeners.add(fn); return () => listeners.delete(fn) },
}

export function parseApiError(e: unknown): string {
  if (e instanceof Error) return e.message
  return String(e)
}
