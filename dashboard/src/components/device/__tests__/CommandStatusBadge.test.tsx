import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandStatusBadge } from '../CommandStatusBadge';
import { formatWIBTime } from '../../../lib/dateUtils';

describe('formatWIBTime utility', () => {
  it('formats dates accurately in Asia/Jakarta timezone with WIB suffix', () => {
    // 2026-09-01T12:30:45Z is 19:30:45 in UTC+7 (Asia/Jakarta)
    const date = new Date('2026-09-01T12:30:45Z');
    const result = formatWIBTime(date);
    expect(result).toBe('19:30:45 WIB');
  });

  it('handles empty and invalid dates gracefully', () => {
    expect(formatWIBTime(null)).toBe('');
    expect(formatWIBTime(undefined)).toBe('');
    expect(formatWIBTime('invalid-date')).toBe('');
  });
});

describe('CommandStatusBadge Component', () => {
  it('renders nothing when status is idle', () => {
    const { container } = render(<CommandStatusBadge status="idle" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders queuing indicator when status is queuing', () => {
    render(<CommandStatusBadge status="queuing" />);
    expect(screen.getByText(/Queuing command to server.../i)).toBeInTheDocument();
  });

  it('renders queued pulse indicator with command ID and elapsed time', () => {
    const queuedAt = new Date(Date.now() - 3000);
    render(
      <CommandStatusBadge
        status="queued"
        commandId="cmd-xyz-100"
        queuedAt={queuedAt}
      />
    );
    expect(screen.getByText(/Queued on server — waiting for edge hub delivery.../i)).toBeInTheDocument();
    expect(screen.getByText('[cmd-xyz-100]')).toBeInTheDocument();
  });

  it('renders delivered confirmation with WIB formatted timestamp', () => {
    const deliveredAt = new Date('2026-09-01T12:30:45Z');
    render(
      <CommandStatusBadge
        status="delivered"
        commandId="cmd-xyz-100"
        deliveredAt={deliveredAt}
      />
    );
    expect(screen.getByText(/Delivered to edge hub at 19:30:45 WIB/i)).toBeInTheDocument();
    expect(screen.getByText('[cmd-xyz-100]')).toBeInTheDocument();
  });

  it('renders timeout banner with retry and dismiss buttons', () => {
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(
      <CommandStatusBadge
        status="timeout"
        commandId="cmd-xyz-100"
        errorMessage="No confirmation from hub — check hub connectivity"
        onRetry={onRetry}
        onDismiss={onDismiss}
      />
    );

    expect(screen.getByText(/No confirmation from hub — check hub connectivity/i)).toBeInTheDocument();
    
    const retryBtn = screen.getByRole('button', { name: /Retry/i });
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);

    const dismissBtn = screen.getByRole('button', { name: /Dismiss status/i });
    fireEvent.click(dismissBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders error message with dismiss button', () => {
    const onDismiss = vi.fn();
    render(
      <CommandStatusBadge
        status="error"
        errorMessage="Device unreachable"
        onDismiss={onDismiss}
      />
    );

    expect(screen.getByText('Device unreachable')).toBeInTheDocument();
    const dismissBtn = screen.getByRole('button', { name: /Dismiss status/i });
    fireEvent.click(dismissBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
