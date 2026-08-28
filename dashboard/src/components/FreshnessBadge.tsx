import { useEffect, useState } from 'react';
import { cn } from '../lib/utils';

interface FreshnessBadgeProps {
  dataUpdatedAt?: number;
  className?: string;
}

export function FreshnessBadge({ dataUpdatedAt, className }: FreshnessBadgeProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const ageSeconds =
    typeof dataUpdatedAt === 'number'
      ? Math.max(0, Math.round((now - dataUpdatedAt) / 1000))
      : null;
  const stale = ageSeconds !== null && ageSeconds > 15;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap',
        stale ? 'bg-amber-500/10 text-amber-400 rounded-full px-1.5 py-0.5' : 'text-muted-foreground',
        className
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'size-1.5 rounded-full',
          stale ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'
        )}
      />
      {ageSeconds === null ? 'Awaiting sync' : `Updated ${ageSeconds}s ago`}
    </span>
  );
}
