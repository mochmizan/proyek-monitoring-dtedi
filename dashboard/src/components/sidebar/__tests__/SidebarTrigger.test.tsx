import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SidebarTrigger } from '../SidebarTrigger'
import { useSidebarStore } from '@/lib/sidebarStore'
import { TooltipProvider } from '@/components/ui/tooltip'

describe('SidebarTrigger Component', () => {
  beforeEach(() => {
    useSidebarStore.setState({
      isCollapsed: false,
      isMobileOpen: false,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders expanded state on desktop by default', () => {
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

    render(
      <TooltipProvider>
        <SidebarTrigger />
      </TooltipProvider>
    )

    const btn = screen.getByRole('button', { name: /toggle navigation sidebar/i })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(btn)
    expect(useSidebarStore.getState().isCollapsed).toBe(true)
  })

  it('renders collapsed state on desktop when isCollapsed is true', () => {
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

    useSidebarStore.setState({ isCollapsed: true })

    render(
      <TooltipProvider>
        <SidebarTrigger />
      </TooltipProvider>
    )

    const btn = screen.getByRole('button', { name: /toggle navigation sidebar/i })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders closed state on mobile by default and toggles mobile drawer', () => {
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

    render(
      <TooltipProvider>
        <SidebarTrigger />
      </TooltipProvider>
    )

    const btn = screen.getByRole('button', { name: /toggle navigation sidebar/i })
    expect(btn).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(btn)
    expect(useSidebarStore.getState().isMobileOpen).toBe(true)
  })

  it('renders open state on mobile when isMobileOpen is true', () => {
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

    useSidebarStore.setState({ isMobileOpen: true })

    render(
      <TooltipProvider>
        <SidebarTrigger />
      </TooltipProvider>
    )

    const btn = screen.getByRole('button', { name: /toggle navigation sidebar/i })
    expect(btn).toHaveAttribute('aria-expanded', 'true')
  })
})
