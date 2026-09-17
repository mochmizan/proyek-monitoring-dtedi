import { createFileRoute } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  Snowflake,
  Thermometer,
  Zap,
  HelpCircle,
  Loader2,
  AlertTriangle,
  RefreshCw,
  Radio,
} from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import { fetchCurrentUser, fetchHubs, approveHub, revokeHub } from '../lib/api';
import { POLL_TIER3_PRESENCE_MS, STALE_TIER3_PRESENCE_MS } from '../lib/constants';
import { useJitteredInterval } from '../lib/jitter';
import { cn } from '../lib/utils';
import { StatusDot } from '../components/StatusDot';
import { FreshnessBadge } from '../components/FreshnessBadge';
import type { HubResponse, HubDeviceSummary } from '../types/api';

export const Route = createFileRoute('/hubs')({
  component: HubsPage,
});

function DeviceTypeIcon({ devType }: { devType?: string | null }) {
  if (devType === 'AC') return <Snowflake className="h-3.5 w-3.5 text-sky-400" />;
  if (devType === 'TS') return <Thermometer className="h-3.5 w-3.5 text-amber-400" />;
  if (devType === 'ATS') return <Zap className="h-3.5 w-3.5 text-indigo-400" />;
  return <HelpCircle className="h-3.5 w-3.5 text-zinc-500" />;
}

function formatRelative(lastSeen?: string | null): string {
  if (!lastSeen) return '—';
  const ageMs = Date.now() - new Date(lastSeen).getTime();
  if (!Number.isFinite(ageMs)) return '—';
  const ageSec = Math.max(0, Math.round(ageMs / 1000));
  if (ageSec < 60) return `${ageSec}s ago`;
  const ageMin = Math.floor(ageSec / 60);
  if (ageMin < 60) return `${ageMin}m ago`;
  const ageHr = Math.floor(ageMin / 60);
  return `${ageHr}h ago`;
}

function HubCard({
  hub,
  isAdmin,
  onApprove,
  onRevoke,
}: {
  hub: HubResponse;
  isAdmin: boolean;
  onApprove: (hubId: string) => void;
  onRevoke: (hubId: string) => void;
}) {
  const online = hub.status === 'online';

  return (
    <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-5 flex flex-col justify-between">
      <div>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h4 className="font-bold text-zinc-100 truncate">{hub.hub_name}</h4>
            <p className="font-mono text-xs text-zinc-500 truncate">
              {hub.hub_id}
              {hub.room ? ` · ${hub.room}` : ''}
            </p>
          </div>
          <StatusDot
            tone={online ? 'emerald' : 'red'}
            label={online ? 'Online' : 'Offline'}
            pulse={online}
            className="mt-1.5"
          />
        </div>

        <ul className="mt-4 space-y-2">
          {hub.devices.map((dev) => (
            <HubDeviceRow key={dev.dev_id} dev={dev} />
          ))}
          {hub.devices.length === 0 && (
            <li className="text-xs text-zinc-600 italic">No connected devices</li>
          )}
        </ul>
      </div>

      <div className="mt-4 pt-3 border-t border-zinc-800 flex items-center justify-between">
        <span className="text-xs font-medium text-zinc-400">
          {hub.device_count} device{hub.device_count === 1 ? '' : 's'}
        </span>
        {isAdmin && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => onApprove(hub.hub_id)}
              disabled={hub.is_active ?? online}
              title={(hub.is_active ?? online) ? 'Hub already active' : 'Approve hub'}
              className="px-2 py-1 bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-400 border border-emerald-800/40 rounded text-[10px] font-semibold cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Approve
            </button>
            <button
              onClick={() => onRevoke(hub.hub_id)}
              disabled={hub.is_active === false}
              title="Revoke hub access"
              className="px-2 py-1 bg-red-950/30 hover:bg-red-950/60 text-red-400 border border-red-900/30 rounded text-[10px] font-semibold cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Revoke
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function HubDeviceRow({ dev }: { dev: HubDeviceSummary }) {
  const fresh = dev.last_seen
    ? Date.now() - new Date(dev.last_seen).getTime() <= 25_000
    : false;

  return (
    <li className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-2 min-w-0">
        <DeviceTypeIcon devType={dev.dev_type} />
        <span className="text-zinc-300 font-medium truncate">
          {dev.dev_name || dev.dev_id}
        </span>
        <span className="font-mono text-[10px] text-zinc-500 shrink-0">
          {dev.dev_type || '?'}
        </span>
      </span>
      <span
        className={cn(
          'tabular-nums shrink-0 font-medium',
          fresh ? 'text-emerald-400' : 'text-zinc-500'
        )}
      >
        {formatRelative(dev.last_seen)}
      </span>
    </li>
  );
}

function HubsPage() {
  const queryClient = useQueryClient();

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchCurrentUser,
    staleTime: 60000,
  });
  const isAdmin = (currentUser?.role || 'viewer') === 'admin';
  const hubsPollInterval = useJitteredInterval(POLL_TIER3_PRESENCE_MS);

  const {
    data: hubs = [],
    isPending,
    dataUpdatedAt,
  } = useQuery({
    queryKey: queryKeys.hubs.list(),
    queryFn: fetchHubs,
    refetchInterval: hubsPollInterval,
    refetchIntervalInBackground: false,
    staleTime: STALE_TIER3_PRESENCE_MS,
  });

  const [actionError, setActionError] = useState<string | null>(null);

  const invalidateHubs = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.hubs.all });
  };

  const approveMutation = useMutation({
    mutationFn: approveHub,
    onSuccess: invalidateHubs,
    onError: (err: Error) => setActionError(err.message),
  });

  const revokeMutation = useMutation({
    mutationFn: revokeHub,
    onSuccess: invalidateHubs,
    onError: (err: Error) => setActionError(err.message),
  });

  const handleApprove = (hubId: string) => {
    setActionError(null);
    approveMutation.mutate(hubId);
  };

  const handleRevoke = (hubId: string) => {
    if (!window.confirm(`Revoke access for hub "${hubId}"? The hub will be rejected until re-approved.`)) {
      return;
    }
    setActionError(null);
    revokeMutation.mutate(hubId);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Edge Hubs</h1>
          <p className="text-xs text-zinc-500 mt-1">
            Live presence and device roster for every registered edge gateway.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold text-emerald-400">Live</span>
        </div>
      </div>

      {actionError && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {isPending ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl bg-zinc-900 border border-zinc-800 p-5 animate-pulse space-y-3">
              <div className="h-4 w-1/2 bg-zinc-800 rounded" />
              <div className="h-3 w-1/3 bg-zinc-800 rounded" />
              <div className="space-y-2 pt-2">
                <div className="h-3 w-full bg-zinc-800/70 rounded" />
                <div className="h-3 w-5/6 bg-zinc-800/70 rounded" />
              </div>
              <div className="h-3 w-1/4 bg-zinc-800 rounded pt-1" />
            </div>
          ))}
        </div>
      ) : hubs.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-10 flex flex-col items-center justify-center gap-3 text-center">
          <Radio className="h-8 w-8 text-zinc-600" />
          <p className="text-sm font-semibold text-zinc-300">No hubs paired yet</p>
          <p className="text-xs text-zinc-500 max-w-xs">
            Power on an edge gateway and complete its bootstrap pairing — it will appear here automatically for admin approval.
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {hubs.map((hub) => (
              <HubCard
                key={hub.hub_id}
                hub={hub}
                isAdmin={isAdmin}
                onApprove={handleApprove}
                onRevoke={handleRevoke}
              />
            ))}
          </div>
          <div className="flex items-center justify-between text-xs text-zinc-500">
            <FreshnessBadge dataUpdatedAt={dataUpdatedAt} />
            <span className="flex items-center gap-1.5">
              <RefreshCw className={cn('h-3 w-3', isPending && 'animate-spin')} />
              Polling every 3s
            </span>
          </div>
        </>
      )}

      {(approveMutation.isPending || revokeMutation.isPending) && (
        <div className="fixed bottom-6 right-6 bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-3 flex items-center gap-2 shadow-2xl">
          <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
          <span className="text-xs text-zinc-300">Applying hub action...</span>
        </div>
      )}
    </div>
  );
}
