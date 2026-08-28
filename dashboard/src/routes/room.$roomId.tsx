import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Wind,
  CheckCircle,
  AlertTriangle,
  Thermometer,
  Zap,
  Loader2,
  RefreshCw,
  HelpCircle,
  MapPin,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { z } from "zod";
import { queryKeys } from "@/lib/queryKeys";
import { fetchRooms, fetchRoomMap, fetchCurrentUser, sendDeviceCommand, fetchAlerts } from "@/lib/api";
import { POLL_MS } from "@/lib/constants";
import type { RoomMapMarker, ATSCommand } from "@/types/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia, EmptyContent } from "@/components/ui/empty";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { FieldGroup, Field, FieldLabel } from "@/components/ui/field";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const roomSearchSchema = z.object({
  range: z.enum(["6h", "24h", "7d", "30d"]).optional(),
});

export const Route = createFileRoute("/room/$roomId")({
  validateSearch: (search) => roomSearchSchema.parse(search),
  component: RoomDetailPage,
});

function RoomDetailPage() {
  const { roomId } = Route.useParams();
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchCurrentUser,
  });

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const { data: roomMap, isFetching: isFetchingMap } = useQuery({
    queryKey: queryKeys.rooms.map(roomId),
    queryFn: () => fetchRoomMap(roomId),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const { data: roomAlertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ room: roomId }),
    queryFn: () => fetchAlerts({ room: roomId }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const [selectedDeviceForCmd, setSelectedDeviceForCmd] = useState<RoomMapMarker | null>(null);
  const [commandPayload, setCommandPayload] = useState<ATSCommand>({});
  const [cmdError, setCmdError] = useState<string | null>(null);
  const [cmdSuccess, setCmdSuccess] = useState<string | null>(null);

  const commandMutation = useMutation({
    mutationFn: ({ devId, payload }: { devId: string; payload: ATSCommand }) => sendDeviceCommand(devId, payload),
    onSuccess: () => {
      setCmdSuccess("Command queued successfully for edge delivery");
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.map(roomId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => {
        setSelectedDeviceForCmd(null);
        setCmdSuccess(null);
        setCommandPayload({});
      }, 1500);
    },
    onError: (err: Error) => {
      setCmdError(err.message || "Failed to dispatch command");
    },
  });

  const room = rooms.find((r) => r.id === roomId);

  if (!room && !roomMap) {
    return (
      <div className="flex flex-col gap-6">
        <Button variant="ghost" size="sm" onClick={() => router.navigate({ to: "/" })} className="w-fit gap-1.5">
          <ArrowLeft data-icon="inline-start" />
          Back to Dashboard
        </Button>
        <Card>
          <CardContent className="py-10">
            <Empty className="border-0">
              <EmptyMedia>
                <HelpCircle className="size-8 text-muted-foreground" />
              </EmptyMedia>
              <EmptyHeader>
                <EmptyTitle>Room not found</EmptyTitle>
                <EmptyDescription>The requested room does not exist or has been removed.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          </CardContent>
        </Card>
      </div>
    );
  }

  const roomName = roomMap?.room_name || room?.name || "Room";
  const devices = roomMap?.devices || [];
  const activeAlerts = (roomAlertsData?.alerts || []).filter((a) => !a.resolved_at);

  const role = currentUser?.role || "viewer";
  const canControl = role === "admin" || role === "operator";
  const isAdmin = role === "admin";

  const handleOpenCommandModal = (device: RoomMapMarker) => {
    setSelectedDeviceForCmd(device);
    setCmdError(null);
    setCmdSuccess(null);
    setCommandPayload({});
  };

  const handleExecuteCommand = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDeviceForCmd) return;
    setCmdError(null);
    setCmdSuccess(null);
    commandMutation.mutate({
      devId: selectedDeviceForCmd.dev_id,
      payload: commandPayload,
    });
  };

  return (
    <div className="flex flex-col gap-8">
      {/* Top bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <Button
            variant="outline"
            size="icon"
            onClick={() => router.navigate({ to: "/" })}
            className="size-9 shrink-0"
            aria-label="Back to dashboard"
          >
            <ArrowLeft data-icon="inline-start" />
          </Button>
          <div className="flex flex-col gap-1 min-w-0">
            <h1 className="font-serif text-2xl font-semibold tracking-tight truncate">{roomName}</h1>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="font-mono text-xs">
                {devices.length} assigned {devices.length === 1 ? "device" : "devices"}
              </Badge>
              <Separator orientation="vertical" className="h-3" />
              <Badge variant={activeAlerts.length > 0 ? "destructive" : "secondary"} className="gap-1.5 text-xs">
                <span
                  className={cn(
                    "size-1.5 rounded-full shrink-0",
                    activeAlerts.length > 0 ? "bg-destructive-foreground animate-pulse" : "bg-emerald-400 animate-pulse",
                  )}
                  aria-hidden
                />
                {activeAlerts.length > 0 ? `${activeAlerts.length} Alert Active` : "Normal Status"}
              </Badge>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {isFetchingMap ? (
            <Badge variant="outline" className="gap-1.5 font-mono text-xs">
              <RefreshCw data-icon="inline-start" className="size-3 animate-spin text-primary" />
              Live 3s Polling
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5 font-mono text-xs">
              <span className="size-1.5 rounded-full bg-primary animate-pulse shrink-0" aria-hidden />
              Live
            </Badge>
          )}
        </div>
      </div>

      {/* Floor Plan Overview */}
      {roomMap && (
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-sm font-semibold tracking-tight">Room Floor Plan Layout</CardTitle>
            <CardDescription className="text-xs">Spatial placement of assigned devices — markers show live status</CardDescription>
          </CardHeader>
          <Separator />
          <CardContent className="pt-6">
            {isFetchingMap && !roomMap.has_image ? (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-[320px] w-full max-w-3xl mx-auto" />
                <div className="flex gap-2 justify-center">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-20" />
                </div>
              </div>
            ) : roomMap.has_image && roomMap.floor_plan_url ? (
              <div className="relative w-full max-w-3xl mx-auto aspect-[16/9] bg-muted border rounded-lg overflow-hidden select-none">
                <img src={roomMap.floor_plan_url} alt={`${roomName} Floor Plan`} className="h-full w-full object-cover opacity-60" />
                <TooltipProvider>
                  {devices.map((device) => {
                    const x = device.marker_x !== null && device.marker_x !== undefined ? device.marker_x : 50;
                    const y = device.marker_y !== null && device.marker_y !== undefined ? device.marker_y : 50;
                    const markerBg = !device.is_active
                      ? "bg-muted-foreground border-border"
                      : "bg-emerald-500 border-emerald-300 shadow-lg";
                    return (
                      <div key={device.dev_id} style={{ left: `${x}%`, top: `${y}%` }} className="absolute -translate-x-1/2 -translate-y-1/2">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Link
                              to="/device/$deviceId"
                              params={{ deviceId: device.dev_id }}
                              className={cn(
                                "size-8 rounded-full border-2 flex items-center justify-center cursor-pointer hover:scale-110 active:scale-95 transition-transform duration-150",
                                markerBg,
                              )}
                            >
                              {device.dev_type === "TS" && <Thermometer className="size-4 text-primary-foreground" />}
                              {device.dev_type === "ATS" && <Zap className="size-4 text-primary-foreground" />}
                              {(device.dev_type === "AC" || device.dev_type === "ACC") && <Wind className="size-4 text-primary-foreground" />}
                              {!["TS", "ATS", "AC", "ACC"].includes(device.dev_type || "") && (
                                <HelpCircle className="size-4 text-primary-foreground" />
                              )}
                            </Link>
                          </TooltipTrigger>
                          <TooltipContent side="right" className="max-w-[14rem]">
                            <div className="flex flex-col gap-1">
                              <span className="font-semibold text-xs truncate">{device.dev_name || device.dev_id}</span>
                              <span className="font-mono text-[10px] text-muted-foreground">{device.dev_type || "Device"}</span>
                              {device.latest_reading && (
                                <span className="text-xs font-semibold text-primary">
                                  {device.dev_type === "TS" && typeof device.latest_reading.temp === "number" && (
                                    <span>
                                      {device.latest_reading.temp.toFixed(1)}°C / {String(device.latest_reading.humid ?? "")}%
                                    </span>
                                  )}
                                  {device.dev_type === "ATS" && <span>State: {String(device.latest_reading.state ?? "N/A")}</span>}
                                </span>
                              )}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </div>
                    );
                  })}
                </TooltipProvider>
              </div>
            ) : (
              <Empty>
                <EmptyMedia>
                  <MapPin className="size-8 text-muted-foreground" />
                </EmptyMedia>
                <EmptyHeader>
                  <EmptyTitle>No floor plan uploaded</EmptyTitle>
                  <EmptyDescription>Upload a diagram in Settings to enable interactive spatial positioning.</EmptyDescription>
                </EmptyHeader>
                <EmptyContent>
                  <Badge variant="outline" className="font-mono text-xs">
                    {roomName}
                  </Badge>
                </EmptyContent>
              </Empty>
            )}
          </CardContent>
        </Card>
      )}

      {/* Devices in Room */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Assigned Room Devices</h3>
          <Badge variant="outline" className="font-mono text-xs gap-1.5">
            <span className="size-1.5 rounded-full bg-primary shrink-0" aria-hidden />
            {devices.length} total
          </Badge>
        </div>

        {devices.length === 0 ? (
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <Empty>
                <EmptyMedia>
                  <HelpCircle className="size-8 text-muted-foreground" />
                </EmptyMedia>
                <EmptyHeader>
                  <EmptyTitle>No devices assigned</EmptyTitle>
                  <EmptyDescription>No devices currently assigned to this room. You can pair devices in Settings.</EmptyDescription>
                </EmptyHeader>
              </Empty>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {devices.map((device) => {
              const reading = device.latest_reading;
              const isTS = device.dev_type === "TS";
              const isATS = device.dev_type === "ATS";
              const isAC = device.dev_type === "AC" || device.dev_type === "ACC";
              return (
                <Card
                  key={device.dev_id}
                  className="flex flex-col gap-0 py-0 overflow-hidden card-stagger hover:border-border/80 transition-colors"
                >
                  <CardHeader className="flex flex-row items-start justify-between gap-2 gap-0 pb-3 pt-5">
                    <div className="flex flex-col gap-1 min-w-0">
                      <CardTitle className="text-sm font-semibold truncate leading-none">{device.dev_name || device.dev_id}</CardTitle>
                      <CardDescription className="font-mono text-xs truncate">{device.dev_id}</CardDescription>
                    </div>
                    <Badge variant="secondary" className="font-mono text-xs shrink-0">
                      {device.dev_type || "Generic"}
                    </Badge>
                  </CardHeader>

                  <CardContent className="flex flex-col gap-3 pb-4">
                    <Separator />
                    <div className="flex flex-col gap-2 rounded-md border bg-muted/20 p-3 min-h-[5.5rem]">
                      {isTS && reading && typeof reading.temp === "number" ? (
                        <div className="flex items-center justify-between gap-4">
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Temperature</span>
                            <span className="text-xl font-bold tabular-nums font-mono truncate">
                              {typeof reading.temp === "number" ? `${reading.temp.toFixed(1)}°C` : "—"}
                            </span>
                          </div>
                          <Separator orientation="vertical" className="h-10" />
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Humidity</span>
                            <span className="text-xl font-bold tabular-nums font-mono text-primary truncate">
                              {typeof reading.humid === "number" ? `${reading.humid.toFixed(1)}%` : String(reading.humid ?? "—")}
                            </span>
                          </div>
                        </div>
                      ) : isATS && reading ? (
                        <div className="flex flex-col gap-1.5 text-xs">
                          <div className="flex justify-between gap-2">
                            <span className="text-muted-foreground truncate">State:</span>
                            <span className="font-bold font-mono uppercase truncate">{String(reading.state ?? "N/A")}</span>
                          </div>
                          <Separator />
                          <div className="flex justify-between gap-2">
                            <span className="text-muted-foreground">PLN Voltage:</span>
                            <span className="font-mono tabular-nums truncate">{String(reading.pln ?? "—")} V</span>
                          </div>
                          <div className="flex justify-between gap-2">
                            <span className="text-muted-foreground">Genset Voltage:</span>
                            <span className="font-mono tabular-nums truncate">{String(reading.genset ?? "—")} V</span>
                          </div>
                          <div className="flex justify-between gap-2">
                            <span className="text-muted-foreground">Battery (AKI):</span>
                            <span className="font-mono tabular-nums truncate">{String(reading.aki ?? "—")} V</span>
                          </div>
                          <div className="flex justify-between gap-2">
                            <span className="text-muted-foreground">Mode:</span>
                            <Badge
                              variant={reading.auto_mode ? "default" : "secondary"}
                              className="text-[10px] font-semibold uppercase"
                            >
                              {reading.auto_mode ? "AUTO" : "MANUAL"}
                            </Badge>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-center py-4">
                          <span className="text-xs text-muted-foreground text-center truncate">
                            {device.is_active ? "Awaiting telemetry packet…" : "Device pending pairing"}
                          </span>
                        </div>
                      )}
                    </div>
                  </CardContent>

                  <Separator />
                  <CardFooter className="flex items-center justify-between gap-2 py-3">
                    <Button variant="link" size="sm" asChild className="h-auto p-0 text-xs gap-1">
                      <Link to="/device/$deviceId" params={{ deviceId: device.dev_id }}>
                        View Device
                        <ArrowLeft data-icon="inline-end" className="rotate-180" />
                      </Link>
                    </Button>
                    {(isATS || isAC) && canControl && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleOpenCommandModal(device)}
                        className="h-7 gap-1.5 text-xs"
                      >
                        <Zap data-icon="inline-start" />
                        Command Control
                      </Button>
                    )}
                  </CardFooter>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Command Control Dialog */}
      <Dialog open={!!selectedDeviceForCmd} onOpenChange={(o) => !o && setSelectedDeviceForCmd(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Command Control: {selectedDeviceForCmd?.dev_name || selectedDeviceForCmd?.dev_id}</DialogTitle>
            <DialogDescription className="font-mono text-xs">
              {selectedDeviceForCmd?.dev_type} Node · queued via pending_commands
            </DialogDescription>
          </DialogHeader>

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

          <form onSubmit={handleExecuteCommand} className="flex flex-col gap-4">
            <FieldGroup>
              <Field>
                <FieldLabel>Operating Mode</FieldLabel>
                <ToggleGroup
                  type="single"
                  value={commandPayload.mode || ""}
                  onValueChange={(v) =>
                    setCommandPayload({ ...commandPayload, mode: (v as "auto" | "manual") || undefined })
                  }
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2"
                >
                  <ToggleGroupItem value="auto" className="flex-1 gap-1.5">
                    Auto
                  </ToggleGroupItem>
                  <ToggleGroupItem value="manual" className="flex-1 gap-1.5">
                    Manual
                  </ToggleGroupItem>
                </ToggleGroup>
              </Field>

              <Field>
                <FieldLabel>Genset Ignition (Manual Only)</FieldLabel>
                <ToggleGroup
                  type="single"
                  value={commandPayload.start_genset || ""}
                  onValueChange={(v) =>
                    setCommandPayload({ ...commandPayload, start_genset: (v as "on" | "off") || undefined })
                  }
                  variant="outline"
                  size="sm"
                  className="w-full justify-start gap-2"
                >
                  <ToggleGroupItem value="on" className="flex-1 gap-1.5">
                    Start ON
                  </ToggleGroupItem>
                  <ToggleGroupItem value="off" className="flex-1 gap-1.5">
                    Stop OFF
                  </ToggleGroupItem>
                </ToggleGroup>
              </Field>

              {isAdmin && (
                <Field>
                  <FieldLabel>Controller Reset (Admin Only)</FieldLabel>
                  <div className="flex items-center gap-2">
                    <Switch
                      id="reset-rst"
                      checked={commandPayload.reset === "rst"}
                      onCheckedChange={(c) => setCommandPayload({ ...commandPayload, reset: c ? "rst" : undefined })}
                    />
                    {/* eslint-disable-next-line jsx-a11y/label-has-associated-control */}
                    <label htmlFor="reset-rst" className="text-sm text-muted-foreground cursor-pointer">
                      Issue hardware reset command
                    </label>
                  </div>
                </Field>
              )}
            </FieldGroup>

            <Separator />

            <DialogFooter className="gap-2 sm:gap-2">
              <Button type="button" variant="outline" onClick={() => setSelectedDeviceForCmd(null)} disabled={commandMutation.isPending}>
                Cancel
              </Button>
              <Button type="submit" disabled={commandMutation.isPending} className="gap-1.5">
                {commandMutation.isPending ? (
                  <>
                    <Loader2 data-icon="inline-start" className="size-3.5 animate-spin" />
                    Sending…
                  </>
                ) : (
                  "Queue Command"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
