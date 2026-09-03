import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarStore } from '../sidebarStore'

describe('sidebarStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useSidebarStore.setState({
      isCollapsed: false,
      isMobileOpen: false,
    })
  })

  it('initializes with default values', () => {
    const state = useSidebarStore.getState()
    expect(state.isCollapsed).toBe(false)
    expect(state.isMobileOpen).toBe(false)
  })

  it('toggles isCollapsed correctly', () => {
    expect(useSidebarStore.getState().isCollapsed).toBe(false)

    useSidebarStore.getState().toggleCollapsed()
    expect(useSidebarStore.getState().isCollapsed).toBe(true)

    useSidebarStore.getState().toggleCollapsed()
    expect(useSidebarStore.getState().isCollapsed).toBe(false)
  })

  it('sets isCollapsed explicitly', () => {
    useSidebarStore.getState().setCollapsed(true)
    expect(useSidebarStore.getState().isCollapsed).toBe(true)

    useSidebarStore.getState().setCollapsed(false)
    expect(useSidebarStore.getState().isCollapsed).toBe(false)
  })

  it('toggles isMobileOpen correctly', () => {
    expect(useSidebarStore.getState().isMobileOpen).toBe(false)

    useSidebarStore.getState().toggleMobile()
    expect(useSidebarStore.getState().isMobileOpen).toBe(true)

    useSidebarStore.getState().toggleMobile()
    expect(useSidebarStore.getState().isMobileOpen).toBe(false)
  })

  it('sets and closes mobile state', () => {
    useSidebarStore.getState().setMobileOpen(true)
    expect(useSidebarStore.getState().isMobileOpen).toBe(true)

    useSidebarStore.getState().closeMobile()
    expect(useSidebarStore.getState().isMobileOpen).toBe(false)
  })

  it('persists only isCollapsed to localStorage', () => {
    useSidebarStore.getState().setCollapsed(true)
    useSidebarStore.getState().setMobileOpen(true)

    const raw = localStorage.getItem('smsb-sidebar-pref')
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw!)
    expect(parsed.state.isCollapsed).toBe(true)
    expect(parsed.state.isMobileOpen).toBeUndefined()
  })
})
