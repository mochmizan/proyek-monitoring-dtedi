import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
  Layers,
  AlertTriangle,
  HardDrive,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  HelpCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { z } from 'zod';
import { queryKeys } from '@/lib/queryKeys';
import { fetchRooms, fetchDevices, fetchAlerts } from '@/lib/api';
import { POLL_MS, STALE_MS } from '@/lib/constants';
import type { DeviceResponse } from '@/types/api';
import { RoomCard, RoomCardSkeleton } from '@/components/RoomCard';
import type { RoomCardStatus } from '@/components/RoomCard';
import { StatusDot } from '@/components/StatusDot';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table';
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyMedia } from '@/components/ui/empty';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

const dashboardSearchSchema = z.object({
  sortBy: z.enum(['name', 'type', 'room', 'devId', 'status', 'created']).optional().catch('name'),
  sortOrder: z.enum(['asc', 'desc']).optional().catch('asc'),
});

export const Route = createFileRoute('/')({
  validateSearch: (search) => dashboardSearchSchema.parse(search),
  component: DashboardPage,
});

function DashboardPage() {
  const navigate = useNavigate();
  const { sortBy, sortOrder } = Route.useSearch();

  const { data: rooms = [], status: roomsStatus } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: STALE_MS,
  });

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.list('all'),
    queryFn: () => fetchDevices('all'),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const { data: alertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ limit: 100 }),
    queryFn: () => fetchAlerts({ limit: 100 }),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });

  const unresolvedAlerts = (alertsData?.alerts || []).filter((a) => !a.resolved_at);
  const criticalCount = unresolvedAlerts.filter((a) => a.severity === 'critical').length;
  const warningCount = unresolvedAlerts.filter((a) => a.severity === 'warning').length;

  const getRoomStatus = (roomId: string): RoomCardStatus => {
    const roomAlerts = unresolvedAlerts.filter((a) => a.room_id === roomId);
    if (roomAlerts.some((a) => a.severity === 'critical')) return 'Critical';
    if (roomAlerts.some((a) => a.severity === 'warning')) return 'Warning';
    const roomDevs = devices.filter((d) => d.room_id === roomId);
    if (roomDevs.length > 0 && roomDevs.every((d) => !d.is_active)) return 'Offline';
    return 'Normal';
  };

  const renderSortHead = (
    label: string,
    sortKey: 'name' | 'type' | 'room' | 'devId' | 'status' | 'created',
  ): React.ReactNode => {
    const active = sortBy === sortKey;
    return (
      <TableHead
        aria-sort={active ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
        className="px-4"
      >
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 -ml-2 font-semibold uppercase tracking-wider text-xs active:scale-[0.97] transition-transform duration-[120ms]"
          onClick={() =>
            navigate({
              to: '.',
              search: (prev) => ({
                ...prev,
                sortBy: sortKey,
                sortOrder: active ? (prev.sortOrder === 'asc' ? 'desc' : 'asc') : 'asc',
              }),
            })
          }
        >
          <span className="truncate">{label}</span>
          {active ? (
            sortOrder === 'asc' ? (
              <ArrowUp className="size-3.5 shrink-0" data-icon="inline-end" />
            ) : (
              <ArrowDown className="size-3.5 shrink-0" data-icon="inline-end" />
            )
          ) : (
            <ArrowUpDown className="size-3.5 shrink-0 opacity-40" data-icon="inline-end" />
          )}
        </Button>
      </TableHead>
    );
  };

  const sortedDevices = [...devices].sort((a: DeviceResponse, b: DeviceResponse) => {
    let comparison = 0;
    switch (sortBy) {
      case 'name':
        comparison = (a.dev_name || a.dev_id).toLowerCase().localeCompare((b.dev_name || b.dev_id).toLowerCase());
        break;
      case 'type':
        comparison = (a.dev_type || '').toLowerCase().localeCompare((b.dev_type || '').toLowerCase());
        break;
      case 'room': {
        const nameA = (rooms.find((r) => r.id === a.room_id)?.name || 'Unpaired').toLowerCase();
        const nameB = (rooms.find((r) => r.id === b.room_id)?.name || 'Unpaired').toLowerCase();
        comparison = nameA.localeCompare(nameB);
        break;
      }
      case 'devId':
        comparison = a.dev_id.toLowerCase().localeCompare(b.dev_id.toLowerCase());
        break;
      case 'status': {
        const statA = a.is_active ? 'active' : 'pending';
        const statB = b.is_active ? 'active' : 'pending';
        comparison = statA.localeCompare(statB);
        break;
      }
      case 'created': {
        const timeA = a.created_at ? new Date(a.created_at).getTime() : 0;
        const timeB = b.created_at ? new Date(b.created_at).getTime() : 0;
        comparison = timeA - timeB;
        break;
      }
      default:
        comparison = 0;
    }
    return sortOrder === 'asc' ? comparison : -comparison;
  });

  const isInitialLoading = roomsStatus === 'pending';

  return (
    <div className="flex flex-col gap-8">
      {/* Overview stats — Card composition */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="card-stagger overflow-hidden hover:border-border transition-colors">
          <CardHeader className="flex flex-row items-center justify-between gap-2 gap-0 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Total Rooms
            </CardTitle>
            <Layers className="size-4 text-muted-foreground shrink-0" data-icon="inline-end" />
          </CardHeader>
          <Separator className="mx-6 w-auto" />
          <CardContent className="pt-4">
            {isInitialLoading ? (
              <Skeleton className="h-7 w-12" />
            ) : (
              <p className="text-2xl font-semibold tabular-nums font-mono truncate">{rooms.length}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1 truncate">Configured rooms</p>
          </CardContent>
        </Card>

        <Card className="card-stagger overflow-hidden hover:border-border transition-colors">
          <CardHeader className="flex flex-row items-center justify-between gap-2 gap-0 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Active Devices
            </CardTitle>
            <HardDrive className="size-4 text-muted-foreground shrink-0" data-icon="inline-end" />
          </CardHeader>
          <Separator className="mx-6 w-auto" />
          <CardContent className="pt-4">
            {isInitialLoading ? (
              <Skeleton className="h-7 w-12" />
            ) : (
              <p className="text-2xl font-semibold tabular-nums font-mono truncate">
                {devices.filter((d) => d.is_active).length}
              </p>
            )}
            <p className="text-xs text-muted-foreground mt-1 truncate">
              {devices.length === 0 ? 'No devices paired' : `${devices.filter((d) => d.is_active).length} of ${devices.length} active`}
            </p>
          </CardContent>
        </Card>

        <Card className="card-stagger overflow-hidden hover:border-border transition-colors">
          <CardHeader className="flex flex-row items-center justify-between gap-2 gap-0 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Warning Alerts
            </CardTitle>
            <AlertTriangle className="size-4 text-amber-500/70 shrink-0" data-icon="inline-end" />
          </CardHeader>
          <Separator className="mx-6 w-auto" />
          <CardContent className="pt-4">
            {isInitialLoading ? (
              <Skeleton className="h-7 w-12" />
            ) : (
              <p className="text-2xl font-semibold tabular-nums font-mono truncate text-amber-500">{warningCount}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1 truncate">Needs attention</p>
          </CardContent>
        </Card>

        <Card className="card-stagger overflow-hidden hover:border-border transition-colors">
          <CardHeader className="flex flex-row items-center justify-between gap-2 gap-0 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Critical Alerts
            </CardTitle>
            <AlertTriangle className="size-4 text-destructive/70 shrink-0" data-icon="inline-end" />
          </CardHeader>
          <Separator className="mx-6 w-auto" />
          <CardContent className="pt-4">
            {isInitialLoading ? (
              <Skeleton className="h-7 w-12" />
            ) : (
              <p className="text-2xl font-semibold tabular-nums font-mono truncate text-destructive">{criticalCount}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1 truncate">Immediate action</p>
          </CardContent>
        </Card>
      </div>

      {/* Rooms Section */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Rooms</h3>
          {!isInitialLoading && (
            <Badge variant="outline" className="gap-1.5 text-xs font-mono" role="status">
              <span className="size-1.5 rounded-full bg-primary animate-pulse shrink-0" aria-hidden="true" />
              Live
            </Badge>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {isInitialLoading &&
            Array.from({ length: 6 }, (_, i) => (
              <div key={`room-skeleton-${i}`} className="card-stagger" style={{ animationDelay: `${i * 40}ms` }}>
                <RoomCardSkeleton />
              </div>
            ))}
          {!isInitialLoading &&
            rooms.map((room, idx) => {
              const status = getRoomStatus(room.id);
              return (
                <div key={room.id} className="card-stagger" style={{ animationDelay: `${idx * 40}ms` }}>
                  <RoomCard room={room} status={status} />
                </div>
              );
            })}
          {!isInitialLoading && rooms.length === 0 && (
            <Card className="col-span-full overflow-hidden">
              <CardContent className="p-0">
                <Empty>
                  <EmptyMedia>
                    <Layers className="size-8 text-muted-foreground" />
                  </EmptyMedia>
                  <EmptyHeader>
                    <EmptyTitle>No rooms yet</EmptyTitle>
                    <EmptyDescription>Create a room in Settings to begin organizing devices.</EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* All Connected Nodes — shadcn Table */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">All Connected Nodes</h3>
        </div>

        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    {renderSortHead('Device Name', 'name')}
                    {renderSortHead('Type', 'type')}
                    {renderSortHead('Room', 'room')}
                    {renderSortHead('MAC / ID', 'devId')}
                    {renderSortHead('Status', 'status')}
                    <TableHead className="px-4 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Thresholds
                    </TableHead>
                    {renderSortHead('Created', 'created')}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isInitialLoading &&
                    Array.from({ length: 5 }, (_, i) => (
                      <TableRow key={`device-skeleton-${i}`}>
                        <TableCell className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Skeleton className="size-8 rounded-full shrink-0" />
                            <Skeleton className="h-4 w-24" />
                          </div>
                        </TableCell>
                        <TableCell className="px-4 py-3">
                          <Skeleton className="h-5 w-14 rounded-full" />
                        </TableCell>
                        <TableCell className="px-4 py-3">
                          <Skeleton className="h-4 w-20" />
                        </TableCell>
                        <TableCell className="px-4 py-3">
                          <Skeleton className="h-4 w-28" />
                        </TableCell>
                        <TableCell className="px-4 py-3">
                          <Skeleton className="h-5 w-16 rounded-full" />
                        </TableCell>
                        <TableCell className="px-4 py-3">
                          <Skeleton className="h-4 w-20" />
                        </TableCell>
                        <TableCell className="px-4 py-3">
                          <Skeleton className="h-4 w-24" />
                        </TableCell>
                      </TableRow>
                    ))}

                  {!isInitialLoading &&
                    sortedDevices.map((device) => {
                      const room = rooms.find((r) => r.id === device.room_id);
                      const isOnline = device.status === 'online';
                      const isPending = !device.is_active || device.status === 'pending';
                      const statusLabel = isPending ? 'Pending' : isOnline ? 'Online' : 'Offline';
                      const initials = (device.dev_name || device.dev_id).charAt(0).toUpperCase();
                      return (
                        <TableRow
                          key={device.dev_id}
                          onClick={() => navigate({ to: '/device/$deviceId', params: { deviceId: device.dev_id } })}
                          className={cn(
                            'hover:bg-muted/50 cursor-pointer transition-colors',
                            !device.is_active && 'opacity-60',
                          )}
                        >
                          <TableCell className="px-4 py-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <Avatar className="size-8 shrink-0">
                                <AvatarFallback className="text-xs font-mono">{initials}</AvatarFallback>
                              </Avatar>
                              <span className="font-semibold text-foreground truncate">{device.dev_name || device.dev_id}</span>
                            </div>
                          </TableCell>
                          <TableCell className="px-4 py-3">
                            <Badge variant="secondary" className="font-mono text-xs">
                              {device.dev_type || 'Generic'}
                            </Badge>
                          </TableCell>
                          <TableCell className="px-4 py-3">
                            {room ? (
                              <Badge variant="outline" className="truncate max-w-[12rem]">
                                {room.name}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground italic text-xs">Unassigned</span>
                            )}
                          </TableCell>
                          <TableCell className="px-4 py-3 font-mono text-xs text-muted-foreground truncate max-w-[10rem]">
                            {device.dev_id}
                          </TableCell>
                          <TableCell className="px-4 py-3">
                            <Badge
                              variant={isPending ? 'secondary' : isOnline ? 'default' : 'outline'}
                              className="gap-1.5 text-xs"
                            >
                              <StatusDot
                                tone={isPending ? 'amber' : isOnline ? 'emerald' : 'zinc'}
                                label={`Status: ${statusLabel}`}
                                pulse={isOnline}
                              />
                              {statusLabel}
                            </Badge>
                          </TableCell>
                          <TableCell className="px-4 py-3">
                            {device.threshold_config ? (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Badge variant="outline" className="font-mono text-xs cursor-help">
                                      W: {device.threshold_config.warning}°C / C: {device.threshold_config.critical}°C
                                    </Badge>
                                  </TooltipTrigger>
                                  <TooltipContent side="top">
                                    Warning {device.threshold_config.warning}°C / Critical {device.threshold_config.critical}°C
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            ) : (
                              <span className="text-muted-foreground text-xs">Default</span>
                            )}
                          </TableCell>
                          <TableCell className="px-4 py-3 text-xs text-muted-foreground tabular-nums">
                            {device.created_at ? new Date(device.created_at).toLocaleString() : '—'}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                </TableBody>
              </Table>
            </div>

            {!isInitialLoading && sortedDevices.length === 0 && (
              <>
                <Separator />
                <div className="px-6 py-10">
                  <Empty>
                    <EmptyMedia>
                      <HelpCircle className="size-8 text-muted-foreground" />
                    </EmptyMedia>
                    <EmptyHeader>
                      <EmptyTitle>No devices found</EmptyTitle>
                      <EmptyDescription>Pair a device in Settings to get started.</EmptyDescription>
                    </EmptyHeader>
                  </Empty>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
