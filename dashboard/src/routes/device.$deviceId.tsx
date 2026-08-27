import { createFileRoute, useRouter } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Thermometer, Zap, Wind, ShieldAlert, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { z } from 'zod';
import { cn } from '../lib/utils';
import { queryKeys } from '../lib/queryKeys';
import { fetchDevices, fetchRooms, fetchAlerts, fetchCurrentUser } from '../lib/api';
import { POLL_MS } from '../lib/constants';
import { HistoryChart } from '../components/device/HistoryChart';
import { DeviceControls } from '../components/device/Controls';
import { useDeviceHistory } from '../hooks/useDeviceHistory';

const deviceSearchSchema = z.object({
  range: z.enum(['6h', '24h', '7d', '30d']).catch('24h').optional(),
});

export const Route = createFileRoute('/device/$deviceId')({
  validateSearch: (search) => deviceSearchSchema.parse(search),
  component: DeviceDetailPage,
});

function DeviceDetailPage() {
  const { deviceId } = Route.useParams();
  const { range } = Route.useSearch();
  const router = useRouter();
  const [timeRange, setTimeRange] = useState<'6h' | '24h' | '7d' | '30d'>(range ?? '24h');

  const { data: currentUser } = useQuery({ queryKey: queryKeys.auth.me(), queryFn: fetchCurrentUser });
  const { data: devices = [], isFetching: isFetchingDevices } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  const { data: deviceAlertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ device: deviceId }),
    queryFn: () => fetchAlerts({ device: deviceId }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  const { data: historyData } = useDeviceHistory(deviceId, timeRange);

  const device = devices.find((d) => d.dev_id === deviceId);
  const room = device ? rooms.find((r) => r.id === device.room_id) : null;
  const role = currentUser?.role || 'viewer';

  if (!device) {
    return (
      <div className="space-y-6">
        <button onClick={() => router.navigate({ to: '/' })} className="flex items-center gap-2 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer">
          <ArrowLeft className="h-4 w-4" /><span>Back to Dashboard</span>
        </button>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center"><p className="text-zinc-400">Device '{deviceId}' not found.</p></div>
      </div>
    );
  }

  const isTS = device.dev_type === 'TS';
  const isATS = device.dev_type === 'ATS';
  const isAC = device.dev_type === 'AC' || device.dev_type === 'ACC';
  const alerts = deviceAlertsData?.alerts || [];
  const historyPoints = historyData?.points || [];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => router.navigate({ to: '/' })} className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-md text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"><ArrowLeft className="h-4 w-4" /></button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-zinc-100">{device.dev_name || device.dev_id}</h1>
              {(() => {
                const isOnline = device.status === 'online';
                const isPending = !device.is_active || device.status === 'pending';
                return (<span className={cn("px-2.5 py-0.5 rounded-full text-xs font-semibold border inline-flex items-center gap-1.5", isPending ? "bg-amber-500/10 text-amber-400 border-amber-500/20" : isOnline ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-zinc-800/80 text-zinc-400 border-zinc-700/50")}><span className={cn("h-1.5 w-1.5 rounded-full", isPending ? "bg-amber-400" : isOnline ? "bg-emerald-400 animate-pulse" : "bg-zinc-500")} />{isPending ? 'Pending Approval' : isOnline ? 'Online' : 'Offline'}</span>);
              })()}
            </div>
            <p className="text-xs text-zinc-500 mt-1 font-mono">MAC / ID: {device.dev_id} · Type: {device.dev_type || 'Generic'} · Room: {room?.name || 'Unassigned'}</p>
          </div>
        </div>
        {isFetchingDevices && <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-zinc-900 px-3 py-1.5 rounded-full border border-zinc-800"><RefreshCw className="h-3 w-3 animate-spin text-indigo-400" /><span>Polling</span></div>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <HistoryChart points={historyPoints} devType={device.dev_type || 'TS'} timeRange={timeRange} setTimeRange={setTimeRange} warningThresholdVal={device.threshold_config ? device.threshold_config.warning : null} criticalThresholdVal={device.threshold_config ? device.threshold_config.critical : null} />
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              {isTS && <Thermometer className="h-4 w-4 text-indigo-400" />}{isATS && <Zap className="h-4 w-4 text-amber-400" />}{isAC && <Wind className="h-4 w-4 text-emerald-400" />}<span>Node Information</span>
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-2 text-sm">
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800"><span className="text-[10px] text-zinc-500 uppercase font-semibold">Gateway Hub</span><p className="font-mono font-medium text-zinc-200 mt-0.5">{device.hub_id || 'Direct'}</p></div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800"><span className="text-[10px] text-zinc-500 uppercase font-semibold">Room Assignment</span><p className="font-medium text-zinc-200 mt-0.5">{room?.name || 'Unpaired'}</p></div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800"><span className="text-[10px] text-zinc-500 uppercase font-semibold">Registered Date</span><p className="text-xs text-zinc-300 mt-0.5">{device.created_at ? new Date(device.created_at).toLocaleDateString() : '—'}</p></div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800"><span className="text-[10px] text-zinc-500 uppercase font-semibold">Map Coordinate</span><p className="font-mono text-xs text-zinc-300 mt-0.5">{device.marker_x !== null && device.marker_y !== null ? `(${device.marker_x}%, ${device.marker_y}%)` : 'Unplaced'}</p></div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800"><span className="text-[10px] text-zinc-500 uppercase font-semibold">Warning Level</span><p className="font-mono font-medium text-amber-400 mt-0.5">{device.threshold_config ? `${device.threshold_config.warning}°C` : 'Default'}</p></div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800"><span className="text-[10px] text-zinc-500 uppercase font-semibold">Critical Level</span><p className="font-mono font-medium text-red-400 mt-0.5">{device.threshold_config ? `${device.threshold_config.critical}°C` : 'Default'}</p></div>
            </div>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-indigo-400" /><span>Device Alert Log</span></h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800"><tr><th className="px-4 py-3">Severity</th><th className="px-4 py-3">Metric / Message</th><th className="px-4 py-3">Value</th><th className="px-4 py-3">Timestamp</th><th className="px-4 py-3">Status</th></tr></thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {alerts.map((a) => (<tr key={a.event_id} className="hover:bg-zinc-800/50"><td className="px-4 py-3"><span className={cn("px-2 py-0.5 rounded text-[10px] font-bold uppercase", a.severity === 'critical' ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400")}>{a.severity}</span></td><td className="px-4 py-3 font-medium text-zinc-200">{a.message || a.metric || 'Threshold Breach'}</td><td className="px-4 py-3 font-mono">{a.value !== null && a.value !== undefined ? a.value : '—'}</td><td className="px-4 py-3 text-zinc-500">{new Date(a.timestamp).toLocaleString()}</td><td className="px-4 py-3"><span className={cn("px-2 py-0.5 rounded text-[10px] font-semibold", a.resolved_at ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400")}>{a.resolved_at ? 'Resolved' : 'Active'}</span></td></tr>))}
                  {alerts.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-zinc-500 text-xs">No alerts recorded for this device.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="space-y-6"><DeviceControls device={device} role={role} /></div>
      </div>
    </div>
  );
}
