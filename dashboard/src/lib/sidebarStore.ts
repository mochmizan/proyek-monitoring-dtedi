import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface SidebarState {
  isCollapsed: boolean
  isMobileOpen: boolean
  toggleCollapsed: () => void
  setCollapsed: (collapsed: boolean) => void
  toggleMobile: () => void
  setMobileOpen: (open: boolean) => void
  closeMobile: () => void
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      isCollapsed: false,
      isMobileOpen: false,
      toggleCollapsed: () => set((s) => ({ isCollapsed: !s.isCollapsed })),
      setCollapsed: (isCollapsed) => set({ isCollapsed }),
      toggleMobile: () => set((s) => ({ isMobileOpen: !s.isMobileOpen })),
      setMobileOpen: (isMobileOpen) => set({ isMobileOpen }),
      closeMobile: () => set({ isMobileOpen: false }),
    }),
    {
      name: 'smsb-sidebar-pref',
      partialize: (state) => ({ isCollapsed: state.isCollapsed }),
    }
  )
)
