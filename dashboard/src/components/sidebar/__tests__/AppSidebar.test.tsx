import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AppSidebar } from '../AppSidebar'
import { useSidebarStore } from '@/lib/sidebarStore'
import { TooltipProvider } from '@/components/ui/tooltip'

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    className,
    onClick,
  }: {
    children: React.ReactNode
    to: string
    className?: string
    onClick?: (e: React.MouseEvent) => void
  }) => (
    <a
      href={to}
      className={className}
      onClick={(e) => {
        onClick?.(e)
      }}
    >
      {children}
    </a>
  ),
}))

describe('AppSidebar Component', () => {
  beforeEach(() => {
    useSidebarStore.setState({
      isCollapsed: false,
      isMobileOpen: false,
    })
  })

  it('renders desktop sidebar in expanded state by default', () => {
    render(
      <TooltipProvider>
        <AppSidebar
          currentUser={{ display_name: 'Admin User', username: 'admin' }}
          role="admin"
          isAdmin={true}
        />
      </TooltipProvider>
    )

    const aside = screen.getByRole('complementary', { name: /primary navigation/i })
    expect(aside).toBeInTheDocument()
    expect(aside.className).toContain('w-[260px]')
    expect(aside.className).toContain('rounded-none')
    expect(aside.className).toContain('border-r')
    expect(aside.className).toContain('shadow-none')
    expect(screen.getByText('Proyek Monitoring')).toBeInTheDocument()
    expect(screen.getByText('Admin User')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('collapses to 68px rail when isCollapsed is true', () => {
    useSidebarStore.setState({ isCollapsed: true })

    render(
      <TooltipProvider>
        <AppSidebar
          currentUser={{ display_name: 'Admin User', username: 'admin' }}
          role="admin"
          isAdmin={true}
        />
      </TooltipProvider>
    )

    const aside = screen.getByRole('complementary', { name: /primary navigation/i })
    expect(aside.className).toContain('w-[68px]')
    expect(screen.queryByText('Proyek Monitoring')).not.toBeInTheDocument()
  })

  it('triggers onLogout callback when sign out is clicked', () => {
    const handleLogout = vi.fn()

    render(
      <TooltipProvider>
        <AppSidebar
          currentUser={{ display_name: 'Test User' }}
          role="viewer"
          onLogout={handleLogout}
        />
      </TooltipProvider>
    )

    const signOutBtn = screen.getByRole('button', { name: /sign out/i })
    fireEvent.click(signOutBtn)
    expect(handleLogout).toHaveBeenCalledTimes(1)
  })

  it('opens and closes mobile drawer via store state', () => {
    useSidebarStore.setState({ isMobileOpen: true })

    render(
      <TooltipProvider>
        <AppSidebar
          currentUser={{ display_name: 'Mobile User' }}
          role="viewer"
        />
      </TooltipProvider>
    )

    // Mobile dialog should be visible
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog.className).toContain('rounded-none')
    expect(dialog.className).toContain('border-r')
    expect(dialog.className).toContain('shadow-none')
    expect(screen.getByText('Navigation Menu')).toBeInTheDocument()

    // Close button inside mobile drawer
    const closeBtn = screen.getByRole('button', { name: /close navigation sidebar/i })
    fireEvent.click(closeBtn)

    expect(useSidebarStore.getState().isMobileOpen).toBe(false)
  })
})
