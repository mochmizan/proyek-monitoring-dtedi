import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Cpu, CheckCircle, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { queryKeys } from '../../lib/queryKeys';
import { fetchRooms, fetchDevices, pairDevice, unpairDevice } from '../../lib/api';
import { POLL_MS } from '../../lib/constants';
import type { DeviceResponse, DevicePairRequest } from '../../types/api';

export function DevicesTab() {
  const queryClient = useQueryClient();
  const { data: rooms = [] } = useQuery({ queryKey: queryKeys.rooms.list(), queryFn: fetchRooms });
  const { data: pendingDevices = [], isFetching: isFetchingPending } = useQuery({ queryKey: queryKeys.devices.pending(), queryFn: () => fetchDevices('pending'), refetchInterval: POLL_MS, refetchIntervalInBackground: false });
  const { data: activeDevices = [], isFetching: isFetchingActive } = useQuery({ queryKey: queryKeys.devices.active(), queryFn: () => fetchDevices('active'), refetchInterval: POLL_MS, refetchIntervalInBackground: false });

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
    setSelectedDeviceToPair(dev); setPairName(dev.dev_name || dev.dev_id); setPairRoomId(rooms[0]?.id || ''); setPairMarkerX(dev.marker_x?.toString() || '50'); setPairMarkerY(dev.marker_y?.toString() || '50');
    if (dev.threshold_config) { setPairWarn(dev.threshold_config.warning.toString()); setPairCrit(dev.threshold_config.critical.toString()); setPairHyst(dev.threshold_config.hysteresis.toString()); setPairDebounce(dev.threshold_config.debounce_seconds.toString()); }
    setPairError(null);
  };
  const handlePairSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDeviceToPair || !pairRoomId || !pairName.trim()) { setPairError('Device name and room assignment are required'); return; }
    const warn = parseFloat(pairWarn); const crit = parseFloat(pairCrit); const hyst = parseFloat(pairHyst); const deb = parseInt(pairDebounce, 10); const mx = parseFloat(pairMarkerX); const my = parseFloat(pairMarkerY);
    pairMutation.mutate({ devId: selectedDeviceToPair.dev_id, payload: { dev_name: pairName.trim(), room_id: pairRoomId, marker_x: isNaN(mx) ? 50 : mx, marker_y: isNaN(my) ? 50 : my, warning_threshold: isNaN(warn) ? undefined : warn, critical_threshold: isNaN(crit) ? undefined : crit, hysteresis: isNaN(hyst) ? 0.5 : hyst, debounce_seconds: isNaN(deb) ? 60 : deb } });
  };

  return (
    <div className="flex flex-col gap-6">
      {pairError && <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="size-4 flex-shrink-0" /><span>{pairError}</span></div>}
      {pairSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="size-4 flex-shrink-0" /><span>{pairSuccess}</span></div>}
      <div className="bg-card border rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div><h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2"><Cpu className="size-4 text-amber-400" /><span>Pending Self-Discovered Devices</span></h3><p className="text-xs text-muted-foreground">Unpaired edge devices blocked by default until approved by an administrator.</p></div>
          {isFetchingPending && <RefreshCw className="size-3 animate-spin text-amber-400" />}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {pendingDevices.map((dev) => (<div key={dev.dev_id} className="bg-muted border p-4 rounded-lg flex flex-col justify-between"><div><div className="flex items-start justify-between"><div><h4 className="font-bold text-foreground text-sm">{dev.dev_name || dev.dev_id}</h4><p className="font-mono text-xs text-muted-foreground">{dev.dev_id}</p></div><span className="bg-muted text-amber-400 text-[10px] px-2 py-0.5 rounded font-mono font-bold border">{dev.dev_type || 'Unknown'}</span></div><p className="text-[10px] text-muted-foreground mt-2">Hub: {dev.hub_id || 'Direct'}</p></div><div className="mt-4 pt-3 border-t flex justify-end"><button onClick={() => handleStartPair(dev)} className="px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded text-xs font-semibold cursor-pointer">Pair & Activate</button></div></div>))}
          {pendingDevices.length === 0 && <div className="col-span-full py-8 text-center text-muted-foreground text-xs">No pending self-discovered devices at this time.</div>}
        </div>
      </div>
      <div className="bg-card border rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b flex items-center justify-between"><h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Active Paired Devices</h3>{isFetchingActive && <RefreshCw className="size-3 animate-spin text-primary" />}</div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-foreground">
            <thead className="bg-muted text-[10px] font-semibold uppercase text-muted-foreground border-b"><tr><th className="px-6 py-3">Device Name</th><th className="px-6 py-3">Type</th><th className="px-6 py-3">MAC / ID</th><th className="px-6 py-3">Room</th><th className="px-6 py-3">Map Coordinate</th><th className="px-6 py-3">Thresholds</th><th className="px-6 py-3 text-right">Actions</th></tr></thead>
            <tbody className="divide-y divide-border/60">
              {activeDevices.map((d) => { const r = rooms.find((room) => room.id === d.room_id); return (<tr key={d.dev_id} className="hover:bg-muted/50"><td className="px-6 py-4 font-semibold text-foreground">{d.dev_name || d.dev_id}</td><td className="px-6 py-4 font-mono text-muted-foreground">{d.dev_type || '—'}</td><td className="px-6 py-4 font-mono text-muted-foreground">{d.dev_id}</td><td className="px-6 py-4 font-medium text-foreground">{r?.name || 'Unassigned'}</td><td className="px-6 py-4 font-mono text-muted-foreground">{d.marker_x !== null && d.marker_y !== null ? `(${d.marker_x}%, ${d.marker_y}%)` : '—'}</td><td className="px-6 py-4 font-mono text-xs text-muted-foreground">{d.threshold_config ? `W: ${d.threshold_config.warning}°C / C: ${d.threshold_config.critical}°C` : 'Default'}</td><td className="px-6 py-4 text-right gap-2"><button onClick={() => handleStartPair(d)} className="px-2 py-1 bg-muted hover:bg-muted/80 text-foreground rounded text-[10px] font-medium cursor-pointer">Edit</button><button onClick={() => unpairMutation.mutate(d.dev_id)} disabled={unpairMutation.isPending} className="px-2 py-1 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/30 rounded text-[10px] font-medium cursor-pointer">Unpair</button></td></tr>); })}
              {activeDevices.length === 0 && <tr><td colSpan={7} className="px-6 py-6 text-center text-muted-foreground text-xs">No active paired devices.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {selectedDeviceToPair && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-card border rounded-lg p-6 max-w-lg w-full shadow-2xl flex flex-col gap-4">
            <div className="flex items-center justify-between border-b pb-3"><div><h3 className="font-bold text-foreground">Pair & Configure Device</h3><p className="text-xs text-muted-foreground font-mono">MAC: {selectedDeviceToPair.dev_id}</p></div><button onClick={() => setSelectedDeviceToPair(null)} className="text-muted-foreground hover:text-foreground text-sm">✕</button></div>
            <form onSubmit={handlePairSubmit} className="flex flex-col gap-4">
              <div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Device Friendly Name *</label><input type="text" value={pairName} onChange={(e) => setPairName(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div>
              <div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Room Assignment *</label><select value={pairRoomId} onChange={(e) => setPairRoomId(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"><option value="">Select Room...</option>{rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></div>
              <div className="grid grid-cols-2 gap-4"><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Map Position X (%)</label><input type="number" min="0" max="100" value={pairMarkerX} onChange={(e) => setPairMarkerX(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Map Position Y (%)</label><input type="number" min="0" max="100" value={pairMarkerY} onChange={(e) => setPairMarkerY(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div></div>
              <div className="grid grid-cols-2 gap-4"><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Warning Level (°C)</label><input type="number" step="0.1" value={pairWarn} onChange={(e) => setPairWarn(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Critical Level (°C)</label><input type="number" step="0.1" value={pairCrit} onChange={(e) => setPairCrit(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div></div>
              <div className="flex items-center justify-end gap-3 pt-4 border-t"><button type="button" onClick={() => setSelectedDeviceToPair(null)} className="px-4 py-2 border rounded hover:bg-muted text-muted-foreground text-xs font-medium cursor-pointer">Cancel</button><button type="submit" disabled={pairMutation.isPending} className="px-4 py-2 bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground rounded text-xs font-semibold cursor-pointer flex items-center gap-2">{pairMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : 'Confirm Pairing'}</button></div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
export default DevicesTab;
