import { Dialog as DialogPrimitive } from 'radix-ui'
import { useSidebarStore } from '@/lib/sidebarStore'
import { SidebarHeader } from './SidebarHeader'
import { SidebarNav } from './SidebarNav'
import { SidebarFooter } from './SidebarFooter'
import { cn } from '@/lib/utils'

export interface AppSidebarProps {
  currentUser?: {
    display_name?: string | null
    username?: string | null
  } | null
  role?: string
  isAdmin?: boolean
  alertCount?: number
  onLogout?: () => void
  isLoggingOut?: boolean
  className?: string
}

export function AppSidebar({
  currentUser,
  role = 'viewer',
  isAdmin = false,
  alertCount = 0,
  onLogout,
  isLoggingOut = false,
  className,
}: AppSidebarProps) {
  const isCollapsed = useSidebarStore((s) => s.isCollapsed)
  const isMobileOpen = useSidebarStore((s) => s.isMobileOpen)
  const setMobileOpen = useSidebarStore((s) => s.setMobileOpen)
  const closeMobile = useSidebarStore((s) => s.closeMobile)

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        aria-label="Primary Navigation"
        className={cn(
          "hidden md:flex flex-col h-full rounded-none bg-zinc-900/80 backdrop-blur-xl border-r border-zinc-800/80 shadow-none transition-[width] duration-300 ease-[var(--ease-out)] flex-shrink-0 select-none overflow-hidden z-20",
          isCollapsed ? "w-[68px]" : "w-[260px]",
          className
        )}
      >
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto overflow-x-hidden">
          <SidebarHeader isCollapsed={isCollapsed} />
          <div className="flex-1 py-0">
            <SidebarNav
              role={role}
              isAdmin={isAdmin}
              alertCount={alertCount}
              isCollapsed={isCollapsed}
            />
          </div>
        </div>
        <SidebarFooter
          currentUser={currentUser}
          role={role}
          onLogout={onLogout}
          isLoggingOut={isLoggingOut}
          isCollapsed={isCollapsed}
        />
      </aside>

      {/* Mobile Slide-over Drawer */}
      <DialogPrimitive.Root open={isMobileOpen} onOpenChange={setMobileOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay
            data-slot="dialog-overlay"
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity duration-300 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0 md:hidden"
          />
          <DialogPrimitive.Content
            data-slot="dialog-content"
            aria-describedby="mobile-sidebar-description"
            className="fixed inset-y-0 left-0 z-50 w-[280px] max-w-[calc(100vw-2rem)] rounded-none bg-zinc-900/95 backdrop-blur-2xl border-r border-zinc-800 shadow-none flex flex-col justify-between overflow-hidden outline-none data-[state=closed]:animate-out data-[state=closed]:slide-out-to-left-full data-[state=open]:animate-in data-[state=open]:slide-in-from-left-full duration-300 ease-[var(--ease-drawer)] md:hidden"
          >
            <DialogPrimitive.Title className="sr-only">Navigation Menu</DialogPrimitive.Title>
            <DialogPrimitive.Description id="mobile-sidebar-description" className="sr-only">
              Mobile navigation menu and user settings
            </DialogPrimitive.Description>

            <div className="flex-1 flex flex-col min-h-0 overflow-y-auto overflow-x-hidden">
              <SidebarHeader
                isCollapsed={false}
                showCloseButton
                onClose={closeMobile}
              />
              <div className="flex-1 py-0">
                <SidebarNav
                  role={role}
                  isAdmin={isAdmin}
                  alertCount={alertCount}
                  isCollapsed={false}
                  onItemClick={closeMobile}
                />
              </div>
            </div>
            <SidebarFooter
              currentUser={currentUser}
              role={role}
              onLogout={onLogout}
              isLoggingOut={isLoggingOut}
              isCollapsed={false}
            />
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </>
  )
}
