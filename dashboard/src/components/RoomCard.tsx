import React from 'react';
import { Link } from '@tanstack/react-router';
import { ChevronRight } from 'lucide-react';
import { cn } from '../lib/utils';
import type { RoomResponse, DeviceResponse, AlertResponse, RoomSparklinePoint } from '../types/api';
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

export interface RoomCardProps {
  room: RoomResponse;
  status?: RoomCardStatus;
  devices?: DeviceResponse[];
  alerts?: AlertResponse[];
  sparklinePoints?: RoomSparklinePoint[];
  className?: string;
}

export function RoomCard({ room, status, devices, alerts, sparklinePoints, className }: RoomCardProps) {
  const computedStatus: RoomCardStatus = React.useMemo(() => {
    if (status) return status;
    if (alerts && alerts.length > 0) {
      if (alerts.some((a) => a.severity === 'critical')) return 'Critical';
      if (alerts.some((a) => a.severity === 'warning')) return 'Warning';
    }
    if (devices && devices.length > 0) {
      if (devices.every((d) => !d.is_active || d.status === 'offline')) return 'Offline';
    }
    return 'Normal';
  }, [status, alerts, devices]);

  // Section A: TS / AC
  const tsAcDevices = React.useMemo(
    () => (devices || []).filter((d) => d.dev_type === 'TS' || d.dev_type === 'AC' || d.dev_type === 'ACC'),
    [devices]
  );
  const hasSectionA = tsAcDevices.length > 0;

  const instantTemp = React.useMemo(() => {
    if (!hasSectionA) return null;
    const temps = tsAcDevices
      .map((d) => d.latest_reading?.temp)
      .filter((t): t is number => typeof t === 'number' && Number.isFinite(t));
    return temps.length > 0 ? Math.max(...temps) : null;
  }, [hasSectionA, tsAcDevices]);

  const instantHumid = React.useMemo(() => {
    if (!hasSectionA) return null;
    const humids = tsAcDevices
      .map((d) => d.latest_reading?.humid)
      .filter((h): h is number => typeof h === 'number' && Number.isFinite(h));
    return humids.length > 0 ? Math.max(...humids) : null;
  }, [hasSectionA, tsAcDevices]);

  // Section B: ATS
  const atsDevices = React.useMemo(
    () => (devices || []).filter((d) => d.dev_type === 'ATS'),
    [devices]
  );
  const hasSectionB = atsDevices.length > 0;

  // Freshness calculation
  const latestTsMs = React.useMemo(() => {
    let maxMs = 0;
    if (sparklinePoints && sparklinePoints.length > 0) {
      const last = sparklinePoints[sparklinePoints.length - 1];
      if (last.timestamp) {
        const ms = new Date(last.timestamp).getTime();
        if (!isNaN(ms) && ms > maxMs) maxMs = ms;
      }
    }
    if (devices) {
      for (const d of devices) {
        if (d.latest_reading?.timestamp) {
          const ms = new Date(d.latest_reading.timestamp).getTime();
          if (!isNaN(ms) && ms > maxMs) maxMs = ms;
        } else if (d.last_seen) {
          const ms = new Date(d.last_seen).getTime();
          if (!isNaN(ms) && ms > maxMs) maxMs = ms;
        }
      }
    }
    return maxMs > 0 ? maxMs : undefined;
  }, [sparklinePoints, devices]);

  const deviceCount = devices ? devices.length : room.device_count ?? 0;
  const sparklineValues = React.useMemo(
    () => (sparklinePoints ? sparklinePoints.map((p) => p.temp) : []),
    [sparklinePoints]
  );

  return (
    <div
      className={cn(
        'relative rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 p-5 flex flex-col gap-3 transition-colors',
        'has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-indigo-500 has-[a:focus-visible]:border-indigo-500/60 focus-within:outline-none',
        className
      )}
    >
      {/* Header: Room Name & Status Dot */}
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
        <StatusDot
          tone={statusTone[computedStatus]}
          label={`Status: ${computedStatus}`}
          pulse={computedStatus !== 'Offline'}
        />
      </div>

      {/* SECTION A: TS / AC Temperature, Humidity & Sparkline */}
      {hasSectionA && (
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2">
            <div className="value-flash -mx-1 px-1 py-0.5 min-h-[2.5rem] flex items-baseline">
              {instantTemp === null ? (
                <span className="text-3xl font-semibold tabular-nums text-zinc-400 leading-none">—</span>
              ) : (
                <p className="text-3xl font-semibold tabular-nums text-zinc-100 leading-none">
                  {instantTemp.toFixed(1)}
                  <span className="ml-1 text-base font-medium text-zinc-400">°C</span>
                </p>
              )}
            </div>
            <Sparkline values={sparklineValues} />
          </div>

          <p className="text-sm text-zinc-300">
            {instantHumid === null ? (
              <span className="text-zinc-400">Humidity —</span>
            ) : (
              <>
                Humidity <span className="tabular-nums font-medium">{instantHumid.toFixed(0)}%</span>
              </>
            )}
          </p>
        </div>
      )}

      {/* SECTION B: ATS Power & Battery Status */}
      {hasSectionB && (
        <div className={cn('flex flex-col gap-1.5', hasSectionA && 'pt-2.5 border-t border-zinc-800/40')}>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">ATS Power</span>
          <div className="flex flex-wrap gap-2 items-center">
            {atsDevices.map((d) => {
              const state = String(
                d.latest_reading?.state || d.latest_reading?.STATE || 'UNKNOWN'
              ).toUpperCase();
              const isPln = state === 'PLN' || state.startsWith('PLN') || state.includes('PLN');
              const isEmergency =
                state.includes('EMERGENCY') || state.includes('GENSET') || state.includes('ALARM');
              const rawVolt = d.latest_reading?.battery ?? d.latest_reading?.aki ?? d.latest_reading?.AKI;
              const volt =
                typeof rawVolt === 'number'
                  ? rawVolt
                  : typeof rawVolt === 'string'
                  ? parseFloat(rawVolt)
                  : null;
              const hasLowVolt = volt !== null && !isNaN(volt) && volt <= 11.8;

              return (
                <div key={d.dev_id} className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={cn(
                      'inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold tracking-wide',
                      isEmergency
                        ? 'bg-red-500/15 text-red-400 border border-red-500/30 animate-pulse'
                        : isPln
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                    )}
                  >
                    {state}
                  </span>
                  {hasLowVolt && (
                    <span
                      className={cn(
                        'inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium',
                        volt <= 11.2
                          ? 'bg-red-500/20 text-red-300 border border-red-500/40'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      )}
                    >
                      Aki {volt.toFixed(1)}V
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SECTION C: Fallback when neither TS/AC nor ATS are paired */}
      {!hasSectionA && !hasSectionB && (
        <div className="py-4 text-center">
          <p className="text-sm text-zinc-500">No sensors paired</p>
        </div>
      )}

      {/* Footer: Device count, Freshness, Navigation Chevron */}
      <div className="mt-auto flex items-end justify-between gap-3 pt-3 border-t border-zinc-800/60">
        <div className="flex flex-col gap-1 min-w-0">
          <span className="text-xs font-medium text-zinc-400">
            {deviceCount} {deviceCount === 1 ? 'device' : 'devices'}
          </span>
          <FreshnessBadge dataUpdatedAt={latestTsMs} />
        </div>
        <ChevronRight
          className="h-4 w-4 text-zinc-400 transition-colors shrink-0"
          aria-hidden="true"
        />
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
      <div className="min-h-[2.5rem] flex items-center justify-between gap-2">
        <div className="h-8 w-20 rounded bg-zinc-800" />
        <div className="h-7 w-24 rounded bg-zinc-800" />
      </div>
      <div className="h-3.5 w-28 rounded bg-zinc-800" />
      <div className="mt-auto flex items-end justify-between gap-3 pt-3 border-t border-zinc-800/60">
        <div className="flex flex-col gap-2">
          <div className="h-3 w-16 rounded bg-zinc-800" />
          <div className="h-3 w-24 rounded bg-zinc-800" />
        </div>
        <div className="h-4 w-4 rounded bg-zinc-800" />
      </div>
    </div>
  );
}
