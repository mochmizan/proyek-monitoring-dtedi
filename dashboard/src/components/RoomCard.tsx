import { useEffect, useRef } from 'react';
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { queryKeys } from '@/lib/queryKeys';
import { fetchRoomMap } from '@/lib/api';
import { POLL_MS, STALE_MS } from '@/lib/constants';
import type { RoomResponse } from '@/types/api';
import { Sparkline } from './Sparkline';
import { FreshnessBadge } from './FreshnessBadge';
import { StatusDot } from './StatusDot';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';

export type RoomCardStatus = 'Normal' | 'Warning' | 'Critical' | 'Offline';

const statusTone: Record<RoomCardStatus, 'emerald' | 'amber' | 'red' | 'zinc'> = {
  Normal: 'emerald',
  Warning: 'amber',
  Critical: 'red',
  Offline: 'zinc',
};

const statusBadgeVariant: Record<RoomCardStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  Normal: 'outline',
  Warning: 'secondary',
  Critical: 'destructive',
  Offline: 'outline',
};

interface RoomCardProps {
  room: RoomResponse;
  status: RoomCardStatus;
  className?: string;
}

export function RoomCard({ room, status, className }: RoomCardProps) {
  const { data: roomMap, dataUpdatedAt } = useQuery({
    queryKey: queryKeys.rooms.map(room.id),
    queryFn: () => fetchRoomMap(room.id),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: STALE_MS,
  });

  const tsReading = (roomMap?.devices || []).find(
    (d) => d.dev_type === 'TS' && typeof d.latest_reading?.temp === 'number',
  )?.latest_reading;

  const temp = typeof tsReading?.temp === 'number' ? tsReading.temp : null;
  const humid = typeof tsReading?.humid === 'number' ? tsReading.humid : null;

  const trendRef = useRef<number[]>([]);
  useEffect(() => {
    if (temp === null) return;
    if (trendRef.current[trendRef.current.length - 1] === temp) return;
    trendRef.current = [...trendRef.current, temp].slice(-20);
  }, [temp]);

  return (
    <Card
      className={cn(
        'relative flex flex-col gap-0 py-0 overflow-hidden hover:border-border transition-colors',
        'has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-ring has-[a:focus-visible]:border-ring/60 focus-within:outline-none',
        className,
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2 pt-5">
        <CardTitle className="font-semibold text-card-foreground truncate text-sm leading-none">
          <Link
            to="/room/$roomId"
            params={{ roomId: room.id }}
            search={{}}
            className="rounded-sm outline-none after:absolute after:inset-0 after:rounded-xl transition-colors hover:text-primary truncate"
          >
            {room.name}
          </Link>
        </CardTitle>
        <Badge variant={statusBadgeVariant[status]} className="gap-1.5 shrink-0 text-xs">
          <StatusDot tone={statusTone[status]} label={`Status: ${status}`} pulse={status !== 'Offline'} />
          {status}
        </Badge>
      </CardHeader>

      <CardContent className="flex flex-col gap-2 pb-3">
        <div key={temp ?? 'no-temp'} className="value-flash -mx-1 px-1 py-0.5 min-h-[2.75rem] flex items-center">
          {temp === null ? (
            <p className="text-sm text-muted-foreground leading-relaxed">Awaiting readings</p>
          ) : (
            <p className="text-2xl font-semibold tabular-nums font-mono text-card-foreground leading-none">
              {temp.toFixed(1)}
              <span className="ml-1 text-base font-medium text-muted-foreground">°C</span>
            </p>
          )}
        </div>

        <p className="text-sm text-muted-foreground truncate">
          {humid === null ? (
            <span className="text-muted-foreground">Humidity —</span>
          ) : (
            <>
              Humidity <span className="tabular-nums font-medium font-mono text-foreground">{humid.toFixed(0)}%</span>
            </>
          )}
        </p>
      </CardContent>

      <Separator />

      <CardFooter className="flex items-end justify-between gap-3 py-3 border-t-0">
        <div className="flex flex-col gap-1 min-w-0">
          <span className="text-xs font-medium text-muted-foreground tabular-nums">
            {room.device_count} {room.device_count === 1 ? 'device' : 'devices'}
          </span>
          <FreshnessBadge dataUpdatedAt={dataUpdatedAt} />
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Sparkline values={trendRef.current} />
          <ChevronRight className="size-4 text-muted-foreground shrink-0" aria-hidden="true" />
        </div>
      </CardFooter>
    </Card>
  );
}

export function RoomCardSkeleton() {
  return (
    <Card className="flex flex-col gap-0 py-0 overflow-hidden" aria-hidden="true">
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2 pt-5">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pb-3">
        <div className="min-h-[2.75rem] flex items-center">
          <Skeleton className="h-8 w-24" />
        </div>
        <Skeleton className="h-3.5 w-28" />
      </CardContent>
      <Separator />
      <CardFooter className="flex items-end justify-between gap-3 py-3">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 w-24" />
        </div>
        <Skeleton className="h-7 w-24 rounded-md" />
      </CardFooter>
    </Card>
  );
}
