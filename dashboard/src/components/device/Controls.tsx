import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Wind, Zap, CheckCircle, AlertTriangle, Loader2, Settings as SettingsIcon } from 'lucide-react';
import { cn } from '../../lib/utils';
import { queryKeys } from '../../lib/queryKeys';
import { updateThresholds, sendDeviceCommand } from '../../lib/api';
import type { ATSCommand, DeviceResponse, ThresholdUpdateRequest, DeviceCommand } from '../../types/api';

interface ControlsProps {
  device: DeviceResponse;
  role: string;
}

export function DeviceControls({ device, role }: ControlsProps) {
  const queryClient = useQueryClient();
  const isATS = device.dev_type === 'ATS';
  const isAC = device.dev_type === 'AC' || device.dev_type === 'ACC';
  const isAdmin = role === 'admin';
  const canControl = role === 'admin' || role === 'operator';

  const [warningThreshold, setWarningThreshold] = useState('30');
  const [criticalThreshold, setCriticalThreshold] = useState('35');
  const [hysteresis, setHysteresis] = useState('0.5');
  const [debounceSeconds, setDebounceSeconds] = useState('60');
  const [configSuccess, setConfigSuccess] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const [commandPayload, setCommandPayload] = useState<ATSCommand>({});
  const [acTarget, setAcTarget] = useState<'AC1' | 'AC2'>('AC1');
  const [acAction, setAcAction] = useState<'ON' | 'OFF' | 'SET_TEMP'>('ON');
  const [acTemp, setAcTemp] = useState<number>(24);
  const [cmdSuccess, setCmdSuccess] = useState<string | null>(null);
  const [cmdError, setCmdError] = useState<string | null>(null);

  useEffect(() => {
    if (device.threshold_config) {
      setWarningThreshold(device.threshold_config.warning.toString());
      setCriticalThreshold(device.threshold_config.critical.toString());
      setHysteresis(device.threshold_config.hysteresis.toString());
      setDebounceSeconds(device.threshold_config.debounce_seconds.toString());
    }
  }, [device]);

  const thresholdMutation = useMutation({
    mutationFn: (payload: ThresholdUpdateRequest) => updateThresholds(device.dev_id, payload),
    onSuccess: () => {
      setConfigSuccess('Thresholds updated successfully');
      setConfigError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setConfigSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setConfigError(err.message || 'Failed to update threshold configuration');
      setConfigSuccess(null);
    },
  });

  const commandMutation = useMutation({
    mutationFn: (payload: DeviceCommand) => sendDeviceCommand(device.dev_id, payload),
    onSuccess: () => {
      setCmdSuccess('Command queued successfully for edge delivery');
      setCmdError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setCmdSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setCmdError(err.message || 'Failed to dispatch command');
      setCmdSuccess(null);
    },
  });

  const handleThresholdSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setConfigError(null);
    setConfigSuccess(null);
    const warn = parseFloat(warningThreshold);
    const crit = parseFloat(criticalThreshold);
    const hyst = parseFloat(hysteresis);
    const deb = parseInt(debounceSeconds, 10);
    if (isNaN(warn) || isNaN(crit)) { setConfigError('Warning and Critical thresholds must be valid numbers'); return; }
    if (warn > crit) { setConfigError('Warning threshold cannot exceed critical threshold'); return; }
    thresholdMutation.mutate({ warning: warn, critical: crit, hysteresis: isNaN(hyst) ? 0.5 : hyst, debounce_seconds: isNaN(deb) ? 60 : deb });
  };

  const handleCommandSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCmdError(null);
    setCmdSuccess(null);
    if (device.dev_type === 'AC' || device.dev_type === 'ACC') {
      if (acAction === 'SET_TEMP' && (acTemp < 16 || acTemp > 30)) { setCmdError('Temperature must be between 16°C and 30°C'); return; }
      commandMutation.mutate({ target: acTarget, action: acAction, ...(acAction === 'SET_TEMP' ? { temp: acTemp } : {}) });
      return;
    }
    if (!commandPayload.mode && !commandPayload.start_genset && !commandPayload.reset) { setCmdError('Select at least one command action to send'); return; }
    commandMutation.mutate(commandPayload);
  };

  return (
    <div className="space-y-6">
      {(isATS || isAC) && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
            {isAC ? <Wind className="h-4 w-4 text-emerald-400" /> : <Zap className="h-4 w-4 text-indigo-400" />}
            <span>{isAC ? 'Air Conditioner Control Panel' : 'ATS Generator Command Dispatch'}</span>
          </h3>
          {!canControl && <div className="bg-zinc-950 border border-zinc-800 rounded p-4 text-zinc-500 text-xs">Your current role ({role}) does not have permission to issue hardware commands.</div>}
          {canControl && isAC && (
            <form onSubmit={handleCommandSubmit} className="space-y-5 pt-2">
              {cmdError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="h-4 w-4 flex-shrink-0" /><span>{cmdError}</span></div>}
              {cmdSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="h-4 w-4 flex-shrink-0" /><span>{cmdSuccess}</span></div>}
              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Target Air Conditioner Unit</label>
                <div className="grid grid-cols-2 gap-3">
                  <button type="button" onClick={() => setAcTarget('AC1')} className={cn("py-2.5 px-4 rounded border text-xs font-medium cursor-pointer transition-all flex items-center justify-center gap-2", acTarget === 'AC1' ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200")}><Wind className="h-3.5 w-3.5" /><span>Unit AC 1</span></button>
                  <button type="button" onClick={() => setAcTarget('AC2')} className={cn("py-2.5 px-4 rounded border text-xs font-medium cursor-pointer transition-all flex items-center justify-center gap-2", acTarget === 'AC2' ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200")}><Wind className="h-3.5 w-3.5" /><span>Unit AC 2</span></button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Control Action</label>
                <div className="grid grid-cols-3 gap-3">
                  <button type="button" onClick={() => setAcAction('ON')} className={cn("py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all", acAction === 'ON' ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200")}>Power ON</button>
                  <button type="button" onClick={() => setAcAction('OFF')} className={cn("py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all", acAction === 'OFF' ? "bg-red-500/20 border-red-500 text-red-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200")}>Power OFF</button>
                  <button type="button" onClick={() => setAcAction('SET_TEMP')} className={cn("py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all", acAction === 'SET_TEMP' ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200")}>Set Temp</button>
                </div>
              </div>
              {acAction === 'SET_TEMP' && (
                <div className="space-y-3 bg-zinc-950 p-4 rounded border border-zinc-800">
                  <div className="flex items-center justify-between"><label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Target Temperature (°C)</label><span className="text-lg font-bold font-mono text-indigo-400">{acTemp} °C</span></div>
                  <input type="range" min="16" max="30" step="1" value={acTemp} onChange={(e) => setAcTemp(parseInt(e.target.value, 10))} className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500" />
                  <div className="flex items-center justify-between gap-1.5 pt-1">{[18, 20, 22, 24, 26].map((tempVal) => (<button key={tempVal} type="button" onClick={() => setAcTemp(tempVal)} className={cn("px-2.5 py-1 rounded text-xs font-mono transition-colors cursor-pointer border", acTemp === tempVal ? "bg-indigo-600 border-indigo-500 text-white font-bold" : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200")}>{tempVal}°C</button>))}</div>
                </div>
              )}
              <div className="flex justify-end pt-2"><button type="submit" disabled={commandMutation.isPending} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer flex items-center gap-2 transition-all shadow-lg shadow-indigo-600/20">{commandMutation.isPending ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /><span>Sending IR Command...</span></> : <><Wind className="h-3.5 w-3.5" /><span>Send AC IR Command</span></>}</button></div>
            </form>
          )}
          {canControl && isATS && (
            <form onSubmit={handleCommandSubmit} className="space-y-4 pt-2">
              {cmdError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="h-4 w-4 flex-shrink-0" /><span>{cmdError}</span></div>}
              {cmdSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="h-4 w-4 flex-shrink-0" /><span>{cmdSuccess}</span></div>}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div><label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Operating Mode</label><select value={commandPayload.mode || ''} onChange={(e) => setCommandPayload({ ...commandPayload, mode: (e.target.value as 'auto' | 'manual') || undefined })} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500"><option value="">Select Mode...</option><option value="auto">Auto Mode</option><option value="manual">Manual Mode</option></select></div>
                <div><label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Genset Start / Stop</label><select value={commandPayload.start_genset || ''} onChange={(e) => setCommandPayload({ ...commandPayload, start_genset: (e.target.value as 'on' | 'off') || undefined })} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500"><option value="">Select Genset Action...</option><option value="on">Start Genset (ON)</option><option value="off">Stop Genset (OFF)</option></select></div>
              </div>
              {isAdmin && (<div className="pt-2"><label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer"><input type="checkbox" checked={commandPayload.reset === 'rst'} onChange={(e) => setCommandPayload({ ...commandPayload, reset: e.target.checked ? 'rst' : undefined })} className="rounded border-zinc-700 bg-zinc-950 text-indigo-600 focus:ring-indigo-500" /><span>Issue controller reboot / reset (`rst`)</span></label></div>)}
              <div className="flex justify-end pt-2"><button type="submit" disabled={commandMutation.isPending} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium cursor-pointer flex items-center gap-2">{commandMutation.isPending ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /><span>Dispatching...</span></> : <span>Send Command</span>}</button></div>
            </form>
          )}
        </div>
      )}

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2"><SettingsIcon className="h-4 w-4 text-indigo-400" /><span>Thresholds & Debounce</span></h3>
        {!isAdmin && <div className="bg-zinc-950 border border-zinc-800 rounded p-4 text-zinc-500 text-xs">Admin permissions required to modify alert threshold parameters.</div>}
        {isAdmin && (
          <form onSubmit={handleThresholdSubmit} className="space-y-4">
            {configError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="h-4 w-4 flex-shrink-0" /><span>{configError}</span></div>}
            {configSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="h-4 w-4 flex-shrink-0" /><span>{configSuccess}</span></div>}
            <div><label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Warning Threshold (°C)</label><input type="number" step="0.1" value={warningThreshold} onChange={(e) => setWarningThreshold(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500" /></div>
            <div><label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Critical Threshold (°C)</label><input type="number" step="0.1" value={criticalThreshold} onChange={(e) => setCriticalThreshold(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500" /></div>
            <div><label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Hysteresis (°C)</label><input type="number" step="0.1" value={hysteresis} onChange={(e) => setHysteresis(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500" /><span className="text-[10px] text-zinc-500 mt-1 block">Recovery offset to prevent oscillations.</span></div>
            <div><label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Debounce Window (Seconds)</label><input type="number" value={debounceSeconds} onChange={(e) => setDebounceSeconds(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500" /><span className="text-[10px] text-zinc-500 mt-1 block">Minimum cooldown period between logged alert events.</span></div>
            <div className="pt-2"><button type="submit" disabled={thresholdMutation.isPending} className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium transition-colors cursor-pointer flex items-center justify-center gap-2">{thresholdMutation.isPending ? <><Loader2 className="h-3.5 w-3.5 animate-spin" /><span>Saving...</span></> : <span>Save Thresholds</span>}</button></div>
          </form>
        )}
      </div>
    </div>
  );
}
export default DeviceControls;
