import * as React from 'react';
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  Layers,
  AlertTriangle,
  HardDrive,
  ArrowUp,
  ArrowDown,
  ArrowUpDown
} from 'lucide-react';
import { cn } from '../lib/utils';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchRooms, fetchDevices, fetchAlerts } from '../lib/api'
import { POLL_MS, STALE_MS } from '../lib/constants';
import type { DeviceResponse } from '../types/api';
import { RoomCard, RoomCardSkeleton } from '../components/RoomCard';
import type { RoomCardStatus } from '../components/RoomCard';
import { StatusDot } from '../components/StatusDot';

const dashboardSearchSchema = z.object({
  sortBy: z.enum(['name', 'type', 'room', 'devId', 'status', 'created']).optional().catch('name'),
  sortOrder: z.enum(['asc', 'desc']).optional().catch('asc'),
});

export const Route = createFileRoute('/')({
  validateSearch: (search) => dashboardSearchSchema.parse(search),
  component: DashboardPage,
});

function DashboardPage() {
  const navigate = useNavigate();
  const { sortBy, sortOrder } = Route.useSearch();

  const { data: rooms = [], status: roomsStatus } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
  });

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    placeholderData: keepPreviousData,
  });

  const { data: alertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ limit: 100 }),
    queryFn: () => fetchAlerts({ limit: 100 }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    placeholderData: keepPreviousData,
  });

  const { unresolvedAlerts, criticalCount, warningCount } = React.useMemo(() => {
    const alerts = alertsData?.alerts || [];
    let crit = 0;
    let warn = 0;
    const unresolved: typeof alerts = [];
    for (const a of alerts) {
      if (!a.resolved_at) {
        unresolved.push(a);
        if (a.severity === 'critical') crit++;
        else if (a.severity === 'warning') warn++;
      }
    }
    return { unresolvedAlerts: unresolved, criticalCount: crit, warningCount: warn };
  }, [alertsData?.alerts]);

  const getRoomStatus = React.useCallback((roomId: string): RoomCardStatus => {
    const roomAlerts = unresolvedAlerts.filter((a) => a.room_id === roomId);
    if (roomAlerts.some((a) => a.severity === 'critical')) return 'Critical';
    if (roomAlerts.some((a) => a.severity === 'warning')) return 'Warning';
    const roomDevs = devices.filter((d) => d.room_id === roomId);
    if (roomDevs.length > 0 && roomDevs.every((d) => !d.is_active)) return 'Offline';
    return 'Normal';
  }, [unresolvedAlerts, devices]);

  const renderHeader = React.useCallback((
    label: string,
    key: 'name' | 'type' | 'room' | 'devId' | 'status' | 'created'
  ): React.ReactNode => {
    const isActive = sortBy === key;
    return (
      <th key={key} className="px-6 py-4">
        <Link
          to="."
          search={(prev) => ({
            ...prev,
            sortBy: key,
            sortOrder: isActive ? (prev.sortOrder === 'asc' ? 'desc' : 'asc') : 'asc',
          })}
          className="group inline-flex items-center gap-1.5 hover:text-indigo-400 transition-colors duration-200 ease-out cursor-pointer select-none active:scale-[0.97]"
        >
          <span>{label}</span>
          {isActive ? (
            sortOrder === 'asc' ? (
              <ArrowUp className="h-3.5 w-3.5 text-indigo-400" />
            ) : (
              <ArrowDown className="h-3.5 w-3.5 text-indigo-400" />
            )
          ) : (
            <ArrowUpDown className="h-3.5 w-3.5 text-zinc-500 opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
          )}
        </Link>
      </th>
    );
  }, [sortBy, sortOrder]);

  const sortedDevices = React.useMemo(() => {
    const copy = [...devices];
    copy.sort((a: DeviceResponse, b: DeviceResponse) => {
      let comparison = 0;
      switch (sortBy) {
        case 'name':
          comparison = (a.dev_name || a.dev_id).toLowerCase().localeCompare((b.dev_name || b.dev_id).toLowerCase());
          break;
        case 'type':
          comparison = (a.dev_type || '').toLowerCase().localeCompare((b.dev_type || '').toLowerCase());
          break;
        case 'room': {
          const nameA = (rooms.find((r) => r.id === a.room_id)?.name || 'Unpaired').toLowerCase();
          const nameB = (rooms.find((r) => r.id === b.room_id)?.name || 'Unpaired').toLowerCase();
          comparison = nameA.localeCompare(nameB);
          break;
        }
        case 'devId':
          comparison = a.dev_id.toLowerCase().localeCompare(b.dev_id.toLowerCase());
          break;
        case 'status': {
          const statA = a.is_active ? 'active' : 'pending';
          const statB = b.is_active ? 'active' : 'pending';
          comparison = statA.localeCompare(statB);
          break;
        }
        case 'created': {
          const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
          const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
          comparison = timeA - timeB;
          break;
        }
        default:
          comparison = 0;
      }
      return sortOrder === 'asc' ? comparison : -comparison;
    });
    return copy;
  }, [devices, rooms, sortBy, sortOrder]);

  const isInitialLoading = roomsStatus === 'pending';

  return (
    <div className="space-y-8">
      {/* Overview stats bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-400 font-semibold uppercase tracking-wider mb-1">Total Rooms</p>
            <h3 className="text-2xl font-bold text-zinc-100">{rooms.length}</h3>
          </div>
          <Layers className="h-8 w-8 text-indigo-500/40" />
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-400 font-semibold uppercase tracking-wider mb-1">Active Devices</p>
            <h3 className="text-2xl font-bold text-zinc-100">
              {devices.filter((d) => d.is_active).length}
            </h3>
          </div>
          <HardDrive className="h-8 w-8 text-indigo-500/40" />
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-400 font-semibold uppercase tracking-wider mb-1">Warning Alerts</p>
            <h3 className="text-2xl font-bold text-amber-400">
              {warningCount}
            </h3>
          </div>
          <AlertTriangle className="h-8 w-8 text-amber-500/40" />
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-400 font-semibold uppercase tracking-wider mb-1">Critical Alerts</p>
            <h3 className="text-2xl font-bold text-red-500">
              {criticalCount}
            </h3>
          </div>
          <AlertTriangle className="h-8 w-8 text-red-500/40" />
        </div>
      </div>

      {/* Rooms Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Rooms</h3>
          {!isInitialLoading && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-400" role="status">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" aria-hidden="true" />
              <span>Live</span>
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {isInitialLoading &&
            Array.from({ length: 6 }, (_, i) => <RoomCardSkeleton key={`room-skeleton-${i}`} />)}
          {!isInitialLoading &&
            rooms.map((room, i) => {
              const status = getRoomStatus(room.id);
              return (
                <div key={room.id} className="stagger-item" style={{ animationDelay: `${i * 60}ms` }}>
                  <RoomCard room={room} status={status} />
                </div>
              );
            })}
          {!isInitialLoading && rooms.length === 0 && (
            <div className="col-span-full bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center text-zinc-400 text-sm">
              No rooms created yet. Create a room in Settings to begin organizing devices.
            </div>
          )}
        </div>
      </div>

      {/* Node Table (Devices) */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">All Connected Nodes</h3>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-zinc-300">
              <thead className="bg-zinc-950 text-xs font-semibold uppercase tracking-wider text-zinc-400 border-b border-zinc-800">
                <tr>
                  {renderHeader('Device Name', 'name')}
                  {renderHeader('Type', 'type')}
                  {renderHeader('Room', 'room')}
                  {renderHeader('MAC / ID', 'devId')}
                  {renderHeader('Status', 'status')}
                  <th className="px-6 py-4">Thresholds</th>
                  {renderHeader('Created', 'created')}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {sortedDevices.map((device) => {
                  const room = rooms.find((r) => r.id === device.room_id);
                  const isOnline = device.status === 'online';
                  const isPending = !device.is_active || device.status === 'pending';
                  const statusLabel = isPending ? 'Pending' : isOnline ? 'Online' : 'Offline';
                  return (
                    <tr
                      key={device.dev_id}
                      onClick={() => navigate({ to: '/device/$deviceId', params: { deviceId: device.dev_name || device.dev_id } })}
                      className={cn(
                        "row-cv hover:bg-zinc-850/50 transition-colors duration-200 ease-out cursor-pointer active:scale-[0.99]",
                        !device.is_active && "opacity-60"
                      )}
                    >
                      <td className="px-6 py-4 font-semibold text-zinc-100">
                        {device.dev_name || device.dev_id}
                      </td>
                      <td className="px-6 py-4">
                        <span className="bg-zinc-800 text-zinc-300 text-xs px-2.5 py-1 rounded font-mono font-medium">
                          {device.dev_type || 'Generic'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-zinc-300 font-medium">
                        {room ? room.name : <span className="text-zinc-500 italic">Unassigned</span>}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-zinc-300">
                        {device.dev_id}
                      </td>
                      <td className="px-6 py-4">
                        <span className={cn(
                          "px-2.5 py-0.5 rounded-full text-xs font-semibold border inline-flex items-center gap-1.5",
                          isPending
                            ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                            : isOnline
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                              : "bg-zinc-800/80 text-zinc-300 border-zinc-700/50"
                        )}>
                          <StatusDot
                            tone={isPending ? 'amber' : isOnline ? 'emerald' : 'zinc'}
                            label={`Status: ${statusLabel}`}
                            variant={isOnline ? 'live' : 'idle'}
                          />
                          {statusLabel}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs font-mono text-zinc-300">
                        {device.threshold_config ? (
                          <span>
                            {device.dev_type === 'ATS'
                              ? `W: ${device.threshold_config.warning}V / C: ${device.threshold_config.critical}V`
                              : `W: ${device.threshold_config.warning}°C / C: ${device.threshold_config.critical}°C`}
                          </span>
                        ) : (
                          <span className="text-zinc-400">Default</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-400">
                        {device.created_at ? new Date(device.created_at).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) + ' WIB' : '—'}
                      </td>
                    </tr>
                  );
                })}
                {sortedDevices.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-6 py-8 text-center text-zinc-400 text-sm">
                      No devices found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

