import { createFileRoute, useRouter } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { Thermometer, Zap, Wind, HelpCircle, RefreshCw, Network, LayoutGrid } from 'lucide-react';
import { useState } from 'react';
import { z } from 'zod';
import { cn } from '../lib/utils';
import { queryKeys } from '../lib/queryKeys';
import { fetchRooms, fetchRoomMap } from '../lib/api'
import { POLL_MS } from '../lib/constants';
import type { RoomMapMarker } from '../types/api';
import { TopologyView } from '../components/TopologyView';

const mapSearchSchema = z.object({
  view: z.enum(['floor-plan', 'topology']).catch('floor-plan').optional(),
});

export const Route = createFileRoute('/map')({
  validateSearch: (search) => mapSearchSchema.parse(search),
  component: MapPage,
});

function MapPage() {
  const router = useRouter();
  const { view } = Route.useSearch();
  const activeView = view ?? 'floor-plan';

  const setView = (next: 'floor-plan' | 'topology') => {
    void router.navigate({ to: '/map', search: { view: next === 'floor-plan' ? undefined : next } });
  };

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
  });

  const [selectedRoomId, setSelectedRoomId] = useState<string>('');
  const activeRoomId = selectedRoomId || rooms[0]?.id || '';

  const { data: roomMap, isFetching } = useQuery({
    queryKey: queryKeys.rooms.map(activeRoomId),
    queryFn: () => fetchRoomMap(activeRoomId),
    enabled: !!activeRoomId,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const [hoveredDevice, setHoveredDevice] = useState<RoomMapMarker | null>(null);

  const getMarkerColor = (device: RoomMapMarker): string => {
    if (!device.is_active) return 'bg-zinc-500 border-zinc-400';
    if (device.dev_type === 'TS') {
      const temp = device.latest_reading?.temp;
      if (typeof temp === 'number') {
        if (temp >= 35) return 'bg-red-500 border-red-300 shadow-red-500/50 animate-pulse';
        if (temp >= 30) return 'bg-amber-500 border-amber-300 shadow-amber-500/50 animate-pulse';
      }
      return 'bg-emerald-500 border-emerald-350 shadow-emerald-500/30';
    } else if (device.dev_type === 'ATS') {
      const state = String(device.latest_reading?.state || '').toLowerCase();
      if (state.includes('genset')) return 'bg-amber-500 border-amber-300';
      return 'bg-emerald-500 border-emerald-350 shadow-emerald-500/30';
    }
    return 'bg-emerald-500 border-emerald-350 shadow-emerald-500/30';
  };

  const getDeviceIcon = (type?: string | null) => {
    switch (type) {
      case 'TS':
      case 'Temperature':
        return <Thermometer className="h-3.5 w-3.5 text-white" />;
      case 'ATS':
        return <Zap className="h-3.5 w-3.5 text-white" />;
      case 'AC':
      case 'ACC':
        return <Wind className="h-3.5 w-3.5 text-white" />;
      default:
        return <HelpCircle className="h-3.5 w-3.5 text-white" />;
    }
  };

  const devices = roomMap?.devices || [];

  return (
    <div className="space-y-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">Facility Floor Map</h1>
          <p className="text-zinc-500 text-xs mt-1">Live spatial telemetry overlay across facility rooms</p>
        </div>

        <div className="flex items-center gap-3">
          {isFetching && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 bg-zinc-900 px-3 py-1.5 rounded-full border border-zinc-800">
              <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />
              <span>Syncing Map</span>
            </div>
          )}

          {rooms.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-400 font-medium">Room:</span>
              <select
                value={activeRoomId}
                onChange={(e) => setSelectedRoomId(e.target.value)}
                className="bg-zinc-900 border border-zinc-700 text-zinc-200 text-xs rounded px-3 py-1.5 focus:outline-none focus:border-indigo-500"
              >
                {rooms.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      <div className="flex border-b border-zinc-800 gap-4 text-sm font-semibold">
        <button
          onClick={() => setView('floor-plan')}
          className={cn(
            'pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer',
            activeView === 'floor-plan'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-zinc-500 hover:text-zinc-300'
          )}
        >
          <LayoutGrid className="h-4 w-4" />
          <span>Floor Plan</span>
        </button>
        <button
          onClick={() => setView('topology')}
          className={cn(
            'pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer',
            activeView === 'topology'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-zinc-500 hover:text-zinc-300'
          )}
        >
          <Network className="h-4 w-4" />
          <span>Topology</span>
        </button>
      </div>

      {activeView === 'floor-plan' ? (
      <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg p-6 flex flex-col items-center justify-center min-h-[500px] relative">
        {rooms.length === 0 ? (
          <div className="w-full h-full flex flex-col items-center justify-center text-zinc-500 gap-2 min-h-[400px]">
            <HelpCircle className="h-8 w-8 text-zinc-600" />
            <p className="text-sm">No rooms found. Create rooms in Settings to view floor plans.</p>
          </div>
        ) : !roomMap?.has_image || !roomMap.floor_plan_url ? (
          <div className="w-full h-full flex flex-col items-center justify-center text-zinc-500 gap-2 min-h-[400px]">
            <HelpCircle className="h-8 w-8 text-zinc-600" />
            <p className="text-sm">
              No floor plan image uploaded for <span className="text-zinc-300 font-semibold">{roomMap?.room_name || 'this room'}</span>.
            </p>
            <p className="text-xs text-zinc-600">Administrators can upload PNG/SVG diagrams in Settings → Rooms.</p>
          </div>
        ) : (
          /* custom uploaded floorplan image */
          <div className="relative w-full max-w-4xl aspect-[16/10] bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden select-none">
            <img 
              src={roomMap.floor_plan_url} 
              alt={`${roomMap.room_name} Floor Plan`} 
              className="w-full h-full object-cover opacity-60" 
            />
            
            {/* Render Node Markers */}
            {devices.map((device) => {
              const x = device.marker_x !== null && device.marker_x !== undefined ? device.marker_x : 50;
              const y = device.marker_y !== null && device.marker_y !== undefined ? device.marker_y : 50;

              return (
                <div
                  key={device.dev_id}
                  style={{ left: `${x}%`, top: `${y}%` }}
                  className="absolute -translate-x-1/2 -translate-y-1/2 z-20"
                >
                  <button
                    onClick={() => router.navigate({ to: '/device/$deviceId', params: { deviceId: device.dev_id } })}
                    onMouseEnter={() => setHoveredDevice(device)}
                    onMouseLeave={() => setHoveredDevice(null)}
                    className={cn(
                      "h-8 w-8 rounded-full border-2 flex items-center justify-center cursor-pointer shadow-lg hover:scale-110 active:scale-95 transition-all duration-150",
                      getMarkerColor(device)
                    )}
                  >
                    {getDeviceIcon(device.dev_type)}
                  </button>

                  {/* Tooltip on hover */}
                  {hoveredDevice?.dev_id === device.dev_id && (
                    <div className="absolute left-10 top-1/2 -translate-y-1/2 bg-zinc-900 border border-zinc-800 rounded-lg p-3.5 shadow-2xl z-30 w-56 pointer-events-none space-y-1">
                      <h5 className="font-bold text-zinc-100 text-xs">{device.dev_name || device.dev_id}</h5>
                      <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                        {device.dev_type || 'Device'} · {device.is_active ? 'Active' : 'Pending'}
                      </div>
                      {device.latest_reading && (
                        <div className="pt-1.5 border-t border-zinc-800 text-xs text-indigo-400 font-semibold">
                          {device.dev_type === 'TS' && typeof device.latest_reading.temp === 'number' && (
                            <span>{device.latest_reading.temp.toFixed(1)}°C / {String(device.latest_reading.humid ?? '')}%</span>
                          )}
                          {device.dev_type === 'ATS' && (
                            <span>State: {String(device.latest_reading.state ?? 'N/A')}</span>
                          )}

                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      ) : (
        <TopologyView />
      )}
    </div>
  );
}
