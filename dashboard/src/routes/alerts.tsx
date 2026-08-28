import { createFileRoute } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { useState, useRef, useEffect } from 'react';
import { cn } from '../lib/utils';
import { ChevronDown, Check, RefreshCw, ShieldAlert } from 'lucide-react';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchAlerts, fetchRooms, fetchDevices } from '../lib/api'
import { POLL_MS } from '../lib/constants';

const alertsSearchSchema = z.object({
  rooms: z.preprocess(
    (val) => (Array.isArray(val) ? val : typeof val === 'string' ? [val] : []),
    z.array(z.string())
  ).catch([]).optional(),
  devices: z.preprocess(
    (val) => (Array.isArray(val) ? val : typeof val === 'string' ? [val] : []),
    z.array(z.string())
  ).catch([]).optional(),
  severity: z.enum(['All', 'Warning', 'Critical', 'warning', 'critical']).catch('All').optional(),
  status: z.enum(['All', 'Open', 'Resolved', 'all', 'open', 'resolved']).catch('All').optional(),
  timeRange: z.enum(['6h', '24h', '7d', '30d']).catch('24h').optional(),
});

export const Route = createFileRoute('/alerts')({
  validateSearch: (search) => alertsSearchSchema.parse(search),
  component: AlertsPage,
});

interface MultiSelectProps {
  label: string;
  placeholder: string;
  options: { id: string; name: string }[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

function MultiSelect({ label, placeholder, options, selected, onChange }: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleOption = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((item) => item !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  const selectAll = () => {
    onChange([]);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">{label}</label>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between bg-muted border hover:border-border rounded px-3 py-2 text-foreground text-sm focus:outline-none focus:border-primary text-left transition-colors cursor-pointer"
      >
        <span className="truncate">
          {selected.length === 0 ? placeholder : `${selected.length} selected`}
        </span>
        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform duration-200", isOpen && "rotate-180")} />
      </button>

      {isOpen && (
        <div className="absolute left-0 z-50 mt-1 w-full bg-popover border rounded shadow-xl max-h-60 overflow-y-auto p-1 divide-y divide-border">
          <div className="py-1">
            <button
              type="button"
              onClick={selectAll}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-primary hover:bg-muted rounded text-left font-semibold cursor-pointer"
            >
              <div className={cn(
                "size-3.5 rounded border flex items-center justify-center bg-muted",
                selected.length === 0 && "bg-primary border-primary"
              )}>
                {selected.length === 0 && <Check className="size-2.5 text-primary-foreground" />}
              </div>
              All (Clear Filters)
            </button>
          </div>
          <div className="py-1 flex flex-col gap-0.5 animate-in fade-in slide-in-from-top-1 duration-100">
            {options.map((opt) => {
              const isChecked = selected.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => toggleOption(opt.id)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted hover:text-foreground rounded text-left cursor-pointer"
                >
                  <div className={cn(
                    "size-3.5 rounded border flex items-center justify-center bg-muted",
                    isChecked && "bg-primary border-primary"
                  )}>
                    {isChecked && <Check className="size-2.5 text-primary-foreground" />}
                  </div>
                  <span className="truncate">{opt.name}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function AlertsPage() {
  const { 
    rooms: selectedRooms = [], 
    devices: selectedDevices = [], 
    severity: selectedSeverity = 'All', 
    status: selectedStatus = 'All',
    timeRange: selectedTimeRange = '24h' 
  } = Route.useSearch();
  const navigate = Route.useNavigate();

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
  });

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
  });

  // Calculate start_time filter based on timeRange (bucketed to the minute to maintain queryKey stability)
  let startTimeIso: string | undefined = undefined;
  const nowMinuteMs = Math.floor(Date.now() / 60000) * 60000;
  if (selectedTimeRange === '6h') {
    startTimeIso = new Date(nowMinuteMs - 6 * 3600 * 1000).toISOString();
  } else if (selectedTimeRange === '24h') {
    startTimeIso = new Date(nowMinuteMs - 24 * 3600 * 1000).toISOString();
  } else if (selectedTimeRange === '7d') {
    startTimeIso = new Date(nowMinuteMs - 7 * 24 * 3600 * 1000).toISOString();
  } else if (selectedTimeRange === '30d') {
    startTimeIso = new Date(nowMinuteMs - 30 * 24 * 3600 * 1000).toISOString();
  }

  const normalizedSeverity = selectedSeverity.toLowerCase() === 'all' ? undefined : selectedSeverity.toLowerCase();
  const normalizedStatus = selectedStatus.toLowerCase() === 'all' ? undefined : selectedStatus.toLowerCase();

  const { data: alertsData, isFetching } = useQuery({
    queryKey: queryKeys.alerts.list({
      rooms: selectedRooms,
      devices: selectedDevices,
      severity: normalizedSeverity,
      status: normalizedStatus,
      start_time: startTimeIso,
      limit: 100,
    }),
    queryFn: () => fetchAlerts({
      rooms: selectedRooms.length > 0 ? selectedRooms : undefined,
      devices: selectedDevices.length > 0 ? selectedDevices : undefined,
      severity: normalizedSeverity,
      status: normalizedStatus,
      start_time: startTimeIso,
      limit: 100,
    }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const updateSearch = (newParams: Partial<z.infer<typeof alertsSearchSchema>>) => {
    navigate({
      search: (prev) => ({
        ...prev,
        ...newParams,
      }),
    });
  };

  const roomOptions = rooms.map((r) => ({ id: r.id, name: r.name }));
  const deviceOptions = devices.map((d) => ({ id: d.dev_id, name: d.dev_name || d.dev_id }));
  const alerts = alertsData?.alerts || [];

  return (
    <div className="flex flex-col gap-6">
      {/* Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Alert History</h1>
          <p className="text-muted-foreground text-xs mt-1">Audit log of environmental threshold breaches and event logs</p>
        </div>
        {isFetching && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground bg-card px-3 py-1.5 rounded-full border">
            <RefreshCw className="size-3 animate-spin text-primary" />
            <span>Updating</span>
          </div>
        )}
      </div>

      {/* Filter Bar */}
      <div className="bg-card border rounded-lg p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <MultiSelect
            label="Rooms"
            placeholder="All Rooms"
            options={roomOptions}
            selected={selectedRooms}
            onChange={(val) => updateSearch({ rooms: val })}
          />

          <MultiSelect
            label="Devices"
            placeholder="All Devices"
            options={deviceOptions}
            selected={selectedDevices}
            onChange={(val) => updateSearch({ devices: val })}
          />

          <div>
            <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Severity</label>
            <select
              value={selectedSeverity}
              onChange={(e) => updateSearch({ severity: e.target.value as 'All' | 'Warning' | 'Critical' })}
              className="w-full bg-muted border rounded px-3 py-2 text-foreground text-sm focus:outline-none focus:border-primary"
            >
              <option value="All">All Severities</option>
              <option value="Warning">Warning</option>
              <option value="Critical">Critical</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Status</label>
            <select
              value={selectedStatus}
              onChange={(e) => updateSearch({ status: e.target.value as 'All' | 'Open' | 'Resolved' })}
              className="w-full bg-muted border rounded px-3 py-2 text-foreground text-sm focus:outline-none focus:border-primary"
            >
              <option value="All">All Statuses</option>
              <option value="Open">Open Only</option>
              <option value="Resolved">Resolved Only</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Time Range</label>
            <select
              value={selectedTimeRange}
              onChange={(e) => updateSearch({ timeRange: e.target.value as '6h' | '24h' | '7d' | '30d' })}
              className="w-full bg-muted border rounded px-3 py-2 text-foreground text-sm focus:outline-none focus:border-primary"
            >
              <option value="6h">Past 6 Hours</option>
              <option value="24h">Past 24 Hours</option>
              <option value="7d">Past 7 Days</option>
              <option value="30d">Past 30 Days</option>
            </select>
          </div>
        </div>
      </div>

      {/* Alerts Table */}
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Recorded Events ({alerts.length})
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-foreground">
            <thead className="bg-muted text-[10px] font-semibold uppercase text-muted-foreground border-b">
              <tr>
                <th className="px-6 py-3">Timestamp</th>
                <th className="px-6 py-3">Severity</th>
                <th className="px-6 py-3">Device</th>
                <th className="px-6 py-3">Room</th>
                <th className="px-6 py-3">Metric / Parameter</th>
                <th className="px-6 py-3">Reading</th>
                <th className="px-6 py-3">Threshold</th>
                <th className="px-6 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {alerts.map((alert) => (
                <tr key={alert.event_id} className="hover:bg-muted/50 transition-colors">
                  <td className="px-6 py-4 text-muted-foreground font-mono">
                    {new Date(alert.timestamp).toLocaleString()}
                  </td>
                  <td className="px-6 py-4">
                    <span className={cn(
                      "px-2.5 py-0.5 rounded text-[10px] font-bold uppercase",
                      alert.severity === 'critical'
                        ? "bg-destructive/20 text-destructive border border-destructive/30"
                        : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                    )}>
                      {alert.severity}
                    </span>
                  </td>
                  <td className="px-6 py-4 font-semibold text-foreground">
                    {alert.dev_name || alert.dev_id || 'Unknown Device'}
                  </td>
                  <td className="px-6 py-4 text-muted-foreground font-medium">
                    {alert.room_name || 'Unassigned'}
                  </td>
                  <td className="px-6 py-4 text-foreground">
                    {alert.metric || alert.message || 'Temperature Threshold'}
                  </td>
                  <td className="px-6 py-4 font-mono font-bold text-foreground">
                    {alert.value !== null && alert.value !== undefined ? `${alert.value}°C` : '—'}
                  </td>
                  <td className="px-6 py-4 font-mono text-muted-foreground">
                    {alert.threshold !== null && alert.threshold !== undefined ? `${alert.threshold}°C` : '—'}
                  </td>
                  <td className="px-6 py-4">
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[10px] font-semibold inline-flex items-center gap-1",
                      alert.resolved_at
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-destructive/10 text-destructive border border-destructive/20"
                    )}>
                      <span className={cn(
                        "size-1.5 rounded-full",
                        alert.resolved_at ? "bg-emerald-400" : "bg-destructive animate-pulse"
                      )} />
                      {alert.resolved_at ? 'Resolved' : 'Active'}
                    </span>
                  </td>
                </tr>
              ))}
              {alerts.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-10 text-center text-muted-foreground">
                    <ShieldAlert className="size-8 mx-auto mb-2 text-muted-foreground" />
                    <p>No alert records match the selected filter criteria.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
