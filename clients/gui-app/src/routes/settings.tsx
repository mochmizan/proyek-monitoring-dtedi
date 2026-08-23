import { createFileRoute, redirect } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { cn } from '../lib/utils';
import { 
  Layers, 
  Cpu, 
  Sliders, 
  Plus, 
  Trash2, 
  Loader2,
  Upload,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  Edit2
} from 'lucide-react';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { 
  fetchCurrentUser, 
  fetchRooms, 
  createRoom, 
  updateRoom, 
  deleteRoom, 
  uploadFloorPlan,
  fetchDevices, 
  pairDevice, 
  unpairDevice, 
  updateThresholds 
} from '../lib/api';
import type { RoomResponse, DeviceResponse, DevicePairRequest, ThresholdUpdateRequest } from '../types/api';

const settingsSearchSchema = z.object({
  tab: z.enum(['rooms', 'devices', 'thresholds']).catch('rooms').optional(),
});

export const Route = createFileRoute('/settings')({
  beforeLoad: async ({ context }) => {
    try {
      const user = await context.queryClient.ensureQueryData({
        queryKey: queryKeys.auth.me(),
        queryFn: fetchCurrentUser,
      });
      if (!user || user.role !== 'admin') {
        throw redirect({ to: '/' });
      }
    } catch {
      throw redirect({ to: '/' });
    }
  },
  validateSearch: (search) => settingsSearchSchema.parse(search),
  component: SettingsPage,
});

function SettingsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'rooms' | 'devices' | 'thresholds'>('rooms');

  // Queries
  const { data: rooms = [], isFetching: isFetchingRooms } = useQuery({
    queryKey: queryKeys.rooms.list(),
    queryFn: fetchRooms,
  });

  const { data: pendingDevices = [], isFetching: isFetchingPending } = useQuery({
    queryKey: queryKeys.devices.pending(),
    queryFn: () => fetchDevices('pending'),
    refetchInterval: 5000,
  });

  const { data: activeDevices = [], isFetching: isFetchingActive } = useQuery({
    queryKey: queryKeys.devices.active(),
    queryFn: () => fetchDevices('active'),
    refetchInterval: 5000,
  });

  // Tab 1: Rooms States
  const [newRoomName, setNewRoomName] = useState('');
  const [newRoomHubId, setNewRoomHubId] = useState('');
  const [editingRoom, setEditingRoom] = useState<RoomResponse | null>(null);
  const [roomActionError, setRoomActionError] = useState<string | null>(null);
  const [roomActionSuccess, setRoomActionSuccess] = useState<string | null>(null);

  // Tab 2: Pairing States
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

  // Tab 3: Thresholds States
  const [threshDevId, setThreshDevId] = useState('');
  const [threshWarn, setThreshWarn] = useState('30');
  const [threshCrit, setThreshCrit] = useState('35');
  const [threshHyst, setThreshHyst] = useState('0.5');
  const [threshDebounce, setThreshDebounce] = useState('60');
  const [threshError, setThreshError] = useState<string | null>(null);
  const [threshSuccess, setThreshSuccess] = useState<string | null>(null);

  // Room Mutations
  const createRoomMutation = useMutation({
    mutationFn: createRoom,
    onSuccess: () => {
      setRoomActionSuccess('Room created successfully');
      setRoomActionError(null);
      setNewRoomName('');
      setNewRoomHubId('');
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });

  const updateRoomMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name: string; hub_id?: string } }) =>
      updateRoom(id, payload),
    onSuccess: () => {
      setRoomActionSuccess('Room updated successfully');
      setRoomActionError(null);
      setEditingRoom(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });

  const deleteRoomMutation = useMutation({
    mutationFn: deleteRoom,
    onSuccess: () => {
      setRoomActionSuccess('Room deleted successfully');
      setRoomActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });

  const uploadFloorPlanMutation = useMutation({
    mutationFn: ({ roomId, file }: { roomId: string; file: File }) =>
      uploadFloorPlan(roomId, file),
    onSuccess: () => {
      setRoomActionSuccess('Floor plan image uploaded successfully');
      setRoomActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });

  // Pairing Mutations
  const pairMutation = useMutation({
    mutationFn: ({ devId, payload }: { devId: string; payload: DevicePairRequest }) =>
      pairDevice(devId, payload),
    onSuccess: () => {
      setPairSuccess('Device paired and activated successfully');
      setPairError(null);
      setSelectedDeviceToPair(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      setTimeout(() => setPairSuccess(null), 3000);
    },
    onError: (err: Error) => setPairError(err.message),
  });

  const unpairMutation = useMutation({
    mutationFn: unpairDevice,
    onSuccess: () => {
      setPairSuccess('Device unpaired and deactivated successfully');
      setPairError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all });
      setTimeout(() => setPairSuccess(null), 3000);
    },
    onError: (err: Error) => setPairError(err.message),
  });

  // Thresholds Mutation
  const thresholdMutation = useMutation({
    mutationFn: ({ devId, payload }: { devId: string; payload: ThresholdUpdateRequest }) =>
      updateThresholds(devId, payload),
    onSuccess: () => {
      setThreshSuccess('Device threshold configuration updated');
      setThreshError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devices.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      setTimeout(() => setThreshSuccess(null), 3000);
    },
    onError: (err: Error) => setThreshError(err.message),
  });

  const handleCreateRoom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRoomName.trim()) return;
    createRoomMutation.mutate({
      name: newRoomName.trim(),
      hub_id: newRoomHubId.trim() || undefined,
    });
  };

  const handleUpdateRoom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingRoom || !editingRoom.name.trim()) return;
    updateRoomMutation.mutate({
      id: editingRoom.id,
      payload: {
        name: editingRoom.name.trim(),
        hub_id: editingRoom.hub_id || undefined,
      },
    });
  };

  const handleFileUpload = (roomId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files[0]) {
      uploadFloorPlanMutation.mutate({
        roomId,
        file: files[0],
      });
    }
  };

  const handleStartPair = (dev: DeviceResponse) => {
    setSelectedDeviceToPair(dev);
    setPairName(dev.dev_name || dev.dev_id);
    setPairRoomId(rooms[0]?.id || '');
    setPairMarkerX(dev.marker_x?.toString() || '50');
    setPairMarkerY(dev.marker_y?.toString() || '50');
    if (dev.threshold_config) {
      setPairWarn(dev.threshold_config.warning.toString());
      setPairCrit(dev.threshold_config.critical.toString());
      setPairHyst(dev.threshold_config.hysteresis.toString());
      setPairDebounce(dev.threshold_config.debounce_seconds.toString());
    }
    setPairError(null);
  };

  const handlePairSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDeviceToPair || !pairRoomId || !pairName.trim()) {
      setPairError('Device name and room assignment are required');
      return;
    }

    const warn = parseFloat(pairWarn);
    const crit = parseFloat(pairCrit);
    const hyst = parseFloat(pairHyst);
    const deb = parseInt(pairDebounce, 10);
    const mx = parseFloat(pairMarkerX);
    const my = parseFloat(pairMarkerY);

    pairMutation.mutate({
      devId: selectedDeviceToPair.dev_id,
      payload: {
        dev_name: pairName.trim(),
        room_id: pairRoomId,
        marker_x: isNaN(mx) ? 50 : mx,
        marker_y: isNaN(my) ? 50 : my,
        warning_threshold: isNaN(warn) ? undefined : warn,
        critical_threshold: isNaN(crit) ? undefined : crit,
        hysteresis: isNaN(hyst) ? 0.5 : hyst,
        debounce_seconds: isNaN(deb) ? 60 : deb,
      },
    });
  };

  const handleThresholdSelectDevice = (devId: string) => {
    setThreshDevId(devId);
    const target = activeDevices.find((d) => d.dev_id === devId);
    if (target?.threshold_config) {
      setThreshWarn(target.threshold_config.warning.toString());
      setThreshCrit(target.threshold_config.critical.toString());
      setThreshHyst(target.threshold_config.hysteresis.toString());
      setThreshDebounce(target.threshold_config.debounce_seconds.toString());
    }
    setThreshError(null);
  };

  const handleThresholdFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!threshDevId) {
      setThreshError('Please select a device to configure');
      return;
    }

    const warn = parseFloat(threshWarn);
    const crit = parseFloat(threshCrit);
    const hyst = parseFloat(threshHyst);
    const deb = parseInt(threshDebounce, 10);

    if (isNaN(warn) || isNaN(crit)) {
      setThreshError('Warning and Critical values must be numbers');
      return;
    }

    if (warn > crit) {
      setThreshError('Warning threshold cannot exceed Critical threshold');
      return;
    }

    thresholdMutation.mutate({
      devId: threshDevId,
      payload: {
        warning: warn,
        critical: crit,
        hysteresis: isNaN(hyst) ? 0.5 : hyst,
        debounce_seconds: isNaN(deb) ? 60 : deb,
      },
    });
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">System Administration</h1>
        <p className="text-xs text-zinc-500 mt-1">
          Manage facility rooms, self-discovered device pairing, and global telemetry threshold configuration.
        </p>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-zinc-800 gap-4 text-sm font-semibold">
        <button
          onClick={() => setActiveTab('rooms')}
          className={cn(
            "pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer",
            activeTab === 'rooms'
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          )}
        >
          <Layers className="h-4 w-4" />
          <span>Rooms Management</span>
        </button>

        <button
          onClick={() => setActiveTab('devices')}
          className={cn(
            "pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer",
            activeTab === 'devices'
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          )}
        >
          <Cpu className="h-4 w-4" />
          <span>Device Pairing</span>
          {pendingDevices.length > 0 && (
            <span className="bg-amber-500 text-black text-[10px] px-1.5 py-0.2 rounded-full font-bold">
              {pendingDevices.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('thresholds')}
          className={cn(
            "pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer",
            activeTab === 'thresholds'
              ? "border-indigo-500 text-indigo-400"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          )}
        >
          <Sliders className="h-4 w-4" />
          <span>Global Thresholds</span>
        </button>
      </div>

      {/* Tab 1: Rooms */}
      {activeTab === 'rooms' && (
        <div className="space-y-6">
          {roomActionError && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              <span>{roomActionError}</span>
            </div>
          )}

          {roomActionSuccess && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2">
              <CheckCircle className="h-4 w-4 flex-shrink-0" />
              <span>{roomActionSuccess}</span>
            </div>
          )}

          {/* Create Room Card */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-3 flex items-center gap-2">
              <Plus className="h-4 w-4 text-indigo-400" />
              <span>Create New Room</span>
            </h3>
            <form onSubmit={handleCreateRoom} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-[10px] font-semibold text-zinc-400 uppercase mb-1">Room Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Server Room B"
                  value={newRoomName}
                  onChange={(e) => setNewRoomName(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-[10px] font-semibold text-zinc-400 uppercase mb-1">Associated Hub ID</label>
                <input
                  type="text"
                  placeholder="e.g. hub-v5-01 (optional)"
                  value={newRoomHubId}
                  onChange={(e) => setNewRoomHubId(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex items-end">
                <button
                  type="submit"
                  disabled={createRoomMutation.isPending || !newRoomName.trim()}
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium cursor-pointer flex items-center justify-center gap-2"
                >
                  {createRoomMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create Room'}
                </button>
              </div>
            </form>
          </div>

          {/* Rooms Table */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Existing Facility Rooms</h3>
              {isFetchingRooms && <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800">
                  <tr>
                    <th className="px-6 py-3">Room Name</th>
                    <th className="px-6 py-3">Room ID</th>
                    <th className="px-6 py-3">Hub ID</th>
                    <th className="px-6 py-3">Devices</th>
                    <th className="px-6 py-3">Floor Plan</th>
                    <th className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {rooms.map((r) => (
                    <tr key={r.id} className="hover:bg-zinc-850/50">
                      <td className="px-6 py-4 font-semibold text-zinc-100">
                        {editingRoom?.id === r.id ? (
                          <input
                            type="text"
                            value={editingRoom.name}
                            onChange={(e) => setEditingRoom({ ...editingRoom, name: e.target.value })}
                            className="bg-zinc-950 border border-indigo-500 rounded px-2 py-1 text-xs text-zinc-100"
                          />
                        ) : (
                          r.name
                        )}
                      </td>
                      <td className="px-6 py-4 font-mono text-zinc-500">{r.id}</td>
                      <td className="px-6 py-4 font-mono text-zinc-400">
                        {editingRoom?.id === r.id ? (
                          <input
                            type="text"
                            value={editingRoom.hub_id || ''}
                            onChange={(e) => setEditingRoom({ ...editingRoom, hub_id: e.target.value })}
                            placeholder="hub_id"
                            className="bg-zinc-950 border border-indigo-500 rounded px-2 py-1 text-xs text-zinc-100"
                          />
                        ) : (
                          r.hub_id || '—'
                        )}
                      </td>
                      <td className="px-6 py-4 font-medium text-zinc-300">{r.device_count} assigned</td>
                      <td className="px-6 py-4">
                        <label className="inline-flex items-center gap-1.5 px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px] font-medium text-zinc-300 cursor-pointer">
                          <Upload className="h-3 w-3" />
                          <span>{r.floor_plan_image_path ? 'Replace Image' : 'Upload Plan'}</span>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => handleFileUpload(r.id, e)}
                            className="hidden"
                          />
                        </label>
                      </td>
                      <td className="px-6 py-4 text-right space-x-2">
                        {editingRoom?.id === r.id ? (
                          <>
                            <button
                              onClick={handleUpdateRoom}
                              disabled={updateRoomMutation.isPending}
                              className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[10px] font-medium cursor-pointer"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => setEditingRoom(null)}
                              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded text-[10px] font-medium cursor-pointer"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => setEditingRoom(r)}
                              className="p-1 text-zinc-400 hover:text-indigo-400 transition-colors"
                              title="Edit Room"
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => deleteRoomMutation.mutate(r.id)}
                              disabled={deleteRoomMutation.isPending || r.device_count > 0}
                              className="p-1 text-zinc-500 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                              title={r.device_count > 0 ? "Cannot delete room with assigned devices" : "Delete Room"}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                  {rooms.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-6 text-center text-zinc-500 text-xs">
                        No rooms configured yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Devices & Pairing */}
      {activeTab === 'devices' && (
        <div className="space-y-6">
          {pairError && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              <span>{pairError}</span>
            </div>
          )}

          {pairSuccess && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2">
              <CheckCircle className="h-4 w-4 flex-shrink-0" />
              <span>{pairSuccess}</span>
            </div>
          )}

          {/* Pending Discovery Section */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-amber-400" />
                  <span>Pending Self-Discovered Devices</span>
                </h3>
                <p className="text-xs text-zinc-500">Unpaired edge devices blocked by default until approved by an administrator.</p>
              </div>
              {isFetchingPending && <RefreshCw className="h-3 w-3 animate-spin text-amber-400" />}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {pendingDevices.map((dev) => (
                <div key={dev.dev_id} className="bg-zinc-950 border border-zinc-850 p-4 rounded-lg flex flex-col justify-between">
                  <div>
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-bold text-zinc-200 text-sm">{dev.dev_name || dev.dev_id}</h4>
                        <p className="font-mono text-xs text-zinc-500">{dev.dev_id}</p>
                      </div>
                      <span className="bg-zinc-850 text-amber-400 text-[10px] px-2 py-0.5 rounded font-mono font-bold">
                        {dev.dev_type || 'Unknown'}
                      </span>
                    </div>
                    <p className="text-[10px] text-zinc-500 mt-2">Hub: {dev.hub_id || 'Direct'}</p>
                  </div>
                  <div className="mt-4 pt-3 border-t border-zinc-850 flex justify-end">
                    <button
                      onClick={() => handleStartPair(dev)}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-semibold cursor-pointer"
                    >
                      Pair & Activate
                    </button>
                  </div>
                </div>
              ))}
              {pendingDevices.length === 0 && (
                <div className="col-span-full py-8 text-center text-zinc-500 text-xs">
                  No pending self-discovered devices at this time.
                </div>
              )}
            </div>
          </div>

          {/* Active Devices Table */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Active Paired Devices</h3>
              {isFetchingActive && <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800">
                  <tr>
                    <th className="px-6 py-3">Device Name</th>
                    <th className="px-6 py-3">Type</th>
                    <th className="px-6 py-3">MAC / ID</th>
                    <th className="px-6 py-3">Room</th>
                    <th className="px-6 py-3">Map Coordinate</th>
                    <th className="px-6 py-3">Thresholds</th>
                    <th className="px-6 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {activeDevices.map((d) => {
                    const r = rooms.find((room) => room.id === d.room_id);
                    return (
                      <tr key={d.dev_id} className="hover:bg-zinc-850/50">
                        <td className="px-6 py-4 font-semibold text-zinc-100">{d.dev_name || d.dev_id}</td>
                        <td className="px-6 py-4 font-mono text-zinc-400">{d.dev_type || '—'}</td>
                        <td className="px-6 py-4 font-mono text-zinc-500">{d.dev_id}</td>
                        <td className="px-6 py-4 font-medium text-zinc-300">{r?.name || 'Unassigned'}</td>
                        <td className="px-6 py-4 font-mono text-zinc-400">
                          {d.marker_x !== null && d.marker_y !== null ? `(${d.marker_x}%, ${d.marker_y}%)` : '—'}
                        </td>
                        <td className="px-6 py-4 font-mono text-xs text-zinc-400">
                          {d.threshold_config ? `W: ${d.threshold_config.warning}°C / C: ${d.threshold_config.critical}°C` : 'Default'}
                        </td>
                        <td className="px-6 py-4 text-right space-x-2">
                          <button
                            onClick={() => handleStartPair(d)}
                            className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded text-[10px] font-medium cursor-pointer"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => unpairMutation.mutate(d.dev_id)}
                            disabled={unpairMutation.isPending}
                            className="px-2 py-1 bg-red-950/30 hover:bg-red-950/60 text-red-400 border border-red-900/30 rounded text-[10px] font-medium cursor-pointer"
                          >
                            Unpair
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {activeDevices.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-6 py-6 text-center text-zinc-500 text-xs">
                        No active paired devices.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Global Thresholds */}
      {activeTab === 'thresholds' && (
        <div className="space-y-6">
          {threshError && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              <span>{threshError}</span>
            </div>
          )}

          {threshSuccess && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2">
              <CheckCircle className="h-4 w-4 flex-shrink-0" />
              <span>{threshSuccess}</span>
            </div>
          )}

          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-xl">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-4 flex items-center gap-2">
              <Sliders className="h-4 w-4 text-indigo-400" />
              <span>Configure Device Alert Parameters</span>
            </h3>

            <form onSubmit={handleThresholdFormSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Target Device *</label>
                <select
                  value={threshDevId}
                  onChange={(e) => handleThresholdSelectDevice(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="">Select an active device...</option>
                  {activeDevices.map((d) => (
                    <option key={d.dev_id} value={d.dev_id}>
                      {d.dev_name || d.dev_id} ({d.dev_type || 'Device'})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Warning Level (°C)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={threshWarn}
                    onChange={(e) => setThreshWarn(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Critical Level (°C)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={threshCrit}
                    onChange={(e) => setThreshCrit(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Hysteresis Offset (°C)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={threshHyst}
                    onChange={(e) => setThreshHyst(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Debounce Window (s)</label>
                  <input
                    type="number"
                    value={threshDebounce}
                    onChange={(e) => setThreshDebounce(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={thresholdMutation.isPending || !threshDevId}
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer flex items-center justify-center gap-2"
                >
                  {thresholdMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save Parameters'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Pairing Modal */}
      {selectedDeviceToPair && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="font-bold text-zinc-100">Pair & Configure Device</h3>
                <p className="text-xs text-zinc-500 font-mono">MAC: {selectedDeviceToPair.dev_id}</p>
              </div>
              <button 
                onClick={() => setSelectedDeviceToPair(null)}
                className="text-zinc-500 hover:text-zinc-300 text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handlePairSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Device Friendly Name *</label>
                <input
                  type="text"
                  value={pairName}
                  onChange={(e) => setPairName(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Room Assignment *</label>
                <select
                  value={pairRoomId}
                  onChange={(e) => setPairRoomId(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="">Select Room...</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Map Position X (%)</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={pairMarkerX}
                    onChange={(e) => setPairMarkerX(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Map Position Y (%)</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={pairMarkerY}
                    onChange={(e) => setPairMarkerY(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Warning Level (°C)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={pairWarn}
                    onChange={(e) => setPairWarn(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase mb-1">Critical Level (°C)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={pairCrit}
                    onChange={(e) => setPairCrit(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setSelectedDeviceToPair(null)}
                  className="px-4 py-2 border border-zinc-800 rounded hover:bg-zinc-800 text-zinc-300 text-xs font-medium cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={pairMutation.isPending}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-semibold cursor-pointer flex items-center gap-2"
                >
                  {pairMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Confirm Pairing'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
