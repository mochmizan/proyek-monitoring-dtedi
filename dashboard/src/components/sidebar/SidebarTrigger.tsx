import { useState, useEffect } from 'react'
import { PanelLeft, PanelLeftClose } from 'lucide-react'
import { useSidebarStore } from '@/lib/sidebarStore'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export interface SidebarTriggerProps {
  className?: string
}

export function SidebarTrigger({ className }: SidebarTriggerProps) {
  const isCollapsed = useSidebarStore((s) => s.isCollapsed)
  const isMobileOpen = useSidebarStore((s) => s.isMobileOpen)
  const toggleCollapsed = useSidebarStore((s) => s.toggleCollapsed)
  const toggleMobile = useSidebarStore((s) => s.toggleMobile)

  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
    return window.matchMedia('(min-width: 768px)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia('(min-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  const handleClick = () => {
    if (isDesktop) {
      toggleCollapsed()
      setTimeout(() => {
        window.dispatchEvent(new Event('resize'))
      }, 300)
    } else {
      toggleMobile()
    }
  }

  const isOpen = isDesktop ? !isCollapsed : isMobileOpen

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={handleClick}
          aria-label="Toggle navigation sidebar"
          aria-expanded={isOpen}
          className={cn(
            "p-2 rounded-lg text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 cursor-pointer",
            className
          )}
        >
          {isOpen ? (
            <PanelLeftClose className="h-5 w-5" />
          ) : (
            <PanelLeft className="h-5 w-5" />
          )}
          <span className="sr-only">Toggle navigation sidebar</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {isDesktop ? "Toggle Sidebar (Ctrl+B)" : "Toggle Navigation"}
      </TooltipContent>
    </Tooltip>
  )
}
