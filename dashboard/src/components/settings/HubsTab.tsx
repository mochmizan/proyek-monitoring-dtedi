import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Sliders, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { queryKeys } from '../../lib/queryKeys';
import { fetchDevices, updateThresholds } from '../../lib/api';
import type { ThresholdUpdateRequest } from '../../types/api';

// This tab reuses the global thresholds configuration (named HubsTab per task spec; thresholds logic lives here)
export function HubsTab() {
  const queryClient = useQueryClient();
  const { data: activeDevices = [] } = useQuery({ queryKey: queryKeys.devices.active(), queryFn: () => fetchDevices('active') });
  const [threshDevId, setThreshDevId] = useState('');
  const [threshWarn, setThreshWarn] = useState('30');
  const [threshCrit, setThreshCrit] = useState('35');
  const [threshHyst, setThreshHyst] = useState('0.5');
  const [threshDebounce, setThreshDebounce] = useState('60');
  const [threshError, setThreshError] = useState<string | null>(null);
  const [threshSuccess, setThreshSuccess] = useState<string | null>(null);

  const thresholdMutation = useMutation({
    mutationFn: ({ devId, payload }: { devId: string; payload: ThresholdUpdateRequest }) => updateThresholds(devId, payload),
    onSuccess: () => {
      setThreshSuccess('Device threshold configuration updated'); setThreshError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all }); queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all }); setTimeout(() => setThreshSuccess(null), 3000);
    },
    onError: (err: Error) => setThreshError(err.message),
  });

  const handleThresholdSelectDevice = (devId: string) => {
    setThreshDevId(devId);
    const target = activeDevices.find((d) => d.dev_id === devId);
    if (target?.threshold_config) {
      setThreshWarn(target.threshold_config.warning.toString()); setThreshCrit(target.threshold_config.critical.toString());
      setThreshHyst(target.threshold_config.hysteresis.toString()); setThreshDebounce(target.threshold_config.debounce_seconds.toString());
    }
    setThreshError(null);
  };
  const handleThresholdFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!threshDevId) { setThreshError('Please select a device to configure'); return; }
    const warn = parseFloat(threshWarn); const crit = parseFloat(threshCrit); const hyst = parseFloat(threshHyst); const deb = parseInt(threshDebounce, 10);
    if (isNaN(warn) || isNaN(crit)) { setThreshError('Warning and Critical values must be numbers'); return; }
    if (warn > crit) { setThreshError('Warning threshold cannot exceed Critical threshold'); return; }
    thresholdMutation.mutate({ devId: threshDevId, payload: { warning: warn, critical: crit, hysteresis: isNaN(hyst) ? 0.5 : hyst, debounce_seconds: isNaN(deb) ? 60 : deb } });
  };

  return (
    <div className="flex flex-col gap-6">
      {threshError && <div className="bg-destructive/10 border border-destructive/20 text-destructive text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="size-4 flex-shrink-0" /><span>{threshError}</span></div>}
      {threshSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="size-4 flex-shrink-0" /><span>{threshSuccess}</span></div>}
      <div className="bg-card border rounded-lg p-6 max-w-xl">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4 flex items-center gap-2"><Sliders className="size-4 text-primary" /><span>Configure Device Alert Parameters</span></h3>
        <form onSubmit={handleThresholdFormSubmit} className="flex flex-col gap-4">
          <div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Target Device *</label><select value={threshDevId} onChange={(e) => handleThresholdSelectDevice(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"><option value="">Select an active device...</option>{activeDevices.map((d) => <option key={d.dev_id} value={d.dev_id}>{d.dev_name || d.dev_id} ({d.dev_type || 'Device'})</option>)}</select></div>
          <div className="grid grid-cols-2 gap-4"><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Warning Level (°C)</label><input type="number" step="0.1" value={threshWarn} onChange={(e) => setThreshWarn(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Critical Level (°C)</label><input type="number" step="0.1" value={threshCrit} onChange={(e) => setThreshCrit(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div></div>
          <div className="grid grid-cols-2 gap-4"><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Hysteresis Offset (°C)</label><input type="number" step="0.1" value={threshHyst} onChange={(e) => setThreshHyst(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div><div><label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Debounce Window (s)</label><input type="number" value={threshDebounce} onChange={(e) => setThreshDebounce(e.target.value)} className="w-full bg-muted border rounded px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary" /></div></div>
          <div className="pt-2"><button type="submit" disabled={thresholdMutation.isPending || !threshDevId} className="w-full py-2 bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground rounded text-xs font-semibold cursor-pointer flex items-center justify-center gap-2">{thresholdMutation.isPending ? <Loader2 data-icon="inline-start" className="animate-spin" /> : 'Save Parameters'}</button></div>
        </form>
      </div>
    </div>
  );
}
export default HubsTab;
