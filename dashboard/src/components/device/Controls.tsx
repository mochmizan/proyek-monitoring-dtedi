import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Wind, Zap, CheckCircle, AlertTriangle, Loader2, Settings as SettingsIcon } from "lucide-react";
import { queryKeys } from "../../lib/queryKeys";
import { updateThresholds, sendDeviceCommand } from "../../lib/api";
import type { ATSCommand, DeviceResponse, ThresholdUpdateRequest, DeviceCommand } from "../../types/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { FieldGroup, Field, FieldLabel, FieldDescription } from "@/components/ui/field";
import { InputGroup, InputGroupInput, InputGroupAddon } from "@/components/ui/input-group";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

interface ControlsProps {
  device: DeviceResponse;
  role: string;
}

// ── AC Controls compound ────────────────────────────────────────────────────

function AcControls({
  acTarget,
  setAcTarget,
  acAction,
  setAcAction,
  acTemp,
  setAcTemp,
  onSubmit,
  pending,
  cmdError,
  cmdSuccess,
}: {
  acTarget: "AC1" | "AC2";
  setAcTarget: (v: "AC1" | "AC2") => void;
  acAction: "ON" | "OFF" | "SET_TEMP";
  setAcAction: (v: "ON" | "OFF" | "SET_TEMP") => void;
  acTemp: number;
  setAcTemp: (v: number) => void;
  onSubmit: (e: React.FormEvent) => void;
  pending: boolean;
  cmdError: string | null;
  cmdSuccess: string | null;
}) {
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {cmdError && (
        <Alert variant="destructive">
          <AlertTriangle data-icon="inline-start" />
          <AlertTitle>Failed</AlertTitle>
          <AlertDescription>{cmdError}</AlertDescription>
        </Alert>
      )}
      {cmdSuccess && (
        <Alert>
          <CheckCircle data-icon="inline-start" />
          <AlertTitle>Queued</AlertTitle>
          <AlertDescription>{cmdSuccess}</AlertDescription>
        </Alert>
      )}

      <FieldGroup>
        <Field>
          <FieldLabel>Target Air Conditioner Unit</FieldLabel>
          <ToggleGroup type="single" value={acTarget} onValueChange={(v) => v && setAcTarget(v as "AC1" | "AC2")} variant="outline" size="sm">
            <ToggleGroupItem value="AC1" aria-label="AC1">
              <Wind data-icon="inline-start" />
              Unit AC 1
            </ToggleGroupItem>
            <ToggleGroupItem value="AC2" aria-label="AC2">
              <Wind data-icon="inline-start" />
              Unit AC 2
            </ToggleGroupItem>
          </ToggleGroup>
        </Field>

        <Field>
          <FieldLabel>Control Action</FieldLabel>
          <ToggleGroup type="single" value={acAction} onValueChange={(v) => v && setAcAction(v as "ON" | "OFF" | "SET_TEMP")} variant="outline" size="sm">
            <ToggleGroupItem value="ON">Power ON</ToggleGroupItem>
            <ToggleGroupItem value="OFF">Power OFF</ToggleGroupItem>
            <ToggleGroupItem value="SET_TEMP">Set Temp</ToggleGroupItem>
          </ToggleGroup>
        </Field>

        {acAction === "SET_TEMP" && (
          <Field>
            <FieldLabel htmlFor="ac-temp">Target Temperature</FieldLabel>
            <div className="flex flex-col gap-3 rounded-md border bg-card p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Target °C</span>
                <span className="font-mono text-lg font-bold text-primary truncate">{acTemp} °C</span>
              </div>
              <input
                id="ac-temp"
                type="range"
                min={16}
                max={30}
                step={1}
                value={acTemp}
                onChange={(e) => setAcTemp(parseInt(e.target.value, 10))}
                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
              />
              <div className="flex items-center justify-between gap-1.5">
                {[18, 20, 22, 24, 26].map((tempVal) => (
                  <Button
                    key={tempVal}
                    type="button"
                    variant={acTemp === tempVal ? "default" : "outline"}
                    size="sm"
                    onClick={() => setAcTemp(tempVal)}
                    className="font-mono text-xs px-2.5"
                  >
                    {tempVal}°C
                  </Button>
                ))}
              </div>
            </div>
            <FieldDescription>16–30°C via IR blaster</FieldDescription>
          </Field>
        )}
      </FieldGroup>

      <Separator />

      <div className="flex justify-end">
        <Button type="submit" disabled={pending} className="gap-2">
          {pending ? (
            <>
              <Loader2 data-icon="inline-start" className="animate-spin" />
              Sending IR Command...
            </>
          ) : (
            <>
              <Wind data-icon="inline-start" />
              Send AC IR Command
            </>
          )}
        </Button>
      </div>
    </form>
  );
}

// ── ATS Controls compound ───────────────────────────────────────────────────

function AtsControls({
  commandPayload,
  setCommandPayload,
  isAdmin,
  onSubmit,
  pending,
  cmdError,
  cmdSuccess,
}: {
  commandPayload: ATSCommand;
  setCommandPayload: (v: ATSCommand) => void;
  isAdmin: boolean;
  onSubmit: (e: React.FormEvent) => void;
  pending: boolean;
  cmdError: string | null;
  cmdSuccess: string | null;
}) {
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {cmdError && (
        <Alert variant="destructive">
          <AlertTriangle data-icon="inline-start" />
          <AlertTitle>Failed</AlertTitle>
          <AlertDescription>{cmdError}</AlertDescription>
        </Alert>
      )}
      {cmdSuccess && (
        <Alert>
          <CheckCircle data-icon="inline-start" />
          <AlertTitle>Queued</AlertTitle>
          <AlertDescription>{cmdSuccess}</AlertDescription>
        </Alert>
      )}

      <FieldGroup>
        <Field>
          <FieldLabel>Operating Mode</FieldLabel>
          <ToggleGroup
            type="single"
            value={commandPayload.mode || ""}
            onValueChange={(v) => setCommandPayload({ ...commandPayload, mode: (v as "auto" | "manual") || undefined })}
            variant="outline"
            size="sm"
          >
            <ToggleGroupItem value="auto">Auto</ToggleGroupItem>
            <ToggleGroupItem value="manual">Manual</ToggleGroupItem>
          </ToggleGroup>
          <FieldDescription>Controller auto/manual selection</FieldDescription>
        </Field>

        <Field>
          <FieldLabel>Genset Start / Stop</FieldLabel>
          <ToggleGroup
            type="single"
            value={commandPayload.start_genset || ""}
            onValueChange={(v) => setCommandPayload({ ...commandPayload, start_genset: (v as "on" | "off") || undefined })}
            variant="outline"
            size="sm"
          >
            <ToggleGroupItem value="on">Start ON</ToggleGroupItem>
            <ToggleGroupItem value="off">Stop OFF</ToggleGroupItem>
          </ToggleGroup>
          <FieldDescription>Requires manual mode for direct genset control</FieldDescription>
        </Field>

        {isAdmin && (
          <Field orientation="horizontal">
            <Switch
              id="ats-reset"
              checked={commandPayload.reset === "rst"}
              onCheckedChange={(c) => setCommandPayload({ ...commandPayload, reset: c ? "rst" : undefined })}
            />
            <div className="flex flex-col gap-1">
              <Label htmlFor="ats-reset" className="text-sm leading-none">
                Controller reboot (admin)
              </Label>
              <FieldDescription>Issue hardware reset `rst`</FieldDescription>
            </div>
          </Field>
        )}
      </FieldGroup>

      <Separator />

      <div className="flex justify-end">
        <Button type="submit" disabled={pending} className="gap-2">
          {pending ? (
            <>
              <Loader2 data-icon="inline-start" className="animate-spin" />
              Dispatching...
            </>
          ) : (
            <>Queue Command</>
          )}
        </Button>
      </div>
    </form>
  );
}

// ── Threshold Form compound ─────────────────────────────────────────────────

function ThresholdForm({
  warningThreshold,
  setWarningThreshold,
  criticalThreshold,
  setCriticalThreshold,
  hysteresis,
  setHysteresis,
  debounceSeconds,
  setDebounceSeconds,
  onSubmit,
  pending,
  configError,
  configSuccess,
}: {
  warningThreshold: string;
  setWarningThreshold: (v: string) => void;
  criticalThreshold: string;
  setCriticalThreshold: (v: string) => void;
  hysteresis: string;
  setHysteresis: (v: string) => void;
  debounceSeconds: string;
  setDebounceSeconds: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  pending: boolean;
  configError: string | null;
  configSuccess: string | null;
}) {
  const warnVal = parseFloat(warningThreshold);
  const critVal = parseFloat(criticalThreshold);
  const warnError = !isNaN(warnVal) && !isNaN(critVal) && warnVal > critVal ? "Warning cannot exceed critical" : configError?.toLowerCase().includes("warning") ? configError : null;
  const critError = !isNaN(warnVal) && !isNaN(critVal) && warnVal > critVal ? "Critical must be >= warning" : null;
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {configError && (
        <Alert variant="destructive">
          <AlertTriangle data-icon="inline-start" />
          <AlertTitle>Failed</AlertTitle>
          <AlertDescription>{configError}</AlertDescription>
        </Alert>
      )}
      {configSuccess && (
        <Alert>
          <CheckCircle data-icon="inline-start" />
          <AlertTitle>Saved</AlertTitle>
          <AlertDescription>{configSuccess}</AlertDescription>
        </Alert>
      )}

      <FieldGroup>
        <Field data-invalid={!!warnError}>
          <FieldLabel htmlFor="warn">Warning Threshold</FieldLabel>
          <InputGroup>
            <InputGroupInput id="warn" type="number" step="0.1" value={warningThreshold} onChange={(e) => setWarningThreshold(e.target.value)} aria-invalid={!!warnError} />
            <InputGroupAddon align="inline-end">°C</InputGroupAddon>
          </InputGroup>
          <FieldDescription className={warnError ? "text-destructive" : undefined}>{warnError ?? "Trigger warning alert above this temperature"}</FieldDescription>
        </Field>

        <Field data-invalid={!!critError}>
          <FieldLabel htmlFor="crit">Critical Threshold</FieldLabel>
          <InputGroup>
            <InputGroupInput id="crit" type="number" step="0.1" value={criticalThreshold} onChange={(e) => setCriticalThreshold(e.target.value)} aria-invalid={!!critError} />
            <InputGroupAddon align="inline-end">°C</InputGroupAddon>
          </InputGroup>
          <FieldDescription className={critError ? "text-destructive" : undefined}>{critError ?? "Trigger critical alert above this temperature"}</FieldDescription>
        </Field>

        <Separator />

        <Field>
          <FieldLabel htmlFor="hyst">Hysteresis</FieldLabel>
          <InputGroup>
            <InputGroupInput id="hyst" type="number" step="0.1" value={hysteresis} onChange={(e) => setHysteresis(e.target.value)} />
            <InputGroupAddon align="inline-end">°C</InputGroupAddon>
          </InputGroup>
          <FieldDescription>Recovery offset to prevent oscillations.</FieldDescription>
        </Field>

        <Field>
          <FieldLabel htmlFor="debounce">Debounce Window</FieldLabel>
          <InputGroup>
            <InputGroupInput id="debounce" type="number" value={debounceSeconds} onChange={(e) => setDebounceSeconds(e.target.value)} />
            <InputGroupAddon align="inline-end">s</InputGroupAddon>
          </InputGroup>
          <FieldDescription>Minimum cooldown between logged alert events.</FieldDescription>
        </Field>
      </FieldGroup>

      <Button type="submit" disabled={pending} className="gap-2 w-full">
        {pending ? (
          <>
            <Loader2 data-icon="inline-start" className="animate-spin" />
            Saving...
          </>
        ) : (
          <>Save Thresholds</>
        )}
      </Button>
    </form>
  );
}

// ── Main export ─────────────────────────────────────────────────────────────

export function DeviceControls({ device, role }: ControlsProps) {
  const queryClient = useQueryClient();
  const isATS = device.dev_type === "ATS";
  const isAC = device.dev_type === "AC" || device.dev_type === "ACC";
  const isAdmin = role === "admin";
  const canControl = role === "admin" || role === "operator";

  const [warningThreshold, setWarningThreshold] = useState("30");
  const [criticalThreshold, setCriticalThreshold] = useState("35");
  const [hysteresis, setHysteresis] = useState("0.5");
  const [debounceSeconds, setDebounceSeconds] = useState("60");
  const [configSuccess, setConfigSuccess] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const [commandPayload, setCommandPayload] = useState<ATSCommand>({});
  const [acTarget, setAcTarget] = useState<"AC1" | "AC2">("AC1");
  const [acAction, setAcAction] = useState<"ON" | "OFF" | "SET_TEMP">("ON");
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
      setConfigSuccess("Thresholds updated successfully");
      setConfigError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setConfigSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setConfigError(err.message || "Failed to update threshold configuration");
      setConfigSuccess(null);
    },
  });

  const commandMutation = useMutation({
    mutationFn: (payload: DeviceCommand) => sendDeviceCommand(device.dev_id, payload),
    onSuccess: () => {
      setCmdSuccess("Command queued successfully for edge delivery");
      setCmdError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setCmdSuccess(null), 3000);
    },
    onError: (err: Error) => {
      setCmdError(err.message || "Failed to dispatch command");
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
    if (isNaN(warn) || isNaN(crit)) {
      setConfigError("Warning and Critical thresholds must be valid numbers");
      return;
    }
    if (warn > crit) {
      setConfigError("Warning threshold cannot exceed critical threshold");
      return;
    }
    thresholdMutation.mutate({
      warning: warn,
      critical: crit,
      hysteresis: isNaN(hyst) ? 0.5 : hyst,
      debounce_seconds: isNaN(deb) ? 60 : deb,
    });
  };

  const handleCommandSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCmdError(null);
    setCmdSuccess(null);
    if (device.dev_type === "AC" || device.dev_type === "ACC") {
      if (acAction === "SET_TEMP" && (acTemp < 16 || acTemp > 30)) {
        setCmdError("Temperature must be between 16°C and 30°C");
        return;
      }
      commandMutation.mutate({ target: acTarget, action: acAction, ...(acAction === "SET_TEMP" ? { temp: acTemp } : {}) });
      return;
    }
    if (!commandPayload.mode && !commandPayload.start_genset && !commandPayload.reset) {
      setCmdError("Select at least one command action to send");
      return;
    }
    commandMutation.mutate(commandPayload);
  };

  return (
    <div className="flex flex-col gap-6">
      {(isATS || isAC) && (
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              {isAC ? <Wind className="size-4 text-primary" data-icon="inline-start" /> : <Zap className="size-4 text-primary" data-icon="inline-start" />}
              {isAC ? "Air Conditioner Control" : "ATS Generator Command"}
            </CardTitle>
            <CardDescription className="text-xs">Queue a command for edge delivery via pending_commands</CardDescription>
          </CardHeader>
          <Separator />
          <CardContent className="pt-4 flex flex-col gap-4">
            {!canControl ? (
              <Alert>
                <AlertTriangle data-icon="inline-start" />
                <AlertTitle>Restricted</AlertTitle>
                <AlertDescription>
                  Your current role (<Badge variant="outline" className="font-mono">{role}</Badge>) does not have permission to issue hardware commands.
                </AlertDescription>
              </Alert>
            ) : isAC ? (
              <AcControls
                acTarget={acTarget}
                setAcTarget={setAcTarget}
                acAction={acAction}
                setAcAction={setAcAction}
                acTemp={acTemp}
                setAcTemp={setAcTemp}
                onSubmit={handleCommandSubmit}
                pending={commandMutation.isPending}
                cmdError={cmdError}
                cmdSuccess={cmdSuccess}
              />
            ) : (
              <AtsControls
                commandPayload={commandPayload}
                setCommandPayload={setCommandPayload}
                isAdmin={isAdmin}
                onSubmit={handleCommandSubmit}
                pending={commandMutation.isPending}
                cmdError={cmdError}
                cmdSuccess={cmdSuccess}
              />
            )}
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <SettingsIcon className="size-4 text-primary" data-icon="inline-start" />
            Thresholds & Debounce
          </CardTitle>
          <CardDescription className="text-xs">Alert thresholds — evaluated server-side at ingest</CardDescription>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4 flex flex-col gap-4">
          {!isAdmin ? (
            <Alert>
              <AlertTriangle data-icon="inline-start" />
              <AlertTitle>Admin only</AlertTitle>
              <AlertDescription>Admin permissions required to modify alert threshold parameters.</AlertDescription>
            </Alert>
          ) : (
            <ThresholdForm
              warningThreshold={warningThreshold}
              setWarningThreshold={setWarningThreshold}
              criticalThreshold={criticalThreshold}
              setCriticalThreshold={setCriticalThreshold}
              hysteresis={hysteresis}
              setHysteresis={setHysteresis}
              debounceSeconds={debounceSeconds}
              setDebounceSeconds={setDebounceSeconds}
              onSubmit={handleThresholdSubmit}
              pending={thresholdMutation.isPending}
              configError={configError}
              configSuccess={configSuccess}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default DeviceControls;

export const ControlsCompound = {
  AcControls,
  AtsControls,
  ThresholdForm,
};
