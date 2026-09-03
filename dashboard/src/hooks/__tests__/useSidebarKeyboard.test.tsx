import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useSidebarKeyboard } from '../useSidebarKeyboard'
import { useSidebarStore } from '@/lib/sidebarStore'

describe('useSidebarKeyboard hook', () => {
  beforeEach(() => {
    useSidebarStore.setState({
      isCollapsed: false,
      isMobileOpen: false,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('toggles isCollapsed on Ctrl+B on desktop', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('768px'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    renderHook(() => useSidebarKeyboard())

    expect(useSidebarStore.getState().isCollapsed).toBe(false)

    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'b',
        ctrlKey: true,
        bubbles: true,
      })
    )

    expect(useSidebarStore.getState().isCollapsed).toBe(true)
  })

  it('toggles isMobileOpen on Ctrl+B on mobile', () => {
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    renderHook(() => useSidebarKeyboard())

    expect(useSidebarStore.getState().isMobileOpen).toBe(false)

    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'b',
        ctrlKey: true,
        bubbles: true,
      })
    )

    expect(useSidebarStore.getState().isMobileOpen).toBe(true)
  })

  it('suppresses shortcut when focus is on an input element', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('768px'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    renderHook(() => useSidebarKeyboard())

    const input = document.createElement('input')
    document.body.appendChild(input)

    input.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'b',
        ctrlKey: true,
        bubbles: true,
      })
    )

    expect(useSidebarStore.getState().isCollapsed).toBe(false)
    document.body.removeChild(input)
  })
})
