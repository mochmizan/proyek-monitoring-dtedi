import * as React from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useState, useRef, useEffect, useCallback } from 'react';
import { cn } from '../lib/utils';
import { ChevronDown, Check, RefreshCw, ShieldAlert } from 'lucide-react';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchAlerts, fetchRooms, fetchDevices } from '../lib/api';
import { POLL_TIER2_ALERTS_MS, STALE_TIER2_ALERTS_MS, STALE_METADATA_MS, STALE_TIER3_PRESENCE_MS } from '../lib/constants';
import { useJitteredInterval } from '../lib/jitter';
import { computeStartTimeFromRange, formatWIBDateTime } from '../lib/dateUtils';
import { formatAlertReading, formatAlertThreshold } from '../lib/formatAlert';
import { Pagination } from '../components/ui/pagination';

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
  page: z.number().int().min(1).catch(1).optional(),
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

const MultiSelect = React.memo(function MultiSelect({ label, placeholder, options, selected, onChange }: MultiSelectProps) {
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

  const toggleOption = useCallback((id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((item) => item !== id));
    } else {
      onChange([...selected, id]);
    }
  }, [selected, onChange]);

  const selectAll = useCallback(() => {
    onChange([]);
  }, [onChange]);

  return (
    <div className="relative" ref={dropdownRef}>
      <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">{label}</label>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between bg-zinc-950 border border-zinc-800 hover:border-zinc-700 rounded px-3 py-2 text-zinc-300 text-sm focus:outline-none focus:border-indigo-500 text-left transition-colors cursor-pointer"
      >
        <span className="truncate">
          {selected.length === 0 ? placeholder : `${selected.length} selected`}
        </span>
        <ChevronDown className={cn("h-4 w-4 text-zinc-500 transition-transform duration-200", isOpen && "rotate-180")} />
      </button>

      {isOpen ? (
        <div className="absolute left-0 z-50 mt-1 w-full bg-zinc-950 border border-zinc-800 rounded shadow-xl max-h-60 overflow-y-auto p-1 divide-y divide-zinc-900">
          <div className="py-1">
            <button
              type="button"
              onClick={selectAll}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-indigo-400 hover:bg-zinc-900 rounded text-left font-semibold cursor-pointer transition-colors duration-200 ease-out"
            >
              <div className={cn(
                "w-3.5 h-3.5 rounded border border-zinc-700 flex items-center justify-center bg-zinc-950",
                selected.length === 0 && "bg-indigo-600 border-indigo-600"
              )}>
                {selected.length === 0 ? <Check className="h-2.5 w-2.5 text-white" /> : null}
              </div>
              All (Clear Filters)
            </button>
          </div>
          <div className="py-1 space-y-0.5 animate-in fade-in slide-in-from-top-1 duration-100">
            {options.map((opt) => {
              const isChecked = selected.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => toggleOption(opt.id)}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 rounded text-left cursor-pointer transition-colors duration-200 ease-out"
                >
                  <div className={cn(
                    "w-3.5 h-3.5 rounded border border-zinc-700 flex items-center justify-center bg-zinc-950",
                    isChecked && "bg-indigo-600 border-indigo-600"
                  )}>
                    {isChecked ? <Check className="h-2.5 w-2.5 text-white" /> : null}
                  </div>
                  <span className="truncate">{opt.name}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
});

const PAGE_SIZE = 15;

function AlertsPage() {
  const search = Route.useSearch();
  const { 
    rooms: selectedRooms = [], 
    devices: selectedDevices = [], 
    severity: selectedSeverity = 'All', 
    status: selectedStatus = 'All',
    timeRange: selectedTimeRange = '24h',
    page: searchPage = 1,
  } = search;
  const navigate = Route.useNavigate();

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    staleTime: STALE_METADATA_MS,
  });

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    staleTime: STALE_TIER3_PRESENCE_MS,
  });

  const normalizedSeverity = selectedSeverity.toLowerCase() === 'all' ? undefined : selectedSeverity.toLowerCase();
  const normalizedStatus = selectedStatus.toLowerCase() === 'all' ? undefined : selectedStatus.toLowerCase();

  const offset = (searchPage - 1) * PAGE_SIZE;
  const alertsPollInterval = useJitteredInterval(POLL_TIER2_ALERTS_MS);

  const { data: alertsData, isFetching } = useQuery({
    queryKey: queryKeys.alerts.list({
      rooms: selectedRooms,
      devices: selectedDevices,
      severity: normalizedSeverity,
      status: normalizedStatus,
      timeRange: selectedTimeRange,
      limit: PAGE_SIZE,
      offset,
      page: searchPage,
    }),
    queryFn: () => {
      const startTimeIso = computeStartTimeFromRange(selectedTimeRange);
      return fetchAlerts({
        rooms: selectedRooms.length > 0 ? selectedRooms : undefined,
        devices: selectedDevices.length > 0 ? selectedDevices : undefined,
        severity: normalizedSeverity,
        status: normalizedStatus,
        start_time: startTimeIso,
        limit: PAGE_SIZE,
        offset,
      });
    },
    refetchInterval: alertsPollInterval,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
    staleTime: STALE_TIER2_ALERTS_MS,
  });

  const updateSearch = (newParams: Partial<z.infer<typeof alertsSearchSchema>>) => {
    navigate({
      search: (prev) => {
        const page = newParams.page !== undefined ? newParams.page : 1;
        return {
          ...prev,
          ...newParams,
          page,
        };
      },
      resetScroll: false,
    });
  };

  const roomOptions = rooms.map((r) => ({ id: r.id, name: r.name }));
  const deviceOptions = devices.map((d) => ({ id: d.dev_id, name: d.dev_name || d.dev_id }));
  const alerts = alertsData?.alerts || [];
  const totalAlerts = alertsData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalAlerts / PAGE_SIZE));

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Alert History</h1>
          <p className="text-zinc-500 text-xs mt-1">Audit log of environmental threshold breaches and event logs</p>
        </div>
        {isFetching && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-zinc-900 px-3 py-1.5 rounded-full border border-zinc-800">
            <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />
            <span>Updating</span>
          </div>
        )}
      </div>

      {/* Filter Bar */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
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
            <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Severity</label>
            <select
              value={selectedSeverity}
              onChange={(e) => updateSearch({ severity: e.target.value as 'All' | 'Warning' | 'Critical' })}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-300 text-sm focus:outline-none focus:border-indigo-500"
            >
              <option value="All">All Severities</option>
              <option value="Warning">Warning</option>
              <option value="Critical">Critical</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Status</label>
            <select
              value={selectedStatus}
              onChange={(e) => updateSearch({ status: e.target.value as 'All' | 'Open' | 'Resolved' })}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-300 text-sm focus:outline-none focus:border-indigo-500"
            >
              <option value="All">All Statuses</option>
              <option value="Open">Open Only</option>
              <option value="Resolved">Resolved Only</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Time Range</label>
            <select
              value={selectedTimeRange}
              onChange={(e) => updateSearch({ timeRange: e.target.value as '6h' | '24h' | '7d' | '30d' })}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-300 text-sm focus:outline-none focus:border-indigo-500"
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
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">
            Recorded Events ({totalAlerts})
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800">
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
            <tbody className="divide-y divide-zinc-800/60">
              {alerts.map((alert) => (
                <tr key={alert.event_id} className="hover:bg-zinc-850/50 transition-colors">
                  <td className="px-6 py-4 text-zinc-400 font-mono">
                    {formatWIBDateTime(alert.timestamp)}
                  </td>
                  <td className="px-6 py-4">
                    <span className={cn(
                      "px-2.5 py-0.5 rounded text-[10px] font-bold uppercase",
                      alert.severity === 'critical'
                        ? "bg-red-500/20 text-red-400 border border-red-500/30"
                        : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                    )}>
                      {alert.severity}
                    </span>
                  </td>
                  <td className="px-6 py-4 font-semibold text-zinc-200">
                    {alert.dev_name || alert.dev_id || 'Unknown Device'}
                  </td>
                  <td className="px-6 py-4 text-zinc-400 font-medium">
                    {alert.room_name || 'Unassigned'}
                  </td>
                  <td className="px-6 py-4 text-zinc-300">
                    {alert.message || (
                      alert.metric === 'battery'
                        ? 'Starter Battery Undervoltage'
                        : alert.metric === 'emergency'
                          ? 'ATS Emergency State'
                          : alert.metric === 'connectivity' || alert.metric === 'presence'
                            ? 'Connection Status'
                            : 'Temperature Threshold'
                    )}
                  </td>
                  <td className="px-6 py-4 font-mono font-bold text-zinc-100">
                    {formatAlertReading(alert)}
                  </td>
                  <td className="px-6 py-4 font-mono text-zinc-500">
                    {formatAlertThreshold(alert)}
                  </td>
                  <td className="px-6 py-4">
                    <span className={cn(
                      "px-2 py-0.5 rounded text-[10px] font-semibold inline-flex items-center gap-1",
                      alert.resolved_at
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-red-500/10 text-red-400 border border-red-500/20"
                    )}>
                      <span className={cn(
                        "h-1.5 w-1.5 rounded-full",
                        alert.resolved_at ? "bg-emerald-400" : "bg-red-400 animate-pulse"
                      )} />
                      {alert.resolved_at ? 'Resolved' : 'Active'}
                    </span>
                  </td>
                </tr>
              ))}
              {alerts.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-10 text-center text-zinc-500">
                    <ShieldAlert className="h-8 w-8 mx-auto mb-2 text-zinc-700" />
                    <p>No alert records match the selected filter criteria.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <Pagination
          currentPage={searchPage}
          totalPages={totalPages}
          totalItems={totalAlerts}
          pageSize={PAGE_SIZE}
          onPageChange={(page) => updateSearch({ page })}
          isLoading={isFetching}
          itemLabel="alerts"
        />
      </div>
    </div>
  );
}
