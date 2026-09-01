import { useCallback, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from '@tanstack/react-router';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
} from '@xyflow/react';
import type { Edge, Node, NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Cpu, HelpCircle, Server, Snowflake, Thermometer, Zap } from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import { fetchDevices, fetchHubs, fetchRooms } from '../lib/api'
import { POLL_MS } from '../lib/constants';
import { StatusDot } from './StatusDot';
import type { StatusTone } from './StatusDot';
import { cn } from '../lib/utils';
import type { HubDeviceSummary, RoomResponse } from '../types/api';

const REDUCED_MOTION =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

type TopologyKind = 'vps' | 'hub' | 'device';
type TopologyStatus = 'online' | 'offline' | 'unknown';

interface TopologyNodeData extends Record<string, unknown> {
  kind: TopologyKind;
  name: string;
  sublabel: string;
  status: TopologyStatus;
  iconType?: string | null;
}

type TopologyNodeType = Node<TopologyNodeData, 'topology'>;

interface Descriptor {
  id: string;
  data: TopologyNodeData;
}

interface HubGroup {
  hubId: string;
  online: boolean;
  deviceIds: string[];
}

interface TopologyModel {
  descriptors: Descriptor[];
  hubGroups: HubGroup[];
  devicesByHub: Map<string, string[]>;
  offlineDevIds: Set<string>;
  signature: string;
}

const ROW_Y = [0, 190, 380];
const HUB_SPACING = 320;
const DEVICE_SPACING = 220;
const EDGE_BASE_STROKE = '#52525b';
const EDGE_HOVER_STROKE = '#6366f1';

const nodeTypes = { topology: TopologyNodeView };

const STATUS_TONES: Record<TopologyStatus, StatusTone> = {
  online: 'emerald',
  offline: 'red',
  unknown: 'zinc',
};

function DeviceTypeIcon({ devType }: { devType?: string | null }) {
  if (devType === 'AC') return <Snowflake className="h-3.5 w-3.5 shrink-0 text-sky-400" />;
  if (devType === 'TS') return <Thermometer className="h-3.5 w-3.5 shrink-0 text-amber-400" />;
  if (devType === 'ATS') return <Zap className="h-3.5 w-3.5 shrink-0 text-indigo-400" />;
  return <HelpCircle className="h-3.5 w-3.5 shrink-0 text-zinc-500" />;
}

export function TopologyNodeView({ data }: NodeProps<TopologyNodeType>) {
  return (
    <div
      className={cn(
        'w-44 bg-zinc-900 border rounded-lg px-3 py-2 text-xs shadow-lg',
        data.status === 'offline' ? 'border-red-900/70' : 'border-zinc-700'
      )}
    >
      <div className="flex items-center gap-2">
        {data.kind === 'vps' ? (
          <Server className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
        ) : data.kind === 'hub' ? (
          <Cpu className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
        ) : (
          <DeviceTypeIcon devType={data.iconType} />
        )}
        <span className="font-semibold text-zinc-100 truncate flex-1">{data.name}</span>
        <StatusDot
          tone={STATUS_TONES[data.status]}
          label={`${data.name} ${data.status}`}
          variant={!REDUCED_MOTION && data.status === 'online' ? 'live' : 'idle'}
        />
      </div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wider text-zinc-500 truncate tabular-nums">
        {data.sublabel}
      </div>
      <Handle
        type="target"
        position={Position.Top}
        isConnectable={false}
        className="h-1.5! w-1.5! bg-zinc-600! border-0!"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        className="h-1.5! w-1.5! bg-zinc-600! border-0!"
      />
    </div>
  );
}

function buildModel(
  hubs: Awaited<ReturnType<typeof fetchHubs>>,
  devices: Awaited<ReturnType<typeof fetchDevices>>,
  rooms: RoomResponse[]
): TopologyModel {
  const roomNameById = new Map(rooms.map((r) => [r.id, r.name]));
  const deviceMeta = new Map(devices.map((d) => [d.dev_id, d]));
  const offlineDevIds = new Set(
    devices.filter((d) => d.status === 'offline').map((d) => d.dev_id)
  );

  const roomLabel = (devId: string): string => {
    const meta = deviceMeta.get(devId);
    if (!meta?.room_id) return '';
    return roomNameById.get(meta.room_id) ?? meta.room_id;
  };

  const sortedHubs = [...hubs].sort((a, b) => a.hub_id.localeCompare(b.hub_id));

  const devicesByHub = new Map<string, string[]>();
  for (const hub of sortedHubs) {
    const ids = hub.devices.map((d) => d.dev_id);
    ids.sort(
      (a, b) =>
        roomLabel(a).localeCompare(roomLabel(b)) || a.localeCompare(b)
    );
    devicesByHub.set(hub.hub_id, ids);
  }

  const descriptors: Descriptor[] = [
    {
      id: 'vps',
      data: {
        kind: 'vps',
        name: 'HubGate VPS',
        sublabel: 'Cloud Gateway',
        status: 'online',
      },
    },
  ];
  const hubGroups: HubGroup[] = [];

  for (const hub of sortedHubs) {
    const online = hub.status === 'online';
    const deviceIds = devicesByHub.get(hub.hub_id) ?? [];
    descriptors.push({
      id: `hub:${hub.hub_id}`,
      data: {
        kind: 'hub',
        name: hub.hub_name,
        sublabel: `${hub.room || 'Unassigned'} · ${deviceIds.length}/${hub.device_count} devices`,
        status: online ? 'online' : 'offline',
      },
    });
    hubGroups.push({ hubId: hub.hub_id, online, deviceIds });

    const summaries = new Map<string, HubDeviceSummary>(
      hub.devices.map((d) => [d.dev_id, d])
    );
    for (const devId of deviceIds) {
      const summary = summaries.get(devId);
      const meta = deviceMeta.get(devId);
      const devType = summary?.dev_type ?? meta?.dev_type ?? null;
      const devOnline = !offlineDevIds.has(devId) && (meta ? meta.status !== 'offline' : false);
      descriptors.push({
        id: `dev:${devId}`,
        data: {
          kind: 'device',
          name: summary?.dev_name || devId,
          sublabel: `${devType ?? 'Device'} · ${roomLabel(devId) || 'No room'}`,
          status: meta || summary ? (devOnline ? 'online' : 'offline') : 'unknown',
          iconType: devType,
        },
      });
    }
  }

  const signature = descriptors.map((d) => d.id).sort().join('|');

  return { descriptors, hubGroups, devicesByHub, offlineDevIds, signature };
}

function computeLayout(
  hubGroups: HubGroup[],
  devicesByHub: Map<string, string[]>
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  const count = Math.max(hubGroups.length, 1);

  positions.set('vps', { x: ((count - 1) / 2) * HUB_SPACING, y: ROW_Y[0] });

  const hubX = new Map<string, number>();
  hubGroups.forEach((group, i) => {
    const x = i * HUB_SPACING;
    hubX.set(group.hubId, x);
    positions.set(`hub:${group.hubId}`, { x, y: ROW_Y[1] });
  });

  let nextFreeX = -DEVICE_SPACING / 2;
  for (const group of hubGroups) {
    const ids = devicesByHub.get(group.hubId) ?? [];
    const span = Math.max(0, ids.length - 1) * DEVICE_SPACING;
    let start = (hubX.get(group.hubId) ?? 0) - span / 2;
    if (start < nextFreeX) start = nextFreeX;
    ids.forEach((devId, j) => {
      positions.set(`dev:${devId}`, { x: start + j * DEVICE_SPACING, y: ROW_Y[2] });
    });
    nextFreeX = start + span + DEVICE_SPACING;
  }

  return positions;
}

export function TopologyView() {
  const router = useRouter();

  const { data: hubs = [] } = useQuery({
    queryKey: queryKeys.hubs.list(),
    queryFn: fetchHubs,
    refetchInterval: POLL_MS,
  });

  const { data: devices = [] } = useQuery({
    queryKey: queryKeys.devices.active(),
    queryFn: () => fetchDevices('active'),
    refetchInterval: POLL_MS,
  });

  const { data: rooms = [] } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
  });

  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const model = useMemo(
    () => buildModel(hubs, devices, rooms),
    [hubs, devices, rooms]
  );

  const positionsRef = useRef(new Map<string, { x: number; y: number }>());
  const signatureRef = useRef('');
  if (signatureRef.current !== model.signature) {
    signatureRef.current = model.signature;
    positionsRef.current = computeLayout(model.hubGroups, model.devicesByHub);
  }

  const nodes = useMemo<TopologyNodeType[]>(
    () =>
      model.descriptors.map((d) => ({
        id: d.id,
        type: 'topology' as const,
        position: positionsRef.current.get(d.id) ?? { x: 0, y: 0 },
        data: d.data,
      })),
    [model]
  );

  const edges = useMemo<Edge[]>(() => {
    const isConnected = (source: string, target: string): boolean =>
      hoveredNodeId !== null && (source === hoveredNodeId || target === hoveredNodeId);

    const out: Edge[] = [];
    for (const group of model.hubGroups) {
      const hubNodeId = `hub:${group.hubId}`;
      const hubDown = !group.online || group.deviceIds.some((id) => model.offlineDevIds.has(id));
      const edgeId = `edge:vps:${hubNodeId}`;
      const connected = isConnected('vps', hubNodeId);
      const dimmed = hoveredNodeId !== null && !connected;
      out.push({
        id: edgeId,
        source: 'vps',
        target: hubNodeId,
        animated: hubDown && !REDUCED_MOTION,
        style: {
          stroke: connected ? EDGE_HOVER_STROKE : EDGE_BASE_STROKE,
          strokeWidth: connected ? 2 : 1.5,
          opacity: dimmed ? 0.2 : 1,
        },
      });
      for (const devId of group.deviceIds) {
        const devNodeId = `dev:${devId}`;
        const devDown = !group.online || model.offlineDevIds.has(devId);
        const devEdgeId = `edge:${hubNodeId}:${devNodeId}`;
        const devConnected = isConnected(hubNodeId, devNodeId);
        const devDimmed = hoveredNodeId !== null && !devConnected;
        out.push({
          id: devEdgeId,
          source: hubNodeId,
          target: devNodeId,
          animated: devDown && !REDUCED_MOTION,
          style: {
            stroke: devConnected ? EDGE_HOVER_STROKE : EDGE_BASE_STROKE,
            strokeWidth: devConnected ? 2 : 1.5,
            opacity: devDimmed ? 0.2 : 1,
          },
        });
      }
    }
    return out;
  }, [model, hoveredNodeId]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: TopologyNodeType) => {
      if (node.data.kind === 'device') {
        void router.navigate({
          to: '/device/$deviceId',
          params: { deviceId: node.data.name || node.id.slice(4) },
        });
      } else if (node.data.kind === 'hub') {
        void router.navigate({ to: '/hubs' });
      }
    },
    [router]
  );

  if (model.hubGroups.length === 0) {
    return (
      <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg min-h-[500px] flex flex-col items-center justify-center text-zinc-500 gap-2">
        <HelpCircle className="h-8 w-8 text-zinc-600" />
        <p className="text-sm">No edge hubs registered yet.</p>
        <p className="text-xs text-zinc-600">
          Approved hubs and their devices will appear here automatically.
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg min-h-[500px] overflow-hidden"
      onMouseLeave={() => setHoveredNodeId(null)}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
        onNodeMouseLeave={() => setHoveredNodeId(null)}
        fitView
        fitViewOptions={{ padding: 0.25, maxZoom: 1 }}
        minZoom={0.3}
        maxZoom={1.75}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#27272a" />
        <Controls showInteractive={false} className="bg-zinc-900 border-zinc-800 [&>button]:bg-zinc-900 [&>button]:border-zinc-800 [&>button]:fill-zinc-400 [&>button:hover]:bg-zinc-800" />
        <MiniMap
          pannable
          zoomable
          nodeColor="#3f3f46"
          nodeStrokeWidth={0}
          maskColor="rgba(9, 9, 11, 0.75)"
          className="bg-zinc-950 border border-zinc-800 rounded"
        />
      </ReactFlow>
    </div>
  );
}
