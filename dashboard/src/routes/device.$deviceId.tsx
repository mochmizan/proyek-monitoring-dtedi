import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { cn } from "../lib/utils";
import { queryKeys } from "../lib/queryKeys";
import { fetchDevices, fetchRooms, fetchAlerts, fetchCurrentUser } from "../lib/api";
import { POLL_MS } from "../lib/constants";
import { HistoryChart } from "../components/device/HistoryChart";
import { DeviceControls } from "../components/device/Controls";
import { useDeviceHistory } from "../hooks/useDeviceHistory";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

const deviceSearchSchema = z.object({
  range: z.enum(["6h", "24h", "7d", "30d"]).catch("24h").optional(),
});

export const Route = createFileRoute("/device/$deviceId")({
  validateSearch: (search) => deviceSearchSchema.parse(search),
  component: DeviceDetailPage,
});

function DeviceDetailPage() {
  const { deviceId } = Route.useParams();
  const { range } = Route.useSearch();
  const router = useRouter();
  const [timeRange, setTimeRange] = useState<"6h" | "24h" | "7d" | "30d">(range ?? "24h");

  const { data: currentUser } = useQuery({ queryKey: queryKeys.auth.me(), queryFn: fetchCurrentUser });
  const { data: devices = [], isFetching: isFetchingDevices } = useQuery({
    queryKey: queryKeys.devices.list("all"),
    queryFn: () => fetchDevices("all"),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  const { data: deviceAlertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ device: deviceId }),
    queryFn: () => fetchAlerts({ device: deviceId }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  const { data: historyData } = useDeviceHistory(deviceId, timeRange);

  const device = devices.find((d) => d.dev_id === deviceId);
  const room = device ? rooms.find((r) => r.id === device.room_id) : null;
  const role = currentUser?.role || "viewer";

  if (!device) {
    if (isFetchingDevices) {
      return (
        <div className="flex flex-col gap-6">
          <div className="sticky top-0 z-10 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b px-1 -mx-1 py-3">
            <div className="flex items-center gap-4">
              <Skeleton className="size-9 rounded-md" />
              <div className="flex flex-col gap-2">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-3 w-64" />
              </div>
            </div>
          </div>
          <Skeleton className="h-[300px] w-full" />
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-6">
        <Button variant="ghost" size="sm" onClick={() => router.navigate({ to: "/" })} className="w-fit gap-2">
          <ArrowLeft data-icon="inline-start" />
          Back to Dashboard
        </Button>
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-sm text-muted-foreground">Device &apos;{deviceId}&apos; not found.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const alerts = deviceAlertsData?.alerts || [];
  const historyPoints = historyData?.points || [];

  const isOnline = device.status === "online";
  const isPending = !device.is_active || device.status === "pending";
  const badgeVariant = isPending ? "secondary" : isOnline ? "default" : "outline";
  const hasCoord = device.marker_x !== null && device.marker_y !== null;
  const coordLabel = hasCoord ? `${device.marker_x}%, ${device.marker_y}%` : "Unplaced";
  const hubLabel = device.hub_id || "Direct";
  const warnVal = device.threshold_config?.warning ?? null;
  const critVal = device.threshold_config?.critical ?? null;

  return (
    <div className="flex flex-col gap-6">
      {/* sticky header — Node Information folded inline */}
      <div className="sticky top-0 z-10 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b px-1 -mx-1 py-3">
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
            <div className="flex flex-col gap-2 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="font-serif text-2xl font-semibold tracking-tight truncate">{device.dev_name || device.dev_id}</h1>
                <Badge variant={badgeVariant} className="gap-1.5 font-mono text-xs shrink-0">
                  <span
                    className={cn("size-1.5 rounded-full shrink-0", isPending ? "bg-amber-400" : isOnline ? "bg-emerald-400 animate-pulse" : "bg-muted-foreground")}
                    aria-hidden
                  />
                  {isPending ? "Pending Approval" : isOnline ? "Online" : "Offline"}
                </Badge>
                <Badge variant="secondary" className="font-mono text-xs truncate">
                  {device.dev_type || "Generic"}
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="outline" className="font-mono truncate max-w-[180px]">
                  ID: {device.dev_id}
                </Badge>
                <Separator orientation="vertical" className="h-3" />
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className="truncate">
                        Hub: {hubLabel}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent side="top">Gateway hub — {hubLabel === "Direct" ? "direct MQTT" : hubLabel}</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <Separator orientation="vertical" className="h-3" />
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge variant="outline" className="truncate">
                        Room: {room?.name || "Unpaired"}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent side="top">Room assignment</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="font-mono text-xs text-muted-foreground cursor-default truncate">• {coordLabel}</span>
                    </TooltipTrigger>
                    <TooltipContent side="top">Map coordinate — drag in Settings → Floor Plan</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
                {warnVal !== null && (
                  <>
                    <Separator orientation="vertical" className="h-3" />
                    <Badge variant="outline" className="font-mono text-xs">
                      Warn {warnVal}°C
                    </Badge>
                  </>
                )}
                {critVal !== null && (
                  <>
                    <Separator orientation="vertical" className="h-3" />
                    <Badge variant="secondary" className="font-mono text-xs">
                      Crit {critVal}°C
                    </Badge>
                  </>
                )}
                <Separator orientation="vertical" className="h-3" />
                <span className="text-xs text-muted-foreground truncate">
                  Registered {device.created_at ? new Date(device.created_at).toLocaleDateString() : "—"}
                </span>
              </div>
            </div>
          </div>
          {isFetchingDevices && (
            <Badge variant="outline" className="gap-1.5 shrink-0 font-mono text-xs">
              <RefreshCw data-icon="inline-start" className="size-3 animate-spin text-primary" />
              Polling
            </Badge>
          )}
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
          <HistoryChart
            points={historyPoints}
            devType={device.dev_type || "TS"}
            timeRange={timeRange}
            setTimeRange={setTimeRange}
            warningThresholdVal={device.threshold_config ? device.threshold_config.warning : null}
            criticalThresholdVal={device.threshold_config ? device.threshold_config.critical : null}
          />

          <Card className="overflow-hidden">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm font-semibold tracking-tight">
                <ShieldAlert className="size-4 text-primary" data-icon="inline-start" />
                Device Alert Log
              </CardTitle>
              <CardDescription className="text-xs">{alerts.length} event{alerts.length === 1 ? "" : "s"} · live polling</CardDescription>
            </CardHeader>
            <Separator />
            <CardContent className="p-0">
              {alerts.length === 0 ? (
                <Empty className="border-0">
                  <EmptyMedia>
                    <ShieldAlert className="size-8 text-muted-foreground" data-icon="inline-start" />
                  </EmptyMedia>
                  <EmptyHeader>
                    <EmptyTitle>No alerts recorded</EmptyTitle>
                    <EmptyDescription>No alerts for this device in the current window.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="px-4">Severity</TableHead>
                      <TableHead className="px-4">Metric / Message</TableHead>
                      <TableHead className="px-4">Value</TableHead>
                      <TableHead className="px-4">Timestamp</TableHead>
                      <TableHead className="px-4">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {alerts.map((a) => (
                      <TableRow key={a.event_id} className="hover:bg-muted/50">
                        <TableCell className="px-4">
                          <Badge variant={a.severity === "critical" ? "destructive" : "secondary"} className="text-[10px] font-bold uppercase">
                            {a.severity}
                          </Badge>
                        </TableCell>
                        <TableCell className="px-4 font-medium truncate max-w-[200px]">{a.message || a.metric || "Threshold Breach"}</TableCell>
                        <TableCell className="px-4 font-mono text-xs">{a.value !== null && a.value !== undefined ? String(a.value) : "—"}</TableCell>
                        <TableCell className="px-4 text-xs text-muted-foreground truncate">{new Date(a.timestamp).toLocaleString()}</TableCell>
                        <TableCell className="px-4">
                          <Badge variant={a.resolved_at ? "outline" : "destructive"} className="text-[10px] font-semibold">
                            {a.resolved_at ? "Resolved" : "Active"}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
          <DeviceControls device={device} role={role} />
        </div>
      </div>
    </div>
  );
}
