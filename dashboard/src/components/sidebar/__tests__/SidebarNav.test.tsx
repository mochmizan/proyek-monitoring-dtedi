import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SidebarNav } from '../SidebarNav'
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

describe('SidebarNav Component', () => {
  it('renders default navigation links for viewer role', () => {
    render(
      <TooltipProvider>
        <SidebarNav role="viewer" isAdmin={false} isCollapsed={false} />
      </TooltipProvider>
    )

    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Floor Map')).toBeInTheDocument()
    expect(screen.getByText('Alert History')).toBeInTheDocument()
    expect(screen.getByText('Hubs')).toBeInTheDocument()
    expect(screen.queryByText('Schedules')).not.toBeInTheDocument()
    expect(screen.queryByText('Settings')).not.toBeInTheDocument()
  })

  it('shows Schedules for operator role', () => {
    render(
      <TooltipProvider>
        <SidebarNav role="operator" isAdmin={false} isCollapsed={false} />
      </TooltipProvider>
    )

    expect(screen.getByText('Schedules')).toBeInTheDocument()
    expect(screen.queryByText('Settings')).not.toBeInTheDocument()
  })

  it('shows Schedules and Settings for admin role', () => {
    render(
      <TooltipProvider>
        <SidebarNav role="admin" isAdmin={true} isCollapsed={false} />
      </TooltipProvider>
    )

    expect(screen.getByText('Schedules')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders alert count pill in expanded mode', () => {
    render(
      <TooltipProvider>
        <SidebarNav role="viewer" alertCount={5} isCollapsed={false} />
      </TooltipProvider>
    )

    const badge = screen.getByText('5')
    expect(badge).toBeInTheDocument()
    expect(badge.className).toContain('bg-red-500')
    expect(badge.className).toContain('rounded-full')
  })

  it('renders alert dot in collapsed mode', () => {
    render(
      <TooltipProvider>
        <SidebarNav role="viewer" alertCount={3} isCollapsed={true} />
      </TooltipProvider>
    )

    const dot = screen.getByTestId('alert-dot')
    expect(dot).toBeInTheDocument()
    expect(dot.className).toContain('bg-red-500')
    expect(dot.className).toContain('rounded-full')
    expect(screen.queryByText('Alert History')).not.toBeInTheDocument()
  })

  it('fires onItemClick callback when a link is clicked', () => {
    const onItemClick = vi.fn()
    render(
      <TooltipProvider>
        <SidebarNav role="viewer" isCollapsed={false} onItemClick={onItemClick} />
      </TooltipProvider>
    )

    fireEvent.click(screen.getByText('Dashboard'))
    expect(onItemClick).toHaveBeenCalledTimes(1)
  })
})
