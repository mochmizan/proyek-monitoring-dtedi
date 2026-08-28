import { createFileRoute, useRouter } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Thermometer, Zap, Wind, HelpCircle, RefreshCw, Network, LayoutGrid, MapPin } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { cn } from "@/lib/utils";
import { queryKeys } from "@/lib/queryKeys";
import { fetchRooms, fetchRoomMap } from "@/lib/api";
import { POLL_MS } from "@/lib/constants";
import type { RoomMapMarker } from "@/types/api";
import { TopologyView } from "@/components/TopologyView";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Empty, EmptyMedia, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from "@/components/ui/empty";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const mapSearchSchema = z.object({
  view: z.enum(["floor-plan", "topology"]).catch("floor-plan").optional(),
});

export const Route = createFileRoute("/map")({
  validateSearch: (search) => mapSearchSchema.parse(search),
  component: MapPage,
});

function MapPage() {
  const router = useRouter();
  const { view } = Route.useSearch();
  const activeView = view ?? "floor-plan";

  const setView = (next: "floor-plan" | "topology") => {
    void router.navigate({ to: "/map", search: { view: next === "floor-plan" ? undefined : next } });
  };

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
  });

  const [selectedRoomId, setSelectedRoomId] = useState<string>("");
  const activeRoomId = selectedRoomId || rooms[0]?.id || "";

  const { data: roomMap, isFetching } = useQuery({
    queryKey: queryKeys.rooms.map(activeRoomId),
    queryFn: () => fetchRoomMap(activeRoomId),
    enabled: !!activeRoomId,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const getMarkerColor = (device: RoomMapMarker): string => {
    if (!device.is_active) return "bg-muted-foreground border-border";
    if (device.dev_type === "TS") {
      const temp = device.latest_reading?.temp;
      if (typeof temp === "number") {
        if (temp >= 35) return "bg-destructive border-destructive/50 shadow-destructive/50 animate-pulse";
        if (temp >= 30) return "bg-amber-500 border-amber-300 shadow-amber-500/50 animate-pulse";
      }
      return "bg-emerald-500 border-emerald-300 shadow-emerald-500/30";
    } else if (device.dev_type === "ATS") {
      const state = String(device.latest_reading?.state || "").toLowerCase();
      if (state.includes("genset")) return "bg-amber-500 border-amber-300";
      return "bg-emerald-500 border-emerald-300 shadow-emerald-500/30";
    }
    return "bg-emerald-500 border-emerald-300 shadow-emerald-500/30";
  };

  const getDeviceIcon = (type?: string | null) => {
    switch (type) {
      case "TS":
      case "Temperature":
        return <Thermometer className="size-3.5 text-primary-foreground" />;
      case "ATS":
        return <Zap className="size-3.5 text-primary-foreground" />;
      case "AC":
      case "ACC":
        return <Wind className="size-3.5 text-primary-foreground" />;
      default:
        return <HelpCircle className="size-3.5 text-primary-foreground" />;
    }
  };

  const devices = roomMap?.devices || [];

  return (
    <div className="flex flex-col gap-6 h-full">
      <Card className="overflow-hidden">
        <CardHeader className="flex flex-row items-start justify-between gap-4 gap-0">
          <div className="flex flex-col gap-1 min-w-0">
            <CardTitle className="font-serif text-xl font-semibold tracking-tight">Facility Floor Map</CardTitle>
            <CardDescription className="text-xs">Live spatial telemetry overlay across facility rooms</CardDescription>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {isFetching ? (
              <Badge variant="outline" className="gap-1.5 font-mono text-xs">
                <RefreshCw data-icon="inline-start" className="size-3 animate-spin text-primary" />
                Syncing Map
              </Badge>
            ) : (
              <Badge variant="outline" className="gap-1.5 font-mono text-xs">
                <span className="size-1.5 rounded-full bg-emerald-400 animate-pulse shrink-0" aria-hidden />
                Live
              </Badge>
            )}
            {rooms.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground font-medium">Room:</span>
                <Select value={activeRoomId} onValueChange={setSelectedRoomId}>
                  <SelectTrigger size="sm" className="w-[160px] font-mono text-xs">
                    <SelectValue placeholder="Select room" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {rooms.map((r) => (
                        <SelectItem key={r.id} value={r.id}>
                          {r.name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </CardHeader>
        <Separator />
      </Card>

      <Tabs value={activeView} onValueChange={(v) => setView(v as "floor-plan" | "topology")} className="flex flex-col gap-4">
        <TabsList className="w-fit">
          <TabsTrigger value="floor-plan" className="gap-1.5">
            <LayoutGrid data-icon="inline-start" />
            Floor Plan
          </TabsTrigger>
          <TabsTrigger value="topology" className="gap-1.5">
            <Network data-icon="inline-start" />
            Topology
          </TabsTrigger>
        </TabsList>

        <TabsContent value="floor-plan" className="mt-0">
          <Card className="overflow-hidden min-h-[500px] flex flex-col">
            <CardContent className="flex-1 flex flex-col items-center justify-center p-6 gap-4">
              {!activeRoomId || rooms.length === 0 ? (
                <Empty>
                  <EmptyMedia>
                    <HelpCircle className="size-8 text-muted-foreground" />
                  </EmptyMedia>
                  <EmptyHeader>
                    <EmptyTitle>No rooms found</EmptyTitle>
                    <EmptyDescription>Create rooms in Settings to view floor plans.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : isFetching && !roomMap ? (
                <div className="w-full flex flex-col gap-3 max-w-4xl">
                  <Skeleton className="h-[400px] w-full" />
                  <div className="flex gap-2 justify-center">
                    <Skeleton className="h-4 w-32" />
                  </div>
                </div>
              ) : !roomMap?.has_image || !roomMap.floor_plan_url ? (
                <Empty>
                  <EmptyMedia>
                    <MapPin className="size-8 text-muted-foreground" />
                  </EmptyMedia>
                  <EmptyHeader>
                    <EmptyTitle>No floor plan image</EmptyTitle>
                    <EmptyDescription>
                      No floor plan image uploaded for{" "}
                      <span className="font-semibold text-foreground">{roomMap?.room_name || "this room"}</span>.
                      Administrators can upload PNG/SVG diagrams in Settings → Rooms.
                    </EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    <Badge variant="outline" className="font-mono text-xs">
                      {roomMap?.room_name || activeRoomId}
                    </Badge>
                  </EmptyContent>
                </Empty>
              ) : (
                <div className="relative w-full max-w-4xl aspect-[16/10] bg-muted border rounded-lg overflow-hidden select-none">
                  <img src={roomMap.floor_plan_url} alt={`${roomMap.room_name} Floor Plan`} className="h-full w-full object-cover opacity-60" />

                  <TooltipProvider>
                    {devices.map((device) => {
                      const x = device.marker_x !== null && device.marker_x !== undefined ? device.marker_x : 50;
                      const y = device.marker_y !== null && device.marker_y !== undefined ? device.marker_y : 50;
                      return (
                        <div key={device.dev_id} style={{ left: `${x}%`, top: `${y}%` }} className="absolute -translate-x-1/2 -translate-y-1/2">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                type="button"
                                onClick={() => router.navigate({ to: "/device/$deviceId", params: { deviceId: device.dev_id } })}
                                className={cn(
                                  "size-8 rounded-full border-2 flex items-center justify-center cursor-pointer shadow-lg hover:scale-110 active:scale-95 transition-transform duration-150",
                                  getMarkerColor(device),
                                )}
                                aria-label={`${device.dev_name || device.dev_id} marker`}
                              >
                                {getDeviceIcon(device.dev_type)}
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="right" className="max-w-[14rem]">
                              <div className="flex flex-col gap-1">
                                <span className="font-semibold text-xs truncate">{device.dev_name || device.dev_id}</span>
                                <span className="font-mono text-[10px] uppercase tracking-wider opacity-80">
                                  {device.dev_type || "Device"} · {device.is_active ? "Active" : "Pending"}
                                </span>
                                <Separator className="my-1 bg-border/20" />
                                {device.latest_reading ? (
                                  <span className="text-xs font-semibold truncate">
                                    {device.dev_type === "TS" && typeof device.latest_reading.temp === "number" && (
                                      <span>
                                        {device.latest_reading.temp.toFixed(1)}°C / {String(device.latest_reading.humid ?? "")}%
                                      </span>
                                    )}
                                    {device.dev_type === "ATS" && <span>State: {String(device.latest_reading.state ?? "N/A")}</span>}
                                    {!["TS", "ATS"].includes(device.dev_type || "") && <span>Live telemetry</span>}
                                  </span>
                                ) : (
                                  <span className="text-xs opacity-70">Awaiting telemetry</span>
                                )}
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </div>
                      );
                    })}
                  </TooltipProvider>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="topology" className="mt-0">
          <TopologyView />
        </TabsContent>
      </Tabs>
    </div>
  );
}
