import { createFileRoute, Link, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { 
  Layers, 
  AlertTriangle, 
  HardDrive, 
  ArrowUp, 
  ArrowDown, 
  ArrowUpDown,
  RefreshCw
} from 'lucide-react';
import { cn } from '../lib/utils';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchRooms, fetchDevices, fetchAlerts } from '../lib/api';
import type { DeviceResponse } from '../types/api';

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

  const { data: rooms = [], isFetching: isFetchingRooms } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const { data: devices = [], isFetching: isFetchingDevices } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const { data: alertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ limit: 100 }),
    queryFn: () => fetchAlerts({ limit: 100 }),
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const unresolvedAlerts = (alertsData?.alerts || []).filter((a) => !a.resolved_at);
  const criticalCount = unresolvedAlerts.filter((a) => a.severity === 'critical').length;
  const warningCount = unresolvedAlerts.filter((a) => a.severity === 'warning').length;

  const getRoomStatus = (roomId: string): 'Normal' | 'Warning' | 'Critical' | 'Offline' => {
    const roomAlerts = unresolvedAlerts.filter((a) => a.room_id === roomId);
    if (roomAlerts.some((a) => a.severity === 'critical')) return 'Critical';
    if (roomAlerts.some((a) => a.severity === 'warning')) return 'Warning';
    const roomDevs = devices.filter((d) => d.room_id === roomId);
    if (roomDevs.length > 0 && roomDevs.every((d) => !d.is_active)) return 'Offline';
    return 'Normal';
  };

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'Normal': return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'Warning': return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      case 'Critical': return 'bg-red-500/10 text-red-400 border-red-500/20';
      default: return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
    }
  };

  const renderHeader = (
    label: string, 
    key: 'name' | 'type' | 'room' | 'devId' | 'status' | 'created'
  ): React.ReactNode => {
    const isActive = sortBy === key;
    return (
      <th className="px-6 py-4">
        <Link
          to="."
          search={(prev) => ({
            ...prev,
            sortBy: key,
            sortOrder: isActive ? (prev.sortOrder === 'asc' ? 'desc' : 'asc') : 'asc',
          })}
          className="group inline-flex items-center gap-1.5 hover:text-indigo-400 transition-colors cursor-pointer select-none"
        >
          <span>{label}</span>
          {isActive ? (
            sortOrder === 'asc' ? (
              <ArrowUp className="h-3.5 w-3.5 text-indigo-400" />
            ) : (
              <ArrowDown className="h-3.5 w-3.5 text-indigo-400" />
            )
          ) : (
            <ArrowUpDown className="h-3.5 w-3.5 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity" />
          )}
        </Link>
      </th>
    );
  };

  const sortedDevices = [...devices].sort((a: DeviceResponse, b: DeviceResponse) => {
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

  const isPolling = isFetchingRooms || isFetchingDevices;

  return (
    <div className="space-y-8">
      {/* Overview stats bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider mb-1">Total Rooms</p>
            <h3 className="text-2xl font-bold text-zinc-100">{rooms.length}</h3>
          </div>
          <Layers className="h-8 w-8 text-indigo-500/40" />
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider mb-1">Active Devices</p>
            <h3 className="text-2xl font-bold text-zinc-100">
              {devices.filter((d) => d.is_active).length}
            </h3>
          </div>
          <HardDrive className="h-8 w-8 text-indigo-500/40" />
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider mb-1">Warning Alerts</p>
            <h3 className="text-2xl font-bold text-amber-400">
              {warningCount}
            </h3>
          </div>
          <AlertTriangle className="h-8 w-8 text-amber-500/40" />
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex items-center justify-between">
          <div>
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider mb-1">Critical Alerts</p>
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
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">Rooms</h3>
          {isPolling && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />
              <span>Syncing</span>
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {rooms.map((room) => {
            const status = getRoomStatus(room.id);
            return (
              <Link
                key={room.id}
                to="/room/$roomId"
                params={{ roomId: room.id }}
                search={{}}
                className="bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 hover:border-zinc-700 rounded-lg p-5 flex flex-col justify-between transition-all duration-300 group cursor-pointer shadow-md hover:shadow-lg hover:-translate-y-0.5 min-h-[140px]"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h4 className="font-bold text-zinc-100 group-hover:text-indigo-400 transition-colors">
                      {room.name}
                    </h4>
                    <div className="flex flex-col gap-0.5 mt-1">
                      <span className="text-xs text-zinc-500 font-medium">{room.device_count} devices assigned</span>
                      {room.hub_id && (
                        <span className="text-[10px] text-zinc-500 font-mono">Hub: {room.hub_id}</span>
                      )}
                    </div>
                  </div>
                  <div className={cn("px-2.5 py-1 rounded-full border text-xs font-semibold flex items-center gap-1.5", getStatusColor(status))}>
                    <span className={cn(
                      "h-1.5 w-1.5 rounded-full animate-pulse",
                      status === 'Normal' && 'bg-emerald-400',
                      status === 'Warning' && 'bg-amber-400',
                      status === 'Critical' && 'bg-red-400',
                      status === 'Offline' && 'bg-zinc-400'
                    )} />
                    <span>{status}</span>
                  </div>
                </div>

                <div className="flex items-baseline justify-between mt-auto pt-2 border-t border-zinc-800/60">
                  <span className="text-xs text-zinc-500 font-medium">Floor Plan</span>
                  <span className="text-xs font-medium text-indigo-400">
                    {room.floor_plan_image_path ? 'Available' : 'None'}
                  </span>
                </div>
              </Link>
            );
          })}
          {rooms.length === 0 && (
            <div className="col-span-full bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center text-zinc-500 text-sm">
              No rooms created yet. Create a room in Settings to begin organizing devices.
            </div>
          )}
        </div>
      </div>

      {/* Node Table (Devices) */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-500">All Connected Nodes</h3>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-zinc-300">
              <thead className="bg-zinc-950 text-xs font-semibold uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
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
                  return (
                    <tr 
                      key={device.dev_id} 
                      onClick={() => navigate({ to: '/device/$deviceId', params: { deviceId: device.dev_id } })}
                      className={cn(
                        "hover:bg-zinc-850/50 transition-colors cursor-pointer",
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
                      <td className="px-6 py-4 text-zinc-400 font-medium">
                        {room ? room.name : <span className="text-zinc-600 italic">Unassigned</span>}
                      </td>
                      <td className="px-6 py-4 font-mono text-xs text-zinc-400">
                        {device.dev_id}
                      </td>
                      <td className="px-6 py-4">
                        {(() => {
                          const isOnline = device.status === 'online';
                          const isPending = !device.is_active || device.status === 'pending';
                          return (
                            <span className={cn(
                              "px-2.5 py-0.5 rounded-full text-xs font-semibold border inline-flex items-center gap-1.5",
                              isPending
                                ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                : isOnline
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                  : "bg-zinc-800/80 text-zinc-400 border-zinc-700/50"
                            )}>
                              <span className={cn(
                                "h-1.5 w-1.5 rounded-full",
                                isPending 
                                  ? "bg-amber-400" 
                                  : isOnline 
                                    ? "bg-emerald-400 animate-pulse" 
                                    : "bg-zinc-500"
                              )} />
                              {isPending ? 'Pending' : isOnline ? 'Online' : 'Offline'}
                            </span>
                          );
                        })()}
                      </td>
                      <td className="px-6 py-4 text-xs font-mono text-zinc-400">
                        {device.threshold_config ? (
                          <span>
                            W: {device.threshold_config.warning}°C / C: {device.threshold_config.critical}°C
                          </span>
                        ) : (
                          <span className="text-zinc-600">Default</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-xs text-zinc-500">
                        {device.created_at ? new Date(device.created_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  );
                })}
                {sortedDevices.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-6 py-8 text-center text-zinc-500 text-sm">
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
