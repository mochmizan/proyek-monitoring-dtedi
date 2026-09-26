import { useState, useEffect } from 'react';
import { Loader2, CheckCircle2, AlertTriangle, AlertCircle, X, RotateCw } from 'lucide-react';
import { cn } from '../../lib/utils';
import { formatWIBTime } from '../../lib/dateUtils';
import type { CommandLifecycleStatus } from '../../hooks/useCommandLifecycle';

export interface CommandStatusBadgeProps {
  status: CommandLifecycleStatus;
  commandId?: string | null;
  queuedAt?: Date | null;
  deliveredAt?: Date | null;
  errorMessage?: string | null;
  onDismiss?: () => void;
  onRetry?: () => void;
  className?: string;
}

export function CommandStatusBadge({
  status,
  commandId,
  queuedAt,
  deliveredAt,
  errorMessage,
  onDismiss,
  onRetry,
  className,
}: CommandStatusBadgeProps) {
  const [elapsed, setElapsed] = useState<number>(0);

  useEffect(() => {
    if (status !== 'queued' || !queuedAt) {
      setElapsed(0);
      return;
    }
    const interval = setInterval(() => {
      const diffSec = Math.max(0, Math.floor((Date.now() - queuedAt.getTime()) / 1000));
      setElapsed(diffSec);
    }, 1000);
    const initialDiff = Math.max(0, Math.floor((Date.now() - queuedAt.getTime()) / 1000));
    setElapsed(initialDiff);

    return () => clearInterval(interval);
  }, [status, queuedAt]);

  if (status === 'idle') {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'rounded-lg border p-3.5 text-xs transition-all flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3',
        status === 'queuing' && 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300',
        status === 'queued' && 'bg-amber-500/10 border-amber-500/30 text-amber-300',
        status === 'delivered' && 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
        status === 'timeout' && 'bg-amber-500/15 border-amber-500/40 text-amber-300',
        status === 'error' && 'bg-red-500/10 border-red-500/30 text-red-300',
        className
      )}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        {status === 'queuing' && (
          <>
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-indigo-400" />
            <span className="font-medium">Queuing command to server...</span>
          </>
        )}

        {status === 'queued' && (
          <>
            <div className="relative flex items-center justify-center shrink-0">
              <span className="animate-ping absolute inline-flex h-3 w-3 rounded-full bg-amber-400 opacity-75" />
              <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-400 relative" />
            </div>
            <div className="truncate">
              <span className="font-medium">Queued on server — waiting for edge hub delivery...</span>
              <span className="ml-1.5 font-mono text-[11px] opacity-80">({elapsed}s)</span>
              {commandId && (
                <span className="hidden sm:inline-block ml-2 text-[10px] font-mono text-amber-400/70 truncate">
                  [{commandId}]
                </span>
              )}
            </div>
          </>
        )}

        {status === 'delivered' && (
          <>
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <div className="truncate">
              <span className="font-semibold text-emerald-200">
                Published to the local MQTT broker at {formatWIBTime(deliveredAt || new Date())}; device execution is not confirmed
              </span>
              {commandId && (
                <span className="hidden sm:inline-block ml-2 text-[10px] font-mono text-emerald-400/70 truncate">
                  [{commandId}]
                </span>
              )}
            </div>
          </>
        )}

        {status === 'timeout' && (
          <>
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
            <div>
              <span className="font-semibold text-amber-200">
                {errorMessage || 'No confirmation from hub — check hub connectivity'}
              </span>
              {commandId && (
                <span className="hidden sm:inline-block ml-2 text-[10px] font-mono text-amber-400/70 truncate">
                  [{commandId}]
                </span>
              )}
            </div>
          </>
        )}

        {status === 'error' && (
          <>
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400" />
            <div className="truncate">
              <span className="font-semibold text-red-200">
                {errorMessage || 'Failed to dispatch command'}
              </span>
            </div>
          </>
        )}
      </div>

      <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
        {status === 'timeout' && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/30 rounded text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5"
          >
            <RotateCw className="h-3 w-3" />
            <span>Retry</span>
          </button>
        )}

        {(status === 'timeout' || status === 'error' || status === 'delivered') && onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss status"
            className="p-1 hover:bg-zinc-800/60 rounded text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

export default CommandStatusBadge;
