import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../tooltip'

describe('Tooltip Component', () => {
  it('renders trigger element', () => {
    render(
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button">Hover me</button>
          </TooltipTrigger>
          <TooltipContent>Helpful info</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )

    expect(screen.getByRole('button', { name: 'Hover me' })).toBeInTheDocument()
  })

  it('renders content when open is true', () => {
    render(
      <TooltipProvider>
        <Tooltip open={true}>
          <TooltipTrigger asChild>
            <button type="button">Target</button>
          </TooltipTrigger>
          <TooltipContent>Detailed description</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )

    const content = screen.getByText('Detailed description')
    expect(content).toBeInTheDocument()
    expect(content).toHaveAttribute('data-slot', 'tooltip-content')
    expect(content.className).toContain('z-40')
    expect(content.className).toContain('bg-zinc-900/95')
  })

  it('applies custom className to TooltipContent', () => {
    render(
      <TooltipProvider>
        <Tooltip open={true}>
          <TooltipTrigger asChild>
            <button type="button">Target</button>
          </TooltipTrigger>
          <TooltipContent className="custom-test-class">Styled tooltip</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )

    const content = screen.getByText('Styled tooltip')
    expect(content.className).toContain('custom-test-class')
  })
})
