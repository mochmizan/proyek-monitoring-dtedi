import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useCommandLifecycle } from '../useCommandLifecycle';
import * as api from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api');
  return {
    ...actual,
    sendDeviceCommand: vi.fn(),
    fetchCommandStatus: vi.fn(),
  };
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe('useCommandLifecycle Hook', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in idle state', () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    expect(result.current.commandStatus).toBe('idle');
    expect(result.current.status).toBe('idle');
    expect(result.current.commandId).toBeNull();
    expect(result.current.queuedAt).toBeNull();
    expect(result.current.deliveredAt).toBeNull();
    expect(result.current.errorMessage).toBeNull();
    expect(result.current.isPending).toBe(false);
    expect(result.current.elapsedSeconds).toBe(0);
  });

  it('transitions to queuing then queued upon successful command dispatch', async () => {
    let resolveCommand!: (val: { status: string; command_id: string }) => void;
    vi.mocked(api.sendDeviceCommand).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCommand = resolve;
        })
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    // Call sendCommand
    act(() => {
      result.current.sendCommand('DEV-01', { target: 'AC1', action: 'ON' });
    });

    expect(result.current.commandStatus).toBe('queuing');
    expect(result.current.isPending).toBe(true);
    expect(result.current.errorMessage).toBeNull();

    // Resolve API response
    await act(async () => {
      resolveCommand({ status: 'queued', command_id: 'cmd-123' });
    });

    expect(result.current.commandStatus).toBe('queued');
    expect(result.current.commandId).toBe('cmd-123');
    expect(result.current.queuedAt).toBeInstanceOf(Date);
    expect(result.current.isPending).toBe(true);
  });

  it('polls fetchCommandStatus and transitions to delivered when edge hub delivers', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-poll-1',
    });
    vi.mocked(api.fetchCommandStatus)
      .mockResolvedValueOnce({
        command_id: 'cmd-poll-1',
        dev_id: 'DEV-01',
        hub_id: 'HUB-01',
        payload: { action: 'ON' },
        status: 'pending',
      })
      .mockResolvedValueOnce({
        command_id: 'cmd-poll-1',
        dev_id: 'DEV-01',
        hub_id: 'HUB-01',
        payload: { action: 'ON' },
        status: 'delivered',
        delivered_at: '2026-09-01T12:05:00Z',
      });

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const onSuccess = vi.fn();
    const { result } = renderHook(() => useCommandLifecycle({ onSuccess }), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { action: 'ON' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Advance 1.5s -> first poll (pending)
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(1);
    expect(result.current.commandStatus).toBe('queued');

    // Advance another 1.5s -> second poll (delivered)
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(2);
    expect(result.current.commandStatus).toBe('delivered');
    expect(result.current.deliveredAt).toEqual(new Date('2026-09-01T12:05:00Z'));
    expect(result.current.isPending).toBe(false);
    expect(onSuccess).toHaveBeenCalledWith('cmd-poll-1');

    // Check query invalidations
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.all });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.rooms.all });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.alerts.all });

    // Advance 8s for auto-dismiss
    act(() => {
      vi.advanceTimersByTime(8000);
    });
    expect(result.current.commandStatus).toBe('idle');
  });

  it('transitions to timeout if hub does not deliver within 12 seconds', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-timeout-1',
    });
    vi.mocked(api.fetchCommandStatus).mockResolvedValue({
      command_id: 'cmd-timeout-1',
      dev_id: 'DEV-01',
      hub_id: 'HUB-01',
      payload: {},
      status: 'pending',
    });

    const { wrapper } = createWrapper();
    const onTimeout = vi.fn();
    const { result } = renderHook(() => useCommandLifecycle({ onTimeout }), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { mode: 'manual' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Advance timers by 12 seconds
    await act(async () => {
      vi.advanceTimersByTime(12000);
    });

    expect(result.current.commandStatus).toBe('timeout');
    expect(result.current.isPending).toBe(false);
    expect(result.current.errorMessage).toBe('No confirmation from hub — check hub connectivity');
    expect(onTimeout).toHaveBeenCalled();

    // Verify polling has stopped by advancing further
    const callCount = vi.mocked(api.fetchCommandStatus).mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(vi.mocked(api.fetchCommandStatus).mock.calls.length).toBe(callCount);
  });

  it('transitions to error if initial sendDeviceCommand rejects', async () => {
    vi.mocked(api.sendDeviceCommand).mockRejectedValueOnce(new Error('Network connection failed'));

    const { wrapper } = createWrapper();
    const onError = vi.fn();
    const { result } = renderHook(() => useCommandLifecycle({ onError }), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { mode: 'auto' });
    });

    expect(result.current.commandStatus).toBe('error');
    expect(result.current.isPending).toBe(false);
    expect(result.current.errorMessage).toBe('Network connection failed');
    expect(onError).toHaveBeenCalled();
  });

  it('transitions to error if polling returns an unexpected error', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-err-poll',
    });
    vi.mocked(api.fetchCommandStatus).mockRejectedValueOnce(new Error('Internal Server Error'));

    const { wrapper } = createWrapper();
    const onError = vi.fn();
    const { result } = renderHook(() => useCommandLifecycle({ onError }), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { mode: 'auto' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Advance 1.5s to trigger polling failure
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    expect(result.current.commandStatus).toBe('error');
    expect(result.current.errorMessage).toBe('Internal Server Error');
    expect(result.current.isPending).toBe(false);
    expect(onError).toHaveBeenCalled();
  });

  it('handles immediate delivered response directly', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'delivered',
      command_id: 'cmd-direct-del',
    });

    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { start_genset: 'on' });
    });

    expect(result.current.commandStatus).toBe('delivered');
    expect(result.current.commandId).toBe('cmd-direct-del');
    expect(result.current.deliveredAt).toBeInstanceOf(Date);
    expect(result.current.isPending).toBe(false);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.devices.all });
  });

  it('reset() returns state to idle and clears timers', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-reset-1',
    });
    vi.mocked(api.fetchCommandStatus).mockResolvedValue({
      command_id: 'cmd-reset-1',
      dev_id: 'DEV-01',
      hub_id: 'HUB-01',
      payload: {},
      status: 'pending',
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { mode: 'auto' });
    });

    expect(result.current.commandStatus).toBe('queued');

    act(() => {
      result.current.reset();
    });

    expect(result.current.commandStatus).toBe('idle');
    expect(result.current.commandId).toBeNull();
    expect(result.current.isPending).toBe(false);
    expect(result.current.errorMessage).toBeNull();
  });

  it('retry() re-executes the last command', async () => {
    vi.mocked(api.sendDeviceCommand).mockRejectedValueOnce(new Error('Hub disconnected'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { start_genset: 'on' });
    });

    expect(result.current.commandStatus).toBe('error');

    // Mock success for retry
    vi.mocked(api.sendDeviceCommand).mockResolvedValueOnce({
      status: 'queued',
      command_id: 'cmd-retry-2',
    });

    await act(async () => {
      await result.current.retry();
    });

    expect(api.sendDeviceCommand).toHaveBeenCalledTimes(2);
    expect(api.sendDeviceCommand).toHaveBeenLastCalledWith('DEV-01', { start_genset: 'on' });
    expect(result.current.commandStatus).toBe('queued');
    expect(result.current.commandId).toBe('cmd-retry-2');
  });

  it('halts polling immediately when fetchCommandStatus returns terminal failure', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-fail-1',
    });
    vi.mocked(api.fetchCommandStatus).mockResolvedValueOnce({
      command_id: 'cmd-fail-1',
      dev_id: 'DEV-01',
      hub_id: 'HUB-01',
      payload: {},
      status: 'failed',
    });

    const { wrapper } = createWrapper();
    const onError = vi.fn();
    const { result } = renderHook(() => useCommandLifecycle({ onError }), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { action: 'ON' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Advance 1.5s -> first poll returns failed
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    expect(result.current.commandStatus).toBe('error');
    expect(result.current.errorMessage).toBe('Command failed');
    expect(onError).toHaveBeenCalled();

    // Verify polling has stopped
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(1);
  });

  it('transitions to delivered immediately on case-insensitive ACK', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-ack-1',
    });
    vi.mocked(api.fetchCommandStatus).mockResolvedValueOnce({
      command_id: 'cmd-ack-1',
      dev_id: 'DEV-01',
      hub_id: 'HUB-01',
      payload: {},
      status: 'ACK',
      delivered_at: '2026-09-01T12:06:00Z',
    });

    const { wrapper } = createWrapper();
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useCommandLifecycle({ onSuccess }), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { action: 'ON' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Advance 1.5s -> first poll returns ACK
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    expect(result.current.commandStatus).toBe('delivered');
    expect(result.current.deliveredAt).toEqual(new Date('2026-09-01T12:06:00Z'));
    expect(onSuccess).toHaveBeenCalledWith('cmd-ack-1');
  });

  it('pauses polling when document is hidden and resumes when visible', async () => {
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-vis-1',
    });
    vi.mocked(api.fetchCommandStatus).mockResolvedValue({
      command_id: 'cmd-vis-1',
      dev_id: 'DEV-01',
      hub_id: 'HUB-01',
      payload: {},
      status: 'pending',
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { action: 'ON' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Simulate switching away: tab becomes hidden
    act(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', writable: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Advance 3s while hidden -> should not poll
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(api.fetchCommandStatus).not.toHaveBeenCalled();

    // Switch back: tab becomes visible
    await act(async () => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', writable: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Immediately polls upon becoming visible
    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(1);

    // Further timers advance resumes polling
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(2);
  });

  it('does not schedule interval if tab switches to hidden while resume poll is in-flight', async () => {
    let resolveResumePoll!: (value: any) => void;
    vi.mocked(api.sendDeviceCommand).mockResolvedValue({
      status: 'queued',
      command_id: 'cmd-race-1',
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCommandLifecycle(), { wrapper });

    await act(async () => {
      await result.current.sendCommand('DEV-01', { action: 'ON' });
    });

    expect(result.current.commandStatus).toBe('queued');

    // Switch to hidden
    act(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', writable: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Mock next fetchCommandStatus to stay unresolved until we manually resolve
    vi.mocked(api.fetchCommandStatus).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveResumePoll = resolve;
        })
    );

    // Switch back to visible to initiate resume poll
    act(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', writable: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(1);

    // Before resume poll completes, operator switches away again!
    act(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', writable: true, configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Now resume poll completes
    await act(async () => {
      resolveResumePoll({
        command_id: 'cmd-race-1',
        dev_id: 'DEV-01',
        hub_id: 'HUB-01',
        payload: {},
        status: 'pending',
      });
    });

    // Advance 5 seconds while hidden -> polling should NOT continue!
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Should NOT have polled any further while hidden
    expect(api.fetchCommandStatus).toHaveBeenCalledTimes(1);
  });
});

