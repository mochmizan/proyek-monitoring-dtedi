import { createFileRoute, redirect } from '@tanstack/react-router';
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
import { fetchCurrentUser, fetchHubs, approveHub, revokeHub } from '../lib/api'
import { POLL_MS, STALE_MS } from '../lib/constants';
import { cn } from '../lib/utils';
import { StatusDot } from '../components/StatusDot';
import { FreshnessBadge } from '../components/FreshnessBadge';
import type { HubResponse, HubDeviceSummary } from '../types/api';

export const Route = createFileRoute('/hubs')({
  beforeLoad: async ({ context }) => {
    try {
      const user = await context.queryClient.ensureQueryData({
        queryKey: queryKeys.auth.me(),
        queryFn: fetchCurrentUser,
      });
      if (!user) {
        throw redirect({ to: '/login' });
      }
    } catch {
      throw redirect({ to: '/login' });
    }
  },
  component: HubsPage,
});

function DeviceTypeIcon({ devType }: { devType?: string | null }) {
  if (devType === 'AC') return <Snowflake className="size-3.5 text-sky-400" />;
  if (devType === 'TS') return <Thermometer className="size-3.5 text-amber-400" />;
  if (devType === 'ATS') return <Zap className="size-3.5 text-indigo-400" />;
  return <HelpCircle className="size-3.5 text-muted-foreground" />;
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
    <div className="rounded-xl bg-card border p-5 flex flex-col justify-between">
      <div>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h4 className="font-bold text-foreground truncate">{hub.hub_name}</h4>
            <p className="font-mono text-xs text-muted-foreground truncate">
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

        <ul className="mt-4 flex flex-col gap-2">
          {hub.devices.map((dev) => (
            <HubDeviceRow key={dev.dev_id} dev={dev} />
          ))}
          {hub.devices.length === 0 && (
            <li className="text-xs text-muted-foreground italic">No connected devices</li>
          )}
        </ul>
      </div>

      <div className="mt-4 pt-3 border-t flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          {hub.device_count} device{hub.device_count === 1 ? '' : 's'}
        </span>
        {isAdmin && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => onApprove(hub.hub_id)}
              disabled={online}
              title={online ? 'Hub already active' : 'Approve hub'}
              className="px-2 py-1 bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-400 border border-emerald-800/40 rounded text-[10px] font-semibold cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Approve
            </button>
            <button
              onClick={() => onRevoke(hub.hub_id)}
              title="Revoke hub access"
              className="px-2 py-1 bg-red-950/30 hover:bg-red-950/60 text-red-400 border border-red-900/30 rounded text-[10px] font-semibold cursor-pointer"
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
        <span className="text-foreground font-medium truncate">
          {dev.dev_name || dev.dev_id}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground shrink-0">
          {dev.dev_type || '?'}
        </span>
      </span>
      <span
        className={cn(
          'tabular-nums shrink-0 font-medium',
          fresh ? 'text-emerald-400' : 'text-muted-foreground'
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

  const {
    data: hubs = [],
    isPending,
    dataUpdatedAt,
  } = useQuery({
    queryKey: queryKeys.hubs.list(),
    queryFn: fetchHubs,
    refetchInterval: POLL_MS,
    staleTime: STALE_MS,
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
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Edge Hubs</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Live presence and device roster for every registered edge gateway.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
          <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold text-emerald-400">Live</span>
        </div>
      </div>

      {actionError && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs p-3 rounded flex items-center gap-2">
          <AlertTriangle className="size-4 flex-shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {isPending ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-xl bg-card border p-5 animate-pulse flex flex-col gap-3">
              <div className="h-4 w-1/2 bg-muted rounded" />
              <div className="h-3 w-1/3 bg-muted rounded" />
              <div className="flex flex-col gap-2 pt-2">
                <div className="h-3 w-full bg-muted/70 rounded" />
                <div className="h-3 w-5/6 bg-muted/70 rounded" />
              </div>
              <div className="h-3 w-1/4 bg-muted rounded pt-1" />
            </div>
          ))}
        </div>
      ) : hubs.length === 0 ? (
        <div className="bg-card border rounded-xl p-10 flex flex-col items-center justify-center gap-3 text-center">
          <Radio className="size-8 text-muted-foreground" />
          <p className="text-sm font-semibold text-foreground">No hubs paired yet</p>
          <p className="text-xs text-muted-foreground max-w-xs">
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
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <FreshnessBadge dataUpdatedAt={dataUpdatedAt} />
            <span className="flex items-center gap-1.5">
              <RefreshCw className={cn('size-3', isPending && 'animate-spin')} />
              Polling every 3s
            </span>
          </div>
        </>
      )}

      {(approveMutation.isPending || revokeMutation.isPending) && (
        <div className="fixed bottom-6 right-6 bg-card border rounded-lg px-4 py-3 flex items-center gap-2 shadow-2xl">
          <Loader2 className="size-4 animate-spin text-primary" />
          <span className="text-xs text-foreground">Applying hub action...</span>
        </div>
      )}
    </div>
  );
}
