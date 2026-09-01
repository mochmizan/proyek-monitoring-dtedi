import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { sendDeviceCommand, fetchCommandStatus } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { DeviceCommand } from '../types/api';

export type CommandLifecycleStatus =
  | 'idle'
  | 'queuing'
  | 'queued'
  | 'delivered'
  | 'timeout'
  | 'error';

export interface UseCommandLifecycleOptions {
  pollIntervalMs?: number; // default 1500ms
  timeoutMs?: number; // default 12000ms
  autoDismissMs?: number; // default 8000ms
  onSuccess?: (commandId: string) => void;
  onError?: (error: Error) => void;
  onTimeout?: () => void;
}

export interface UseCommandLifecycleReturn {
  status: CommandLifecycleStatus;
  commandStatus: CommandLifecycleStatus;
  commandId: string | null;
  queuedAt: Date | null;
  deliveredAt: Date | null;
  errorMessage: string | null;
  isPending: boolean;
  elapsedSeconds: number;
  sendCommand: (devId: string, payload: DeviceCommand) => Promise<{ status: string; command_id: string } | undefined>;
  execute: (devId: string, payload: DeviceCommand) => Promise<{ status: string; command_id: string } | undefined>;
  reset: () => void;
  dismiss: () => void;
  retry: () => Promise<{ status: string; command_id: string } | undefined>;
}

export function useCommandLifecycle(options: UseCommandLifecycleOptions = {}): UseCommandLifecycleReturn {
  const {
    pollIntervalMs = 1500,
    timeoutMs = 12000,
    autoDismissMs = 8000,
    onSuccess,
    onError,
    onTimeout,
  } = options;

  const queryClient = useQueryClient();

  const [commandStatus, setCommandStatus] = useState<CommandLifecycleStatus>('idle');
  const [commandId, setCommandId] = useState<string | null>(null);
  const [queuedAt, setQueuedAt] = useState<Date | null>(null);
  const [deliveredAt, setDeliveredAt] = useState<Date | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoDismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const lastParamsRef = useRef<{ devId: string; payload: DeviceCommand } | null>(null);

  const clearAllTimers = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (timeoutTimerRef.current !== null) {
      clearTimeout(timeoutTimerRef.current);
      timeoutTimerRef.current = null;
    }
    if (autoDismissTimerRef.current !== null) {
      clearTimeout(autoDismissTimerRef.current);
      autoDismissTimerRef.current = null;
    }
    if (elapsedTimerRef.current !== null) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    clearAllTimers();
    if (isMountedRef.current) {
      setCommandStatus('idle');
      setCommandId(null);
      setQueuedAt(null);
      setDeliveredAt(null);
      setErrorMessage(null);
      setElapsedSeconds(0);
    }
  }, [clearAllTimers]);

  const sendCommand = useCallback(
    async (devId: string, payload: DeviceCommand): Promise<{ status: string; command_id: string } | undefined> => {
      clearAllTimers();
      lastParamsRef.current = { devId, payload };

      if (!isMountedRef.current) return;

      setCommandStatus('queuing');
      setCommandId(null);
      setQueuedAt(null);
      setDeliveredAt(null);
      setErrorMessage(null);
      setElapsedSeconds(0);

      try {
        const response = await sendDeviceCommand(devId, payload);
        if (!isMountedRef.current) return response;

        const cmdId = response.command_id;
        const now = new Date();

        if (response.status === 'delivered') {
          // Directly delivered
          setCommandStatus('delivered');
          setCommandId(cmdId);
          setDeliveredAt(now);
          setErrorMessage(null);

          queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
          queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
          queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });

          if (autoDismissMs > 0) {
            autoDismissTimerRef.current = setTimeout(() => {
              if (isMountedRef.current) reset();
            }, autoDismissMs);
          }

          onSuccess?.(cmdId);
          return response;
        }

        // Transition to queued
        setCommandStatus('queued');
        setCommandId(cmdId);
        setQueuedAt(now);
        setErrorMessage(null);

        // Elapsed time counter
        const startTime = Date.now();
        elapsedTimerRef.current = setInterval(() => {
          if (isMountedRef.current) {
            setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
          }
        }, 1000);

        // Client-side timeout timer (12s default)
        timeoutTimerRef.current = setTimeout(() => {
          if (!isMountedRef.current) return;
          clearAllTimers();
          setCommandStatus('timeout');
          setErrorMessage('No confirmation from hub — check hub connectivity');
          onTimeout?.();
        }, timeoutMs);

        // Start polling every pollIntervalMs (1500ms default)
        pollTimerRef.current = setInterval(async () => {
          try {
            const statusRes = await fetchCommandStatus(cmdId);
            if (!isMountedRef.current) return;

            if (statusRes.status === 'delivered') {
              clearAllTimers();
              const deliveredTime = statusRes.delivered_at ? new Date(statusRes.delivered_at) : new Date();
              setCommandStatus('delivered');
              setDeliveredAt(deliveredTime);
              setErrorMessage(null);

              queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
              queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
              queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });

              if (autoDismissMs > 0) {
                autoDismissTimerRef.current = setTimeout(() => {
                  if (isMountedRef.current) reset();
                }, autoDismissMs);
              }

              onSuccess?.(cmdId);
            }
          } catch (err: unknown) {
            if (!isMountedRef.current) return;
            clearAllTimers();
            const msg = err instanceof Error ? err.message : 'Failed to check command delivery status';
            setCommandStatus('error');
            setErrorMessage(msg);
            onError?.(err instanceof Error ? err : new Error(msg));
          }
        }, pollIntervalMs);

        return response;
      } catch (err: unknown) {
        if (!isMountedRef.current) return;
        clearAllTimers();
        const msg = err instanceof Error ? err.message : 'Failed to dispatch command';
        setCommandStatus('error');
        setErrorMessage(msg);
        onError?.(err instanceof Error ? err : new Error(msg));
        return undefined;
      }
    },
    [
      autoDismissMs,
      clearAllTimers,
      onError,
      onSuccess,
      onTimeout,
      pollIntervalMs,
      queryClient,
      reset,
      timeoutMs,
    ]
  );

  const retry = useCallback(async () => {
    if (lastParamsRef.current) {
      return sendCommand(lastParamsRef.current.devId, lastParamsRef.current.payload);
    }
    return undefined;
  }, [sendCommand]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      clearAllTimers();
    };
  }, [clearAllTimers]);

  const isPending = commandStatus === 'queuing' || commandStatus === 'queued';

  return {
    status: commandStatus,
    commandStatus,
    commandId,
    queuedAt,
    deliveredAt,
    errorMessage,
    isPending,
    elapsedSeconds,
    sendCommand,
    execute: sendCommand,
    reset,
    dismiss: reset,
    retry,
  };
}
