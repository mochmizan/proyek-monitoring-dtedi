import { Link } from '@tanstack/react-router'
import {
  LayoutDashboard,
  Map as MapIcon,
  ShieldAlert,
  Radio,
  CalendarClock,
  Settings as SettingsIcon,
  Users as UsersIcon,
  ScrollText,
  Layers,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { useSidebarStore } from '@/lib/sidebarStore'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

export interface SidebarNavProps {
  role?: string
  isAdmin?: boolean
  alertCount?: number
  isCollapsed?: boolean
  onItemClick?: () => void
  className?: string
}

interface NavItem {
  to: string
  label: string
  icon: ComponentType<{ className?: string }>
  search?: Record<string, unknown>
  visible?: boolean
}

export function SidebarNav({
  role = 'viewer',
  isAdmin = false,
  alertCount = 0,
  isCollapsed: controlledCollapsed,
  onItemClick,
  className,
}: SidebarNavProps) {
  const storeCollapsed = useSidebarStore((s) => s.isCollapsed)
  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : storeCollapsed

  const items: NavItem[] = [
    {
      to: '/',
      label: 'Dashboard',
      icon: LayoutDashboard,
      visible: true,
    },
    {
      to: '/map',
      label: 'Floor Map',
      icon: MapIcon,
      visible: true,
    },
    {
      to: '/alerts',
      label: 'Alert History',
      icon: ShieldAlert,
      search: {},
      visible: true,
    },
    {
      to: '/hubs',
      label: 'Hubs',
      icon: Radio,
      visible: true,
    },
    {
      to: '/clusters',
      label: 'Clusters',
      icon: Layers,
      visible: role === 'super_admin' || role === 'root',
    },
    {
      to: '/schedules',
      label: 'Schedules',
      icon: CalendarClock,
      visible: role === 'super_admin' || role === 'root' || role === 'admin' || role === 'operator',
    },
    {
      to: '/users',
      label: 'User Management',
      icon: UsersIcon,
      visible: isAdmin,
    },
    {
      to: '/activity-logs',
      label: 'Activity Logs',
      icon: ScrollText,
      visible: isAdmin,
    },
    {
      to: '/settings',
      label: 'Settings',
      icon: SettingsIcon,
      visible: isAdmin,
    },
  ]

  const visibleItems = items.filter((item) => item.visible)

  return (
    <nav className={cn("p-0 space-y-0.5 select-none", className)} aria-label="Main Navigation">
      {visibleItems.map((item) => {
        const Icon = item.icon
        const isAlerts = item.to === '/alerts'
        const hasAlerts = isAlerts && alertCount > 0

        const linkContent = (
          <Link
            key={item.to}
            to={item.to}
            search={item.search}
            onClick={onItemClick}
            activeProps={{
              className: 'bg-indigo-600/20 text-indigo-400 border-l-2 border-indigo-500 font-medium',
            }}
            inactiveProps={{
              className: 'text-zinc-400 hover:bg-zinc-800/80 hover:text-zinc-100',
            }}
            className={cn(
              'rounded-none transition-colors relative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
              isCollapsed
                ? 'flex items-center justify-center h-10 w-full'
                : 'flex items-center gap-3 px-4 py-2.5 w-full text-sm'
            )}
          >
            <Icon className="h-5 w-5 shrink-0" />

            {!isCollapsed && (
              <>
                <span className="truncate">{item.label}</span>
                {hasAlerts && (
                  <span className="ml-auto bg-red-500 text-white text-xs px-2 py-0.5 rounded-none font-bold shrink-0">
                    {alertCount}
                  </span>
                )}
              </>
            )}

            {isCollapsed && hasAlerts && (
              <span
                data-testid="alert-dot"
                className="absolute top-1.5 right-1.5 h-2.5 w-2.5 rounded-none bg-red-500 ring-1 ring-zinc-900 animate-pulse"
              />
            )}
          </Link>
        )

        if (isCollapsed) {
          const tooltipText = hasAlerts
            ? `${item.label} (${alertCount} active)`
            : item.label

          return (
            <Tooltip key={item.to}>
              <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
              <TooltipContent side="right" sideOffset={12}>
                {tooltipText}
              </TooltipContent>
            </Tooltip>
          )
        }

        return linkContent
      })}
    </nav>
  )
}
