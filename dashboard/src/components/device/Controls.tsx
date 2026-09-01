import { useState, useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Wind, Zap, CheckCircle, AlertTriangle, Loader2, Settings as SettingsIcon } from 'lucide-react';
import { cn } from '../../lib/utils';
import { queryKeys } from '../../lib/queryKeys';
import { updateThresholds } from '../../lib/api';
import { useCommandLifecycle } from '../../hooks/useCommandLifecycle';
import { CommandStatusBadge } from './CommandStatusBadge';
import type { ATSCommand, DeviceResponse, ThresholdUpdateRequest } from '../../types/api';

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

  const isEditingRef = useRef(false);
  const [isDirty, setIsDirty] = useState(false);

  const [warningThreshold, setWarningThreshold] = useState(
    device.threshold_config ? device.threshold_config.warning.toString() : isATS ? '11.8' : '28'
  );
  const [criticalThreshold, setCriticalThreshold] = useState(
    device.threshold_config ? device.threshold_config.critical.toString() : isATS ? '11.2' : '32'
  );
  const [hysteresis, setHysteresis] = useState(
    device.threshold_config ? device.threshold_config.hysteresis.toString() : isATS ? '0.2' : '0.5'
  );
  const [debounceSeconds, setDebounceSeconds] = useState(
    device.threshold_config ? device.threshold_config.debounce_seconds.toString() : '60'
  );
  const [configSuccess, setConfigSuccess] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const [commandPayload, setCommandPayload] = useState<ATSCommand>({});
  const [acTarget, setAcTarget] = useState<'AC1' | 'AC2'>('AC1');
  const [acAction, setAcAction] = useState<'ON' | 'OFF' | 'SET_TEMP'>('ON');
  const [acTemp, setAcTemp] = useState<number>(24);
  const [formValidationError, setFormValidationError] = useState<string | null>(null);

  const commandLifecycle = useCommandLifecycle();

  const warningVal = device.threshold_config?.warning;
  const criticalVal = device.threshold_config?.critical;
  const hysteresisVal = device.threshold_config?.hysteresis;
  const debounceVal = device.threshold_config?.debounce_seconds;

  useEffect(() => {
    if (isDirty || isEditingRef.current) return;
    if (warningVal !== undefined && criticalVal !== undefined) {
      setWarningThreshold(warningVal.toString());
      setCriticalThreshold(criticalVal.toString());
      setHysteresis(hysteresisVal !== undefined ? hysteresisVal.toString() : isATS ? '0.2' : '0.5');
      setDebounceSeconds(debounceVal !== undefined ? debounceVal.toString() : '60');
    } else {
      if (isATS) {
        setWarningThreshold('11.8');
        setCriticalThreshold('11.2');
        setHysteresis('0.2');
        setDebounceSeconds('60');
      } else {
        setWarningThreshold('28');
        setCriticalThreshold('32');
        setHysteresis('0.5');
        setDebounceSeconds('60');
      }
    }
  }, [warningVal, criticalVal, hysteresisVal, debounceVal, isATS, isDirty]);

  const handleResetToServer = () => {
    if (device.threshold_config) {
      setWarningThreshold(device.threshold_config.warning.toString());
      setCriticalThreshold(device.threshold_config.critical.toString());
      setHysteresis(device.threshold_config.hysteresis.toString());
      setDebounceSeconds(device.threshold_config.debounce_seconds.toString());
    } else {
      if (isATS) {
        setWarningThreshold('11.8');
        setCriticalThreshold('11.2');
        setHysteresis('0.2');
        setDebounceSeconds('60');
      } else {
        setWarningThreshold('28');
        setCriticalThreshold('32');
        setHysteresis('0.5');
        setDebounceSeconds('60');
      }
    }
    setIsDirty(false);
    setConfigError(null);
  };

  const thresholdMutation = useMutation({
    mutationFn: (payload: ThresholdUpdateRequest) => updateThresholds(device.dev_id, payload),
    onSuccess: (data) => {
      setConfigSuccess('Thresholds updated successfully');
      setConfigError(null);
      if (data) {
        setWarningThreshold(data.warning.toString());
        setCriticalThreshold(data.critical.toString());
        setHysteresis(data.hysteresis.toString());
        setDebounceSeconds(data.debounce_seconds.toString());
      }
      setIsDirty(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setConfigSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setConfigError(err.message || 'Failed to update threshold configuration');
      setConfigSuccess(null);
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
    if (isATS) {
      if (warn < crit) {
        setConfigError('For ATS battery undervoltage, Warning threshold must be greater than or equal to Critical threshold');
        return;
      }
    } else {
      if (warn > crit) {
        setConfigError('Warning threshold cannot exceed critical threshold');
        return;
      }
    }
    const defaultHyst = isATS ? 0.2 : 0.5;
    thresholdMutation.mutate({ warning: warn, critical: crit, hysteresis: isNaN(hyst) ? defaultHyst : hyst, debounce_seconds: isNaN(deb) ? 60 : deb });
  };

  const handleCommandSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormValidationError(null);
    if (device.dev_type === 'AC' || device.dev_type === 'ACC') {
      if (acAction === 'SET_TEMP' && (acTemp < 16 || acTemp > 30)) {
        setFormValidationError('Temperature must be between 16°C and 30°C');
        return;
      }
      await commandLifecycle.sendCommand(device.dev_id, {
        target: acTarget,
        action: acAction,
        ...(acAction === 'SET_TEMP' ? { temp: acTemp } : {}),
      });
      return;
    }
    if (!commandPayload.mode && !commandPayload.start_genset && !commandPayload.reset) {
      setFormValidationError('Select at least one command action to send');
      return;
    }
    await commandLifecycle.sendCommand(device.dev_id, commandPayload);
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
              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Target Air Conditioner Unit</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    disabled={commandLifecycle.isPending}
                    onClick={() => setAcTarget('AC1')}
                    className={cn(
                      "py-2.5 px-4 rounded border text-xs font-medium cursor-pointer transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed",
                      acTarget === 'AC1' ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    <Wind className="h-3.5 w-3.5" />
                    <span>Unit AC 1</span>
                  </button>
                  <button
                    type="button"
                    disabled={commandLifecycle.isPending}
                    onClick={() => setAcTarget('AC2')}
                    className={cn(
                      "py-2.5 px-4 rounded border text-xs font-medium cursor-pointer transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed",
                      acTarget === 'AC2' ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    <Wind className="h-3.5 w-3.5" />
                    <span>Unit AC 2</span>
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Control Action</label>
                <div className="grid grid-cols-3 gap-3">
                  <button
                    type="button"
                    disabled={commandLifecycle.isPending}
                    onClick={() => setAcAction('ON')}
                    className={cn(
                      "py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all disabled:opacity-50 disabled:cursor-not-allowed",
                      acAction === 'ON' ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    Power ON
                  </button>
                  <button
                    type="button"
                    disabled={commandLifecycle.isPending}
                    onClick={() => setAcAction('OFF')}
                    className={cn(
                      "py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all disabled:opacity-50 disabled:cursor-not-allowed",
                      acAction === 'OFF' ? "bg-red-500/20 border-red-500 text-red-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    Power OFF
                  </button>
                  <button
                    type="button"
                    disabled={commandLifecycle.isPending}
                    onClick={() => setAcAction('SET_TEMP')}
                    className={cn(
                      "py-2 px-3 rounded border text-xs font-medium cursor-pointer transition-all disabled:opacity-50 disabled:cursor-not-allowed",
                      acAction === 'SET_TEMP' ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 font-semibold" : "bg-zinc-950 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    )}
                  >
                    Set Temp
                  </button>
                </div>
              </div>
              {acAction === 'SET_TEMP' && (
                <div className="space-y-3 bg-zinc-950 p-4 rounded border border-zinc-800">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Target Temperature (°C)</label>
                    <span className="text-lg font-bold font-mono text-indigo-400">{acTemp} °C</span>
                  </div>
                  <input
                    type="range"
                    min="16"
                    max="30"
                    step="1"
                    disabled={commandLifecycle.isPending}
                    value={acTemp}
                    onChange={(e) => setAcTemp(parseInt(e.target.value, 10))}
                    className="w-full h-2 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                  <div className="flex items-center justify-between gap-1.5 pt-1">
                    {[18, 20, 22, 24, 26].map((tempVal) => (
                      <button
                        key={tempVal}
                        type="button"
                        disabled={commandLifecycle.isPending}
                        onClick={() => setAcTemp(tempVal)}
                        className={cn(
                          "px-2.5 py-1 rounded text-xs font-mono transition-colors cursor-pointer border disabled:opacity-50 disabled:cursor-not-allowed",
                          acTemp === tempVal ? "bg-indigo-600 border-indigo-500 text-white font-bold" : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        )}
                      >
                        {tempVal}°C
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={commandLifecycle.isPending}
                  className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-xs font-semibold cursor-pointer flex items-center gap-2 transition-all shadow-lg shadow-indigo-600/20"
                >
                  {commandLifecycle.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>{commandLifecycle.commandStatus === 'queuing' ? 'Queuing IR Command...' : 'Waiting for Delivery...'}</span>
                    </>
                  ) : (
                    <>
                      <Wind className="h-3.5 w-3.5" />
                      <span>Send AC IR Command</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
          {canControl && isATS && (
            <form onSubmit={handleCommandSubmit} className="space-y-4 pt-2">
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
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="ats-mode-select" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Operating Mode</label>
                  <select
                    id="ats-mode-select"
                    disabled={commandLifecycle.isPending}
                    value={commandPayload.mode || ''}
                    onChange={(e) => setCommandPayload({ ...commandPayload, mode: (e.target.value as 'auto' | 'manual') || undefined })}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <option value="">Select Mode...</option>
                    <option value="auto">Auto Mode</option>
                    <option value="manual">Manual Mode</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="ats-genset-select" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Genset Start / Stop</label>
                  <select
                    id="ats-genset-select"
                    disabled={commandLifecycle.isPending}
                    value={commandPayload.start_genset || ''}
                    onChange={(e) => setCommandPayload({ ...commandPayload, start_genset: (e.target.value as 'on' | 'off') || undefined })}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-200 text-sm focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <option value="">Select Genset Action...</option>
                    <option value="on">Start Genset (ON)</option>
                    <option value="off">Stop Genset (OFF)</option>
                  </select>
                </div>
              </div>
              {isAdmin && (
                <div className="pt-2">
                  <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      disabled={commandLifecycle.isPending}
                      checked={commandPayload.reset === 'rst'}
                      onChange={(e) => setCommandPayload({ ...commandPayload, reset: e.target.checked ? 'rst' : undefined })}
                      className="rounded border-zinc-700 bg-zinc-950 text-indigo-600 focus:ring-indigo-500 disabled:opacity-50"
                    />
                    <span>Issue controller reboot / reset (`rst`)</span>
                  </label>
                </div>
              )}
              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={commandLifecycle.isPending}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded text-xs font-medium cursor-pointer flex items-center gap-2"
                >
                  {commandLifecycle.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>{commandLifecycle.commandStatus === 'queuing' ? 'Dispatching...' : 'Awaiting Hub Delivery...'}</span>
                    </>
                  ) : (
                    <span>Send Command</span>
                  )}
                </button>
              </div>
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
            <div>
              <label htmlFor="warning-threshold-input" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">{isATS ? 'Battery Warning Threshold (V)' : 'Warning Threshold (°C)'}</label>
              <input
                id="warning-threshold-input"
                type="number"
                step="0.1"
                value={warningThreshold}
                onFocus={() => { isEditingRef.current = true; }}
                onBlur={() => { isEditingRef.current = false; }}
                onChange={(e) => { setWarningThreshold(e.target.value); setIsDirty(true); }}
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label htmlFor="critical-threshold-input" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">{isATS ? 'Battery Critical Threshold (V)' : 'Critical Threshold (°C)'}</label>
              <input
                id="critical-threshold-input"
                type="number"
                step="0.1"
                value={criticalThreshold}
                onFocus={() => { isEditingRef.current = true; }}
                onBlur={() => { isEditingRef.current = false; }}
                onChange={(e) => { setCriticalThreshold(e.target.value); setIsDirty(true); }}
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label htmlFor="hysteresis-input" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">{isATS ? 'Hysteresis (V)' : 'Hysteresis (°C)'}</label>
              <input
                id="hysteresis-input"
                type="number"
                step="0.1"
                value={hysteresis}
                onFocus={() => { isEditingRef.current = true; }}
                onBlur={() => { isEditingRef.current = false; }}
                onChange={(e) => { setHysteresis(e.target.value); setIsDirty(true); }}
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[10px] text-zinc-500 mt-1 block">Recovery offset to prevent oscillations.</span>
            </div>
            <div>
              <label htmlFor="debounce-input" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-1.5">Debounce Window (Seconds)</label>
              <input
                id="debounce-input"
                type="number"
                value={debounceSeconds}
                onFocus={() => { isEditingRef.current = true; }}
                onBlur={() => { isEditingRef.current = false; }}
                onChange={(e) => { setDebounceSeconds(e.target.value); setIsDirty(true); }}
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500"
              />
              <span className="text-[10px] text-zinc-500 mt-1 block">Minimum cooldown period between logged alert events.</span>
            </div>
            <div className="pt-2 flex flex-col sm:flex-row gap-2">
              <button
                type="submit"
                disabled={thresholdMutation.isPending}
                className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium transition-colors cursor-pointer flex items-center justify-center gap-2"
              >
                {thresholdMutation.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <span>Save Thresholds</span>
                )}
              </button>
              {isDirty && (
                <button
                  type="button"
                  onClick={handleResetToServer}
                  className="py-2 px-3 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded text-xs font-medium transition-colors cursor-pointer"
                >
                  Reset to Server Values
                </button>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
export default DeviceControls;
