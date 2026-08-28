import { cn } from '../lib/utils';

export type StatusTone = 'emerald' | 'amber' | 'red' | 'zinc';

const toneClasses: Record<StatusTone, string> = {
  emerald: 'bg-emerald-400',
  amber: 'bg-amber-400',
  red: 'bg-red-400',
  zinc: 'bg-muted-foreground',
};

interface StatusDotProps {
  tone: StatusTone;
  label: string;
  pulse?: boolean;
  className?: string;
}

export function StatusDot({ tone, label, pulse = false, className }: StatusDotProps) {
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn(
        'inline-block size-2 shrink-0 rounded-full',
        toneClasses[tone],
        pulse && 'animate-pulse',
        className
      )}
    />
  );
}
