import { LogOut } from 'lucide-react'
import { useSidebarStore } from '@/lib/sidebarStore'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export interface SidebarFooterProps {
  currentUser?: {
    display_name?: string | null
    username?: string | null
  } | null
  role?: string
  onLogout?: () => void
  isLoggingOut?: boolean
  isCollapsed?: boolean
  className?: string
}

export function SidebarFooter({
  currentUser,
  role = 'viewer',
  onLogout,
  isLoggingOut = false,
  isCollapsed: controlledCollapsed,
  className,
}: SidebarFooterProps) {
  const storeCollapsed = useSidebarStore((s) => s.isCollapsed)
  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : storeCollapsed

  const displayName = currentUser?.display_name || currentUser?.username || 'User'
  const initial = displayName.charAt(0).toUpperCase()

  if (isCollapsed) {
    return (
      <div
        className={cn(
          "p-2 border-t border-zinc-800/80 bg-zinc-900/40 flex flex-col items-center gap-2",
          className
        )}
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              tabIndex={0}
              aria-label={`${displayName} (${role})`}
              className="h-9 w-9 rounded-full bg-indigo-700/50 flex items-center justify-center font-bold text-xs text-indigo-300 border border-indigo-500/30 cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              {initial}
            </div>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={12}>
            {displayName} ({role})
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onLogout}
              disabled={isLoggingOut}
              aria-label="Sign Out"
              className="h-9 w-9 flex items-center justify-center rounded-lg border border-zinc-800 text-zinc-400 hover:bg-red-950/20 hover:text-red-400 hover:border-red-900/50 transition-all cursor-pointer disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              <LogOut className="h-4 w-4" />
              <span className="sr-only">Sign Out</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={12}>
            Sign Out
          </TooltipContent>
        </Tooltip>
      </div>
    )
  }

  return (
    <div
      className={cn(
        "p-4 border-t border-zinc-800/80 bg-zinc-900/40 select-none",
        className
      )}
    >
      <div className="flex items-center gap-3 mb-3">
        <div className="h-9 w-9 rounded-full bg-indigo-700/50 flex items-center justify-center font-bold text-xs text-indigo-300 border border-indigo-500/30 shrink-0">
          {initial}
        </div>
        <div className="overflow-hidden min-w-0">
          <h4 className="font-medium text-sm text-zinc-200 truncate">{displayName}</h4>
          <span className="text-[10px] text-zinc-500 font-semibold uppercase tracking-wider block">
            {role}
          </span>
        </div>
      </div>
      <button
        type="button"
        onClick={onLogout}
        disabled={isLoggingOut}
        className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-zinc-800 rounded-lg hover:bg-red-950/20 hover:text-red-400 hover:border-red-900/50 transition-all text-xs text-zinc-400 font-medium cursor-pointer disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      >
        <LogOut className="h-3.5 w-3.5" />
        <span>Sign Out</span>
      </button>
    </div>
  )
}
