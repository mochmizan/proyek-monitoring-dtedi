import { useEffect, useRef } from 'react';
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import { cn } from '../lib/utils';
import { queryKeys } from '../lib/queryKeys';
import { fetchRoomMap } from '../lib/api'
import { POLL_MS, STALE_MS } from '../lib/constants';
import type { RoomResponse } from '../types/api';
import { Sparkline } from './Sparkline';
import { FreshnessBadge } from './FreshnessBadge';
import { StatusDot } from './StatusDot';

export type RoomCardStatus = 'Normal' | 'Warning' | 'Critical' | 'Offline';

const statusTone: Record<RoomCardStatus, 'emerald' | 'amber' | 'red' | 'zinc'> = {
  Normal: 'emerald',
  Warning: 'amber',
  Critical: 'red',
  Offline: 'zinc',
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
    (d) => d.dev_type === 'TS' && typeof d.latest_reading?.temp === 'number'
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
    <div
      className={cn(
        'relative rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 p-5 flex flex-col gap-3 transition-colors',
        'has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-indigo-500 has-[a:focus-visible]:border-indigo-500/60 focus-within:outline-none',
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-zinc-100 truncate">
          <Link
            to="/room/$roomId"
            params={{ roomId: room.id }}
            search={{}}
            className="rounded-sm outline-none after:absolute after:inset-0 after:rounded-xl transition-colors hover:text-indigo-400"
          >
            {room.name}
          </Link>
        </h3>
        <StatusDot tone={statusTone[status]} label={`Status: ${status}`} pulse={status !== 'Offline'} />
      </div>

      <div key={temp ?? 'no-temp'} className="value-flash -mx-1 px-1 py-0.5 min-h-[2.75rem]">
        {temp === null ? (
          <p className="text-sm text-zinc-400 leading-relaxed">Awaiting readings</p>
        ) : (
          <p className="text-3xl font-semibold tabular-nums text-zinc-100 leading-none">
            {temp.toFixed(1)}
            <span className="ml-1 text-base font-medium text-zinc-400">°C</span>
          </p>
        )}
      </div>

      <p className="text-sm text-zinc-300">
        {humid === null ? (
          <span className="text-zinc-400">Humidity —</span>
        ) : (
          <>
            Humidity <span className="tabular-nums font-medium">{humid.toFixed(0)}%</span>
          </>
        )}
      </p>

      <div className="mt-auto flex items-end justify-between gap-3 pt-3 border-t border-zinc-800/60">
        <div className="flex flex-col gap-1 min-w-0">
          <span className="text-xs font-medium text-zinc-400">
            {room.device_count} {room.device_count === 1 ? 'device' : 'devices'}
          </span>
          <FreshnessBadge dataUpdatedAt={dataUpdatedAt} />
        </div>
        <div className="flex items-center gap-1.5">
          <Sparkline values={trendRef.current} />
          <ChevronRight className="h-4 w-4 text-zinc-400" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}

export function RoomCardSkeleton() {
  return (
    <div
      aria-hidden="true"
      className="rounded-xl bg-zinc-900 border border-zinc-800 p-5 flex flex-col gap-3 animate-pulse"
    >
      <div className="flex items-center justify-between">
        <div className="h-4 w-24 rounded bg-zinc-800" />
        <div className="h-2 w-2 rounded-full bg-zinc-800" />
      </div>
      <div className="min-h-[2.75rem] flex items-center">
        <div className="h-8 w-24 rounded bg-zinc-800" />
      </div>
      <div className="h-3.5 w-28 rounded bg-zinc-800" />
      <div className="mt-auto flex items-end justify-between gap-3 pt-3 border-t border-zinc-800/60">
        <div className="flex flex-col gap-2">
          <div className="h-3 w-16 rounded bg-zinc-800" />
          <div className="h-3 w-24 rounded bg-zinc-800" />
        </div>
        <div className="h-7 w-24 rounded bg-zinc-800" />
      </div>
    </div>
  );
}
