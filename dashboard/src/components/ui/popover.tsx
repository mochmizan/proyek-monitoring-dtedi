import * as React from "react"
import { cn } from "@/lib/utils"

interface PopoverProps {
  open: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

export function Popover({ children }: PopoverProps) {
  return <div className="relative inline-block">{children}</div>
}

export function PopoverTrigger({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return <div onClick={onClick} className="cursor-pointer inline-flex">{children}</div>
}

export function PopoverContent({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("absolute z-50 mt-2 w-72 rounded-md border border-zinc-800 bg-zinc-900 p-4 shadow-xl outline-none animate-in fade-in zoom-in-95", className)}>
      {children}
    </div>
  )
}
