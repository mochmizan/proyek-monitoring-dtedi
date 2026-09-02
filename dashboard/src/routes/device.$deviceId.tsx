import { createFileRoute, useRouter } from '@tanstack/react-router';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ArrowLeft, ShieldAlert, RefreshCw, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { z } from 'zod';
import { cn } from '../lib/utils';
import { queryKeys } from '../lib/queryKeys';
import { fetchDevice, fetchRooms, fetchAlerts, fetchCurrentUser } from '../lib/api';
import { POLL_MS } from '../lib/constants';
import { HistoryChart } from '../components/device/HistoryChart';
import { DeviceControls } from '../components/device/Controls';
import { useDeviceHistory } from '../hooks/useDeviceHistory';
import { formatAlertReading } from '../lib/formatAlert';

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
  const [copiedMac, setCopiedMac] = useState(false);

  const { data: currentUser } = useQuery({ queryKey: queryKeys.auth.me(), queryFn: fetchCurrentUser });
  const { data: device, isLoading: isLoadingDevice, isFetching: isFetchingDevice } = useQuery({
    queryKey: queryKeys.devices.detail(deviceId),
    queryFn: () => fetchDevice(deviceId),
    staleTime: 60_000,
    refetchInterval: false,
    refetchOnWindowFocus: true,
  });

  const canonicalDevId = device?.dev_id || deviceId;

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    placeholderData: keepPreviousData,
  });
  const { data: deviceAlertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ device: canonicalDevId }),
    queryFn: () => fetchAlerts({ device: canonicalDevId }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    placeholderData: keepPreviousData,
  });
  const {
    data: historyData,
    isFetching: isFetchingHistory,
    refetch: refetchHistory,
    dataUpdatedAt: historyUpdatedAt,
  } = useDeviceHistory(canonicalDevId, timeRange);

  const room = device ? rooms.find((r) => r.id === device.room_id) : null;
  const role = currentUser?.role || 'viewer';

  const handleCopyMac = async (mac: string) => {
    try {
      await navigator.clipboard.writeText(mac);
      setCopiedMac(true);
      setTimeout(() => setCopiedMac(false), 2000);
    } catch {
      // ignore clipboard error
    }
  };

  if (isLoadingDevice) {
    return (
      <div className="space-y-6">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center"><p className="text-zinc-400">Loading device details...</p></div>
      </div>
    );
  }

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

  const alerts = deviceAlertsData?.alerts || [];
  const historyPoints = historyData?.points || [];
  const displayName = device.dev_name || device.dev_id;
  const isOnline = device.status === 'online';
  const isPending = !device.is_active || device.status === 'pending';

  return (
    <div className="space-y-8">
      {/* Header & Breadcrumbs */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.navigate({ to: '/' })}
            className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-md text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
            aria-label="Back to Dashboard"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">{displayName}</h1>
            <div className="flex flex-wrap items-center gap-2 mt-2 text-xs">
              {/* Type Chip */}
              <span className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-400 font-medium">
                Type: <strong className="text-zinc-200 font-medium">{device.dev_type || 'Generic'}</strong>
              </span>

              {/* Room Chip */}
              <span className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-400 font-medium">
                Room: <strong className="text-zinc-200 font-medium">{(device as any).room_name || room?.name || 'Unassigned'}</strong>
              </span>

              {/* Hub ID Chip */}
              <span className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-400 font-medium">
                Hub: <strong className="text-zinc-200 font-mono font-medium">{device.hub_id || 'Direct'}</strong>
              </span>

              {/* Registered Date Chip */}
              <span className="px-2 py-0.5 rounded bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-400 font-medium">
                Registered: <strong className="text-zinc-200 font-medium">{device.created_at ? new Date(device.created_at).toLocaleDateString('id-ID', { timeZone: 'Asia/Jakarta' }) : '—'}</strong>
              </span>

              {/* MAC Copy Button */}
              <button
                type="button"
                onClick={() => void handleCopyMac(device.dev_id)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 font-mono text-[11px] text-zinc-300 hover:text-zinc-100 transition-colors cursor-pointer"
                title="Click to copy MAC address"
              >
                <span>MAC: {device.dev_id}</span>
                {copiedMac ? (
                  <Check className="h-3 w-3 text-emerald-400 ml-0.5" />
                ) : (
                  <Copy className="h-3 w-3 text-zinc-500 hover:text-zinc-300 ml-0.5" />
                )}
              </button>

              {/* Status Badge */}
              <span
                className={cn(
                  "px-2.5 py-0.5 rounded-full text-xs font-semibold border inline-flex items-center gap-1.5",
                  isPending
                    ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                    : isOnline
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-zinc-800/80 text-zinc-400 border-zinc-700/50"
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    isPending ? "bg-amber-400" : isOnline ? "bg-emerald-400 animate-pulse" : "bg-zinc-500"
                  )}
                />
                {isPending ? 'Pending Approval' : isOnline ? 'Online' : 'Offline'}
              </span>
            </div>
          </div>
        </div>
        {isFetchingDevice && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-zinc-900 px-3 py-1.5 rounded-full border border-zinc-800">
            <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />
            <span>Refreshing</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-6">
          <HistoryChart
            points={historyPoints}
            devType={device.dev_type || 'TS'}
            timeRange={timeRange}
            setTimeRange={setTimeRange}
            warningThresholdVal={device.threshold_config ? device.threshold_config.warning : null}
            criticalThresholdVal={device.threshold_config ? device.threshold_config.critical : null}
            isFetching={isFetchingHistory}
            onRefresh={() => { void refetchHistory(); }}
            dataUpdatedAt={historyUpdatedAt}
          />
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-indigo-400" />
              <span>Device Alert Log</span>
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800">
                  <tr>
                    <th className="px-4 py-3">Severity</th>
                    <th className="px-4 py-3">Metric / Message</th>
                    <th className="px-4 py-3">Value</th>
                    <th className="px-4 py-3">Timestamp</th>
                    <th className="px-4 py-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {alerts.map((a) => (
                    <tr key={a.event_id} className="hover:bg-zinc-800/50">
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "px-2 py-0.5 rounded text-[10px] font-bold uppercase",
                            a.severity === 'critical' ? "bg-red-500/20 text-red-400" : "bg-amber-500/20 text-amber-400"
                          )}
                        >
                          {a.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-zinc-200">
                        {a.message || (
                          a.metric === 'battery'
                            ? 'Starter Battery Undervoltage'
                            : a.metric === 'emergency'
                              ? 'ATS Emergency State'
                              : a.metric === 'connectivity' || a.metric === 'presence'
                                ? 'Connection Status'
                                : a.metric || 'Threshold Breach'
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono">
                        {formatAlertReading(a)}
                      </td>
                      <td className="px-4 py-3 text-zinc-500">
                        {new Date(a.timestamp).toLocaleString('id-ID', {
                          timeZone: 'Asia/Jakarta',
                          year: 'numeric',
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                          hour12: false,
                        }) + ' WIB'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "px-2 py-0.5 rounded text-[10px] font-semibold",
                            a.resolved_at ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                          )}
                        >
                          {a.resolved_at ? 'Resolved' : 'Active'}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {alerts.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-center text-zinc-500 text-xs">
                        No alerts recorded for this device.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="space-y-6">
          <DeviceControls key={canonicalDevId} device={device} role={role} />
        </div>
      </div>
    </div>
  );
}
