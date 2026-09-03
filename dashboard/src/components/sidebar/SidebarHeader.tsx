import { Cpu, X } from 'lucide-react'
import { useSidebarStore } from '@/lib/sidebarStore'
import { cn } from '@/lib/utils'

export interface SidebarHeaderProps {
  isCollapsed?: boolean
  showCloseButton?: boolean
  onClose?: () => void
  className?: string
}

export function SidebarHeader({
  isCollapsed: controlledCollapsed,
  showCloseButton = false,
  onClose,
  className,
}: SidebarHeaderProps) {
  const storeCollapsed = useSidebarStore((s) => s.isCollapsed)
  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : storeCollapsed

  return (
    <div
      className={cn(
        "h-16 flex items-center border-b border-zinc-800/80 px-4 transition-all duration-300",
        isCollapsed ? "justify-center px-2" : "justify-between px-5",
        className
      )}
    >
      <div className="flex items-center gap-2.5 overflow-hidden">
        <div className="h-9 w-9 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center shrink-0">
          <Cpu className="h-5 w-5 text-indigo-400" />
        </div>
        {!isCollapsed && (
          <span className="font-bold text-base tracking-wide bg-gradient-to-r from-indigo-400 via-indigo-300 to-indigo-500 bg-clip-text text-transparent whitespace-nowrap transition-opacity duration-200">
            Proyek Monitoring
          </span>
        )}
      </div>

      {showCloseButton && !isCollapsed && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation sidebar"
          className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors cursor-pointer"
        >
          <X className="h-5 w-5" />
          <span className="sr-only">Close navigation sidebar</span>
        </button>
      )}
    </div>
  )
}
