import { useState, useRef, useEffect, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { sendDeviceCommand, fetchCommandStatus } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { POLL_COMMAND_STATUS_MS, COMMAND_DELIVERY_TIMEOUT_MS, COMMAND_AUTO_DISMISS_MS } from '../lib/constants';
import type { DeviceCommand } from '../types/api';

export type CommandLifecycleStatus =
  | 'idle'
  | 'queuing'
  | 'queued'
  | 'delivered'
  | 'timeout'
  | 'error';

export interface UseCommandLifecycleOptions {
  pollIntervalMs?: number; // default POLL_COMMAND_STATUS_MS
  timeoutMs?: number; // default COMMAND_DELIVERY_TIMEOUT_MS
  autoDismissMs?: number; // default COMMAND_AUTO_DISMISS_MS
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
    pollIntervalMs = POLL_COMMAND_STATUS_MS,
    timeoutMs = COMMAND_DELIVERY_TIMEOUT_MS,
    autoDismissMs = COMMAND_AUTO_DISMISS_MS,
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

  const statusRef = useRef<CommandLifecycleStatus>('idle');
  const activeCmdIdRef = useRef<string | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const pollFnRef = useRef<(() => Promise<void>) | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoDismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef<boolean>(true);
  const isResumingRef = useRef<boolean>(false);
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
    isResumingRef.current = false;
  }, []);

  const reset = useCallback(() => {
    clearAllTimers();
    activeCmdIdRef.current = null;
    startTimeRef.current = null;
    pollFnRef.current = null;
    statusRef.current = 'idle';
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
      statusRef.current = 'queuing';
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
        const initialStatus = response.status?.toLowerCase();

        if (initialStatus === 'dispatched' || initialStatus === 'delivered' || initialStatus === 'ack') {
          // Directly delivered
          setCommandStatus('delivered');
          statusRef.current = 'delivered';
          activeCmdIdRef.current = null;
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
        } else if (initialStatus === 'failed' || initialStatus === 'rejected' || initialStatus === 'timeout' || initialStatus === 'error') {
          clearAllTimers();
          activeCmdIdRef.current = null;
          const msg = `Command ${response.status}`;
          setCommandStatus('error');
          statusRef.current = 'error';
          setErrorMessage(msg);
          onError?.(new Error(msg));
          return response;
        }

        // Transition to queued
        setCommandStatus('queued');
        statusRef.current = 'queued';
        setCommandId(cmdId);
        setQueuedAt(now);
        setErrorMessage(null);

        // Elapsed time counter
        const startTime = Date.now();
        startTimeRef.current = startTime;
        activeCmdIdRef.current = cmdId;

        elapsedTimerRef.current = setInterval(() => {
          if (isMountedRef.current) {
            setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
          }
        }, 1000);

        // Client-side timeout timer (12s default)
        timeoutTimerRef.current = setTimeout(() => {
          if (!isMountedRef.current) return;
          clearAllTimers();
          activeCmdIdRef.current = null;
          setCommandStatus('timeout');
          statusRef.current = 'timeout';
          setErrorMessage('No confirmation from hub — check hub connectivity');
          onTimeout?.();
        }, timeoutMs);

        const pollOnce = async () => {
          if (!isMountedRef.current || statusRef.current !== 'queued') return;
          try {
            const statusRes = await fetchCommandStatus(cmdId);
            if (!isMountedRef.current || statusRef.current !== 'queued') return;

            const status = statusRes.status?.toLowerCase();
            if (status === 'dispatched' || status === 'delivered' || status === 'ack') {
              clearAllTimers();
              activeCmdIdRef.current = null;
              const deliveredTime = statusRes.delivered_at ? new Date(statusRes.delivered_at) : new Date();
              setCommandStatus('delivered');
              statusRef.current = 'delivered';
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
            } else if (status === 'failed' || status === 'rejected' || status === 'timeout' || status === 'error') {
              clearAllTimers();
              activeCmdIdRef.current = null;
              const msg = `Command ${statusRes.status}`;
              setCommandStatus('error');
              statusRef.current = 'error';
              setErrorMessage(msg);
              onError?.(new Error(msg));
            }
          } catch (err: unknown) {
            if (!isMountedRef.current || statusRef.current !== 'queued') return;
            clearAllTimers();
            activeCmdIdRef.current = null;
            const msg = err instanceof Error ? err.message : 'Failed to check command delivery status';
            setCommandStatus('error');
            statusRef.current = 'error';
            setErrorMessage(msg);
            onError?.(err instanceof Error ? err : new Error(msg));
          }
        };

        pollFnRef.current = pollOnce;

        // Start polling every pollIntervalMs (1500ms default)
        if (typeof document === 'undefined' || document.visibilityState !== 'hidden') {
          pollTimerRef.current = setInterval(() => {
            void pollOnce();
          }, pollIntervalMs);
        }

        return response;
      } catch (err: unknown) {
        if (!isMountedRef.current) return;
        clearAllTimers();
        activeCmdIdRef.current = null;
        const msg = err instanceof Error ? err.message : 'Failed to dispatch command';
        setCommandStatus('error');
        statusRef.current = 'error';
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
    if (typeof document === 'undefined') return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        isResumingRef.current = false;
        if (pollTimerRef.current !== null) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
        }
      } else if (document.visibilityState === 'visible') {
        if (statusRef.current === 'queued' && activeCmdIdRef.current) {
          if (startTimeRef.current && Date.now() - startTimeRef.current >= timeoutMs) {
            clearAllTimers();
            activeCmdIdRef.current = null;
            setCommandStatus('timeout');
            statusRef.current = 'timeout';
            setErrorMessage('No confirmation from hub — check hub connectivity');
            onTimeout?.();
            return;
          }

          if (pollTimerRef.current === null && !isResumingRef.current) {
            isResumingRef.current = true;
            void (async () => {
              await pollFnRef.current?.();
              const shouldSchedule =
                isMountedRef.current &&
                statusRef.current === 'queued' &&
                isResumingRef.current &&
                pollTimerRef.current === null &&
                (typeof document === 'undefined' || document.visibilityState !== 'hidden');

              isResumingRef.current = false;

              if (shouldSchedule) {
                pollTimerRef.current = setInterval(() => {
                  void pollFnRef.current?.();
                }, pollIntervalMs);
              }
            })();
          }
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [clearAllTimers, onTimeout, pollIntervalMs, timeoutMs]);

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
