import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Cpu, CheckCircle, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { queryKeys } from '../../lib/queryKeys';
import { fetchRooms, fetchDevices, pairDevice, unpairDevice } from '../../lib/api';
import { POLL_TIER3_PRESENCE_MS, STALE_TIER3_PRESENCE_MS, STALE_METADATA_MS } from '../../lib/constants';
import { getJitteredInterval } from '../../lib/jitter';
import type { DeviceResponse, DevicePairRequest } from '../../types/api';

export function DevicesTab() {
  const queryClient = useQueryClient();
  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    staleTime: STALE_METADATA_MS,
  });
  const { data: allDevices = [], isFetching } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    refetchInterval: () => getJitteredInterval(POLL_TIER3_PRESENCE_MS),
    staleTime: STALE_TIER3_PRESENCE_MS,
  });

  const pendingDevices = useMemo(() => allDevices.filter((d) => !d.is_active), [allDevices]);
  const activeDevices = useMemo(() => allDevices.filter((d) => d.is_active), [allDevices]);
  const isFetchingPending = isFetching;
  const isFetchingActive = isFetching;

  const [selectedDeviceToPair, setSelectedDeviceToPair] = useState<DeviceResponse | null>(null);
  const [pairName, setPairName] = useState('');
  const [pairRoomId, setPairRoomId] = useState('');
  const [pairMarkerX, setPairMarkerX] = useState('50');
  const [pairMarkerY, setPairMarkerY] = useState('50');
  const [pairWarn, setPairWarn] = useState('30');
  const [pairCrit, setPairCrit] = useState('35');
  const [pairHyst, setPairHyst] = useState('0.5');
  const [pairDebounce, setPairDebounce] = useState('60');
  const [pairError, setPairError] = useState<string | null>(null);
  const [pairSuccess, setPairSuccess] = useState<string | null>(null);

  const pairMutation = useMutation({
    mutationFn: ({ devId, payload }: { devId: string; payload: DevicePairRequest }) => pairDevice(devId, payload),
    onSuccess: () => {
      setPairSuccess('Device paired and activated successfully'); setPairError(null); setSelectedDeviceToPair(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all }); queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all }); setTimeout(() => setPairSuccess(null), 3000);
    },
    onError: (err: Error) => setPairError(err.message),
  });
  const unpairMutation = useMutation({
    mutationFn: unpairDevice,
    onSuccess: () => {
      setPairSuccess('Device unpaired and deactivated successfully'); setPairError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all }); queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all }); setTimeout(() => setPairSuccess(null), 3000);
    },
    onError: (err: Error) => setPairError(err.message),
  });

  const handleStartPair = (dev: DeviceResponse) => {
    setSelectedDeviceToPair(dev);
    setPairName(dev.dev_name || dev.dev_id);
    setPairRoomId(rooms[0]?.id || '');
    setPairMarkerX(dev.marker_x?.toString() || '50');
    setPairMarkerY(dev.marker_y?.toString() || '50');
    if (dev.threshold_config) {
      setPairWarn(dev.threshold_config.warning.toString());
      setPairCrit(dev.threshold_config.critical.toString());
      setPairHyst(dev.threshold_config.hysteresis.toString());
      setPairDebounce(dev.threshold_config.debounce_seconds.toString());
    } else {
      if (dev.dev_type === 'ATS') {
        setPairWarn('11.8');
        setPairCrit('11.2');
        setPairHyst('0.2');
        setPairDebounce('60');
      } else {
        setPairWarn('28');
        setPairCrit('32');
        setPairHyst('0.5');
        setPairDebounce('60');
      }
    }
    setPairError(null);
  };
  const handlePairSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDeviceToPair || !pairRoomId || !pairName.trim()) { setPairError('Device name and room assignment are required'); return; }
    const warn = parseFloat(pairWarn);
    const crit = parseFloat(pairCrit);
    const hyst = parseFloat(pairHyst);
    const deb = parseInt(pairDebounce, 10);
    const mx = parseFloat(pairMarkerX);
    const my = parseFloat(pairMarkerY);

    if (!isNaN(warn) && !isNaN(crit)) {
      if (selectedDeviceToPair.dev_type === 'ATS') {
        if (warn < crit) {
          setPairError('For ATS battery undervoltage, Warning threshold must be greater than or equal to Critical threshold');
          return;
        }
      } else {
        if (warn > crit) {
          setPairError('Warning threshold cannot exceed critical threshold');
          return;
        }
      }
    }

    const defaultHyst = selectedDeviceToPair.dev_type === 'ATS' ? 0.2 : 0.5;
    pairMutation.mutate({
      devId: selectedDeviceToPair.dev_id,
      payload: {
        dev_name: pairName.trim(),
        room_id: pairRoomId,
        marker_x: isNaN(mx) ? 50 : mx,
        marker_y: isNaN(my) ? 50 : my,
        warning_threshold: isNaN(warn) ? undefined : warn,
        critical_threshold: isNaN(crit) ? undefined : crit,
        hysteresis: isNaN(hyst) ? defaultHyst : hyst,
        debounce_seconds: isNaN(deb) ? 60 : deb,
      },
    });
  };

  return (
    <div className="space-y-6">
      {pairError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="h-4 w-4 flex-shrink-0" /><span>{pairError}</span></div>}
      {pairSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="h-4 w-4 flex-shrink-0" /><span>{pairSuccess}</span></div>}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div><h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2"><Cpu className="h-4 w-4 text-amber-400" /><span>Pending Self-Discovered Devices</span></h3><p className="text-xs text-zinc-500">Unpaired edge devices blocked by default until approved by an administrator.</p></div>
          {isFetchingPending && <RefreshCw className="h-3 w-3 animate-spin text-amber-400" />}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {pendingDevices.map((dev) => (<div key={dev.dev_id} className="bg-zinc-950 border border-zinc-800 p-4 rounded-lg flex flex-col justify-between"><div><div className="flex items-start justify-between"><div><h4 className="font-bold text-zinc-200 text-sm">{dev.dev_name || dev.dev_id}</h4><p className="font-mono text-xs text-zinc-500">{dev.dev_id}</p></div><span className="bg-zinc-800 text-amber-400 text-[10px] px-2 py-0.5 rounded font-mono font-bold">{dev.dev_type || 'Unknown'}</span></div><p className="text-[10px] text-zinc-500 mt-2">Hub: {dev.hub_id || 'Direct'}</p></div><div className="mt-4 pt-3 border-t border-zinc-800 flex justify-end"><button onClick={() => handleStartPair(dev)} className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-semibold cursor-pointer">Pair & Activate</button></div></div>))}
          {pendingDevices.length === 0 && <div className="col-span-full py-8 text-center text-zinc-500 text-xs">No pending self-discovered devices at this time.</div>}
        </div>
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between"><h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Active Paired Devices</h3>{isFetchingActive && <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />}</div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800"><tr><th className="px-6 py-3">Device Name</th><th className="px-6 py-3">Type</th><th className="px-6 py-3">MAC / ID</th><th className="px-6 py-3">Room</th><th className="px-6 py-3">Map Coordinate</th><th className="px-6 py-3">Thresholds</th><th className="px-6 py-3 text-right">Actions</th></tr></thead>
            <tbody className="divide-y divide-zinc-800/60">
              {activeDevices.map((d) => { const r = rooms.find((room) => room.id === d.room_id); return (<tr key={d.dev_id} className="hover:bg-zinc-800/50"><td className="px-6 py-4 font-semibold text-zinc-100">{d.dev_name || d.dev_id}</td><td className="px-6 py-4 font-mono text-zinc-400">{d.dev_type || '—'}</td><td className="px-6 py-4 font-mono text-zinc-500">{d.dev_id}</td><td className="px-6 py-4 font-medium text-zinc-300">{r?.name || 'Unassigned'}</td><td className="px-6 py-4 font-mono text-zinc-400">{d.marker_x !== null && d.marker_y !== null ? `(${d.marker_x}%, ${d.marker_y}%)` : '—'}</td><td className="px-6 py-4 font-mono text-xs text-zinc-400">{d.threshold_config ? (d.dev_type === 'ATS' ? `W: ${d.threshold_config.warning}V / C: ${d.threshold_config.critical}V` : `W: ${d.threshold_config.warning}°C / C: ${d.threshold_config.critical}°C`) : 'Default'}</td><td className="px-6 py-4 text-right space-x-2"><button onClick={() => handleStartPair(d)} className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded text-[10px] font-medium cursor-pointer">Edit</button><button onClick={() => unpairMutation.mutate(d.dev_id)} disabled={unpairMutation.isPending} className="px-2 py-1 bg-red-950/30 hover:bg-red-950/60 text-red-400 border border-red-900/30 rounded text-[10px] font-medium cursor-pointer">Unpair</button></td></tr>); })}
              {activeDevices.length === 0 && <tr><td colSpan={7} className="px-6 py-6 text-center text-zinc-500 text-xs">No active paired devices.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {selectedDeviceToPair && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3"><div><h3 className="font-bold text-zinc-100">Pair & Configure Device</h3><p className="text-xs text-zinc-500 font-mono">MAC: {selectedDeviceToPair.dev_id}</p></div><button onClick={() => setSelectedDeviceToPair(null)} className="text-zinc-500 hover:text-zinc-300 text-sm">✕</button></div>
            <form onSubmit={handlePairSubmit} className="space-y-4">
              <div><label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Device Friendly Name *</label><input type="text" value={pairName} onChange={(e) => setPairName(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div>
              <div><label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Room Assignment *</label><select value={pairRoomId} onChange={(e) => setPairRoomId(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"><option value="">Select Room...</option>{rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></div>
              <div className="grid grid-cols-2 gap-4"><div><label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Map Position X (%)</label><input type="number" min="0" max="100" value={pairMarkerX} onChange={(e) => setPairMarkerX(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div><div><label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Map Position Y (%)</label><input type="number" min="0" max="100" value={pairMarkerY} onChange={(e) => setPairMarkerY(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div></div>
              <div className="grid grid-cols-2 gap-4"><div><label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">{selectedDeviceToPair.dev_type === 'ATS' ? 'Battery Warning (V)' : 'Warning Level (°C)'}</label><input type="number" step="0.1" value={pairWarn} onChange={(e) => setPairWarn(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div><div><label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">{selectedDeviceToPair.dev_type === 'ATS' ? 'Battery Critical (V)' : 'Critical Level (°C)'}</label><input type="number" step="0.1" value={pairCrit} onChange={(e) => setPairCrit(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div></div>
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-800"><button type="button" onClick={() => setSelectedDeviceToPair(null)} className="px-4 py-2 border border-zinc-800 rounded hover:bg-zinc-800 text-zinc-300 text-xs font-medium cursor-pointer">Cancel</button><button type="submit" disabled={pairMutation.isPending} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer flex items-center gap-2">{pairMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Confirm Pairing'}</button></div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
export default DevicesTab;
