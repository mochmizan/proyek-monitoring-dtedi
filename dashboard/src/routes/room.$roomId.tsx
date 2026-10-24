import { createFileRoute, Link, useRouter } from '@tanstack/react-router';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { 
  ArrowLeft, 
  Wind, 
  AlertTriangle, 
  Thermometer, 
  Zap, 
  Loader2,
  RefreshCw,
  HelpCircle
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '../lib/utils';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchRooms, fetchRoomMap, fetchCurrentUser, fetchAlerts } from '../lib/api';
import { useCommandLifecycle } from '../hooks/useCommandLifecycle';
import { CommandStatusBadge } from '../components/device/CommandStatusBadge';
import { POLL_TIER2_ALERTS_MS, STALE_TIER2_ALERTS_MS, STALE_METADATA_MS } from '../lib/constants';
import { getJitteredInterval } from '../lib/jitter';
import type { RoomMapMarker, ATSCommand } from '../types/api';

const roomSearchSchema = z.object({
  range: z.enum(['6h', '24h', '7d', '30d']).optional(),
});

export const Route = createFileRoute('/room/$roomId')({
  validateSearch: (search) => roomSearchSchema.parse(search),
  component: RoomDetailPage,
});

function RoomDetailPage() {
  const { roomId } = Route.useParams();
  const router = useRouter();

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchCurrentUser,
  });

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: () => fetchRooms(),
    staleTime: STALE_METADATA_MS,
    placeholderData: keepPreviousData,
  });

  const { data: roomMap, isFetching: isFetchingMap } = useQuery({
    queryKey: queryKeys.rooms.map(roomId),
    queryFn: () => fetchRoomMap(roomId),
    refetchInterval: () => getJitteredInterval(POLL_TIER2_ALERTS_MS),
    staleTime: STALE_TIER2_ALERTS_MS,
    placeholderData: keepPreviousData,
  });

  const { data: roomAlertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ room: roomId }),
    queryFn: () => fetchAlerts({ room: roomId }),
    refetchInterval: () => getJitteredInterval(POLL_TIER2_ALERTS_MS),
    staleTime: STALE_TIER2_ALERTS_MS,
    placeholderData: keepPreviousData,
  });

  // ATS / Device Command State
  const [selectedDeviceForCmd, setSelectedDeviceForCmd] = useState<RoomMapMarker | null>(null);
  const [commandPayload, setCommandPayload] = useState<ATSCommand>({});
  const [formValidationError, setFormValidationError] = useState<string | null>(null);

  const commandLifecycle = useCommandLifecycle();

  const room = rooms.find((r) => r.id === roomId);

  if (!room && !roomMap) {
    return (
      <div className="space-y-6">
        <button 
          onClick={() => router.navigate({ to: '/' })}
          className="flex items-center gap-2 text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Dashboard</span>
        </button>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center">
          <p className="text-zinc-400">Room not found.</p>
        </div>
      </div>
    );
  }

  const roomName = roomMap?.room_name || room?.name || 'Room';
  const devices = roomMap?.devices || [];
  const activeAlerts = (roomAlertsData?.alerts || []).filter((a) => !a.resolved_at);

  const role = currentUser?.role || 'viewer';
  const isAdmin = role === 'admin' || role === 'root' || role === 'super_admin';
  const canControl = isAdmin || role === 'operator';

  const handleOpenCommandModal = (device: RoomMapMarker) => {
    setSelectedDeviceForCmd(device);
    setFormValidationError(null);
    setCommandPayload({});
    commandLifecycle.reset();
  };

  const handleExecuteCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDeviceForCmd) return;
    if (!commandPayload.mode && !commandPayload.start_genset && !commandPayload.reset) {
      setFormValidationError('Select at least one command action to send');
      return;
    }
    setFormValidationError(null);

    await commandLifecycle.sendCommand(selectedDeviceForCmd.dev_id, commandPayload);
  };

  return (
    <div className="space-y-8">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => router.navigate({ to: '/' })}
            className="p-2 bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 rounded-md text-zinc-400 hover:text-zinc-100 transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">{roomName}</h1>
            <p className="text-xs text-zinc-500 mt-0.5">
              {devices.length} assigned devices · {activeAlerts.length} active alerts
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isFetchingMap && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-zinc-900 px-3 py-1.5 rounded-full border border-zinc-800">
              <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />
              <span>Live Polling</span>
            </div>
          )}
          <div className={cn(
            "px-3 py-1 rounded-full text-xs font-semibold border flex items-center gap-1.5",
            activeAlerts.length > 0
              ? "bg-red-500/10 text-red-400 border-red-500/20"
              : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
          )}>
            <span className={cn(
              "h-1.5 w-1.5 rounded-full animate-pulse",
              activeAlerts.length > 0 ? "bg-red-400" : "bg-emerald-400"
            )} />
            <span>{activeAlerts.length > 0 ? `${activeAlerts.length} Alert Active` : 'Normal Status'}</span>
          </div>
        </div>
      </div>

      {/* Floor Plan Overview (if available) */}
      {roomMap && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-3">Room Floor Plan Layout</h3>
          {roomMap.has_image && roomMap.floor_plan_url ? (
            <div className="relative w-full max-w-3xl mx-auto aspect-[16/9] bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden select-none">
              <img 
                src={roomMap.floor_plan_url} 
                alt={`${roomName} Floor Plan`} 
                className="w-full h-full object-cover opacity-60" 
              />
              {devices.map((device) => {
                const x = device.marker_x !== null && device.marker_x !== undefined ? device.marker_x : 50;
                const y = device.marker_y !== null && device.marker_y !== undefined ? device.marker_y : 50;

                let markerBg = 'bg-emerald-500 border-emerald-300';
                if (!device.is_active) {
                  markerBg = 'bg-zinc-500 border-zinc-400';
                }

                return (
                  <div
                    key={device.dev_id}
                    style={{ left: `${x}%`, top: `${y}%` }}
                    className="absolute -translate-x-1/2 -translate-y-1/2 z-20 group"
                  >
                    <Link
                      to="/device/$deviceId"
                      params={{ deviceId: device.dev_name || device.dev_id }}
                      className={cn(
                        "h-8 w-8 rounded-full border-2 flex items-center justify-center cursor-pointer shadow-lg hover:scale-110 active:scale-95 transition-all duration-150",
                        markerBg
                      )}
                    >
                      {device.dev_type === 'TS' && <Thermometer className="h-4 w-4 text-white" />}
                      {device.dev_type === 'ATS' && <Zap className="h-4 w-4 text-white" />}
                      {(device.dev_type === 'AC' || device.dev_type === 'ACC') && <Wind className="h-4 w-4 text-white" />}
                      {!['TS', 'ATS', 'AC', 'ACC'].includes(device.dev_type || '') && (
                        <HelpCircle className="h-4 w-4 text-white" />
                      )}
                    </Link>
                    {/* Tooltip */}
                    <div className="absolute left-10 top-1/2 -translate-y-1/2 bg-zinc-900 border border-zinc-800 rounded-lg p-2.5 shadow-2xl z-30 w-48 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity">
                      <div className="font-bold text-zinc-100 text-xs truncate">{device.dev_name || device.dev_id}</div>
                      <div className="text-[10px] text-zinc-500 font-mono">{device.dev_type || 'Device'}</div>
                      {device.latest_reading && (
                        <div className="text-xs text-indigo-400 font-semibold mt-1">
                          {device.dev_type === 'TS' && typeof device.latest_reading.temp === 'number' && (
                            <span>{device.latest_reading.temp.toFixed(1)}°C / {String(device.latest_reading.humid ?? '')}%</span>
                          )}
                          {(device.dev_type === 'AC' || device.dev_type === 'ACC') && (
                            <div className="space-y-0.5">
                              {device.latest_reading.temp != null && (
                                <div>
                                  {typeof device.latest_reading.temp === 'number'
                                    ? `${device.latest_reading.temp.toFixed(1)}°C`
                                    : `${device.latest_reading.temp}°C`}
                                  {device.latest_reading.humid != null ? ` / ${String(device.latest_reading.humid)}%` : ''}
                                </div>
                              )}
                              {(device.latest_reading.ac1_power || device.latest_reading.ac2_power) ? (
                                <div className="text-[10px] text-zinc-300 font-normal">
                                  AC1: {String(device.latest_reading.ac1_power || 'OFF')} | AC2: {String(device.latest_reading.ac2_power || 'OFF')}
                                </div>
                              ) : null}
                            </div>
                          )}
                          {device.dev_type === 'ATS' && (
                            <span>State: {String(device.latest_reading.state ?? 'N/A')}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="bg-zinc-950 border border-zinc-850 rounded-lg p-6 text-center text-zinc-500 text-xs">
              No floor plan uploaded for this room. Upload a diagram in Settings to enable interactive spatial positioning.
            </div>
          )}
        </div>
      )}

      {/* Devices in Room */}
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 mb-4">Assigned Room Devices</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {devices.map((device) => {
            const reading = device.latest_reading;
            const isTS = device.dev_type === 'TS';
            const isATS = device.dev_type === 'ATS';
            const isAC = device.dev_type === 'AC' || device.dev_type === 'ACC';

            return (
              <div 
                key={device.dev_id} 
                className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h4 className="font-bold text-zinc-100">{device.dev_name || device.dev_id}</h4>
                      <p className="text-xs text-zinc-500 font-mono">{device.dev_id}</p>
                    </div>
                    <span className="bg-zinc-800 text-zinc-300 text-xs px-2.5 py-1 rounded font-mono font-medium">
                      {device.dev_type || 'Generic'}
                    </span>
                  </div>

                  {/* Telemetry Display */}
                  <div className="my-4 p-3 bg-zinc-950 rounded border border-zinc-850 space-y-2">
                    {isTS && reading && (
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-[10px] text-zinc-500 uppercase font-semibold">Temperature</div>
                          <div className="text-xl font-bold text-zinc-100">
                            {typeof reading.temp === 'number' ? `${reading.temp.toFixed(1)}°C` : '—'}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-zinc-500 uppercase font-semibold">Humidity</div>
                          <div className="text-xl font-bold text-indigo-400">
                            {typeof reading.humid === 'number' ? `${reading.humid.toFixed(1)}%` : String(reading.humid ?? '—')}
                          </div>
                        </div>
                      </div>
                    )}

                    {isAC && reading && (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800/80">
                            <div className="text-zinc-500 font-medium mb-1">ROOM TEMP</div>
                            <div className="text-lg font-bold text-zinc-100">
                              {reading.temp != null ? `${reading.temp}°C` : '—'}
                            </div>
                          </div>
                          <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800/80">
                            <div className="text-zinc-500 font-medium mb-1">HUMIDITY</div>
                            <div className="text-lg font-bold text-zinc-100">
                              {reading.humid != null ? `${reading.humid}%` : '—'}
                            </div>
                          </div>
                        </div>
                        {(reading.ac1_power || reading.ac2_power || reading.ac1_temp || reading.ac2_temp) && (
                          <div className="grid grid-cols-2 gap-2 text-xs">
                            <div className="bg-zinc-900/40 p-2 rounded border border-zinc-800/50">
                              <span className="text-zinc-400 font-semibold">AC 1: </span>
                              <span className={reading.ac1_power === 'ON' ? 'text-emerald-400 font-bold' : 'text-zinc-500'}>
                                {reading.ac1_power || 'OFF'}
                              </span>
                              {reading.ac1_temp ? <span className="text-zinc-300 ml-1">({reading.ac1_temp}°C)</span> : null}
                            </div>
                            <div className="bg-zinc-900/40 p-2 rounded border border-zinc-800/50">
                              <span className="text-zinc-400 font-semibold">AC 2: </span>
                              <span className={reading.ac2_power === 'ON' ? 'text-emerald-400 font-bold' : 'text-zinc-500'}>
                                {reading.ac2_power || 'OFF'}
                              </span>
                              {reading.ac2_temp ? <span className="text-zinc-300 ml-1">({reading.ac2_temp}°C)</span> : null}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {isATS && reading && (
                      <div className="space-y-1.5 text-xs">
                        <div className="flex justify-between">
                          <span className="text-zinc-500">State:</span>
                          <span className="font-bold text-zinc-200 uppercase">{String(reading.state ?? 'N/A')}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-500">PLN Voltage:</span>
                          <span className="font-mono text-zinc-200">{String(reading.pln ?? '—')} V</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Genset Voltage:</span>
                          <span className="font-mono text-zinc-200">{String(reading.genset ?? '—')} V</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Battery (AKI):</span>
                          <span className="font-mono text-zinc-200">{String(reading.aki ?? '—')} V</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-zinc-500">Mode:</span>
                          <span className={cn("font-semibold", reading.auto_mode ? "text-emerald-400" : "text-amber-400")}>
                            {reading.auto_mode ? 'AUTO' : 'MANUAL'}
                          </span>
                        </div>
                      </div>
                    )}

                    {(!reading || (!isTS && !isATS && !isAC)) && (
                      <div className="text-xs text-zinc-500 text-center py-2">
                        {device.is_active ? 'Awaiting telemetry packet...' : 'Device pending pairing'}
                      </div>
                    )}
                  </div>
                </div>

                {/* Card footer / Actions */}
                <div className="flex items-center justify-between pt-3 border-t border-zinc-800/80">
                  <Link
                    to="/device/$deviceId"
                    params={{ deviceId: device.dev_name || device.dev_id }}
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
                  >
                    View Device →
                  </Link>

                  {(isATS || isAC) && canControl && (
                    <button
                      onClick={() => handleOpenCommandModal(device)}
                      className="px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 border border-indigo-500/30 rounded text-xs font-medium transition-colors cursor-pointer"
                    >
                      Command Control
                    </button>
                  )}
                </div>
              </div>
            );
          })}

          {devices.length === 0 && (
            <div className="col-span-full bg-zinc-900 border border-zinc-800 rounded-lg p-8 text-center text-zinc-500 text-sm">
              No devices currently assigned to this room. You can pair devices in Settings.
            </div>
          )}
        </div>
      </div>

      {/* Command Control Modal */}
      {selectedDeviceForCmd && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="font-bold text-zinc-100">
                  Command Control: {selectedDeviceForCmd.dev_name || selectedDeviceForCmd.dev_id}
                </h3>
                <p className="text-xs text-zinc-500 font-mono">{selectedDeviceForCmd.dev_type} Node</p>
              </div>
              <button 
                onClick={() => {
                  commandLifecycle.reset();
                  setSelectedDeviceForCmd(null);
                }}
                className="text-zinc-500 hover:text-zinc-300 text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            {formValidationError && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                <span>{formValidationError}</span>
              </div>
            )}

            <CommandStatusBadge
              status={commandLifecycle.commandStatus}
              commandId={commandLifecycle.commandId}
              queuedAt={commandLifecycle.queuedAt}
              deliveredAt={commandLifecycle.deliveredAt}
              errorMessage={commandLifecycle.errorMessage}
              onDismiss={commandLifecycle.reset}
              onRetry={commandLifecycle.retry}
            />

            <form onSubmit={handleExecuteCommand} className="space-y-4">
              {/* ATS Mode Selector */}
              <div>
                <label htmlFor="room-modal-mode-select" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                  Operating Mode
                </label>
                <select
                  id="room-modal-mode-select"
                  disabled={commandLifecycle.isPending}
                  value={commandPayload.mode || ''}
                  onChange={(e) => setCommandPayload({ 
                    ...commandPayload, 
                    mode: (e.target.value as 'auto' | 'manual') || undefined 
                  })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <option value="">No Mode Change</option>
                  <option value="auto">Auto Mode</option>
                  <option value="manual">Manual Mode</option>
                </select>
              </div>

              {/* Genset Control (only valid in manual mode) */}
              <div>
                <label htmlFor="room-modal-genset-select" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                  Genset Ignition (Manual Mode Only)
                </label>
                <select
                  id="room-modal-genset-select"
                  disabled={commandLifecycle.isPending}
                  value={commandPayload.start_genset || ''}
                  onChange={(e) => setCommandPayload({ 
                    ...commandPayload, 
                    start_genset: (e.target.value as 'on' | 'off') || undefined 
                  })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <option value="">No Genset Action</option>
                  <option value="on">Start Genset (ON)</option>
                  <option value="off">Stop Genset (OFF)</option>
                </select>
              </div>

              {/* Admin Reset */}
              {isAdmin && (
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">
                    Controller Reset (Admin Only)
                  </label>
                  <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      disabled={commandLifecycle.isPending}
                      checked={commandPayload.reset === 'rst'}
                      onChange={(e) => setCommandPayload({
                        ...commandPayload,
                        reset: e.target.checked ? 'rst' : undefined
                      })}
                      className="rounded border-zinc-700 bg-zinc-950 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
                    />
                    <span>Issue hardware reset command</span>
                  </label>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => {
                    commandLifecycle.reset();
                    setSelectedDeviceForCmd(null);
                  }}
                  disabled={commandLifecycle.isPending}
                  className="px-4 py-2 border border-zinc-800 rounded hover:bg-zinc-800 text-zinc-300 text-xs font-medium cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={commandLifecycle.isPending}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-xs font-medium cursor-pointer flex items-center gap-2"
                >
                  {commandLifecycle.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>{commandLifecycle.commandStatus === 'queuing' ? 'Dispatching...' : 'Awaiting Delivery...'}</span>
                    </>
                  ) : (
                    <span>Queue Command</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

