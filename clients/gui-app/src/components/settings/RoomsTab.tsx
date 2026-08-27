import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, Loader2, Upload, CheckCircle, AlertTriangle, RefreshCw, Edit2 } from 'lucide-react';
import { queryKeys } from '../../lib/queryKeys';
import { fetchRooms, createRoom, updateRoom, deleteRoom, uploadFloorPlan } from '../../lib/api';
import type { RoomResponse } from '../../types/api';

export function RoomsTab() {
  const queryClient = useQueryClient();
  const { data: rooms = [], isFetching: isFetchingRooms } = useQuery({ queryKey: queryKeys.rooms.list(), queryFn: fetchRooms });
  const [newRoomName, setNewRoomName] = useState('');
  const [newRoomHubId, setNewRoomHubId] = useState('');
  const [editingRoom, setEditingRoom] = useState<RoomResponse | null>(null);
  const [roomActionError, setRoomActionError] = useState<string | null>(null);
  const [roomActionSuccess, setRoomActionSuccess] = useState<string | null>(null);

  const createRoomMutation = useMutation({
    mutationFn: createRoom,
    onSuccess: () => {
      setRoomActionSuccess('Room created successfully'); setRoomActionError(null); setNewRoomName(''); setNewRoomHubId('');
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all }); setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });
  const updateRoomMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: { name: string; hub_id?: string } }) => updateRoom(id, payload),
    onSuccess: () => {
      setRoomActionSuccess('Room updated successfully'); setRoomActionError(null); setEditingRoom(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all }); setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });
  const deleteRoomMutation = useMutation({
    mutationFn: deleteRoom,
    onSuccess: () => {
      setRoomActionSuccess('Room deleted successfully'); setRoomActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all }); setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });
  const uploadFloorPlanMutation = useMutation({
    mutationFn: ({ roomId, file }: { roomId: string; file: File }) => uploadFloorPlan(roomId, file),
    onSuccess: () => {
      setRoomActionSuccess('Floor plan image uploaded successfully'); setRoomActionError(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.rooms.all }); setTimeout(() => setRoomActionSuccess(null), 3000);
    },
    onError: (err: Error) => setRoomActionError(err.message),
  });

  const handleCreateRoom = (e: React.FormEvent) => { e.preventDefault(); if (!newRoomName.trim()) return; createRoomMutation.mutate({ name: newRoomName.trim(), hub_id: newRoomHubId.trim() || undefined }); };
  const handleUpdateRoom = (e: React.FormEvent) => { e.preventDefault(); if (!editingRoom || !editingRoom.name.trim()) return; updateRoomMutation.mutate({ id: editingRoom.id, payload: { name: editingRoom.name.trim(), hub_id: editingRoom.hub_id || undefined } }); };
  const handleFileUpload = (roomId: string, e: React.ChangeEvent<HTMLInputElement>) => { const files = e.target.files; if (files && files[0]) uploadFloorPlanMutation.mutate({ roomId, file: files[0] }); };

  return (
    <div className="space-y-6">
      {roomActionError && <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded flex items-center gap-2"><AlertTriangle className="h-4 w-4 flex-shrink-0" /><span>{roomActionError}</span></div>}
      {roomActionSuccess && <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs p-3 rounded flex items-center gap-2"><CheckCircle className="h-4 w-4 flex-shrink-0" /><span>{roomActionSuccess}</span></div>}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-3 flex items-center gap-2"><Plus className="h-4 w-4 text-indigo-400" /><span>Create New Room</span></h3>
        <form onSubmit={handleCreateRoom} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div><label className="block text-[10px] font-semibold text-zinc-400 uppercase mb-1">Room Name *</label><input type="text" placeholder="e.g. Server Room B" value={newRoomName} onChange={(e) => setNewRoomName(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div>
          <div><label className="block text-[10px] font-semibold text-zinc-400 uppercase mb-1">Associated Hub ID</label><input type="text" placeholder="e.g. hub-v5-01 (optional)" value={newRoomHubId} onChange={(e) => setNewRoomHubId(e.target.value)} className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-indigo-500" /></div>
          <div className="flex items-end"><button type="submit" disabled={createRoomMutation.isPending || !newRoomName.trim()} className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-medium cursor-pointer flex items-center justify-center gap-2">{createRoomMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Create Room'}</button></div>
        </form>
      </div>
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between"><h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Existing Facility Rooms</h3>{isFetchingRooms && <RefreshCw className="h-3 w-3 animate-spin text-indigo-400" />}</div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800"><tr><th className="px-6 py-3">Room Name</th><th className="px-6 py-3">Room ID</th><th className="px-6 py-3">Hub ID</th><th className="px-6 py-3">Devices</th><th className="px-6 py-3">Floor Plan</th><th className="px-6 py-3 text-right">Actions</th></tr></thead>
            <tbody className="divide-y divide-zinc-800/60">
              {rooms.map((r) => (
                <tr key={r.id} className="hover:bg-zinc-800/50">
                  <td className="px-6 py-4 font-semibold text-zinc-100">{editingRoom?.id === r.id ? <input type="text" value={editingRoom.name} onChange={(e) => setEditingRoom({ ...editingRoom, name: e.target.value })} className="bg-zinc-950 border border-indigo-500 rounded px-2 py-1 text-xs text-zinc-100" /> : r.name}</td>
                  <td className="px-6 py-4 font-mono text-zinc-500">{r.id}</td>
                  <td className="px-6 py-4 font-mono text-zinc-400">{editingRoom?.id === r.id ? <input type="text" value={editingRoom.hub_id || ''} onChange={(e) => setEditingRoom({ ...editingRoom, hub_id: e.target.value })} placeholder="hub_id" className="bg-zinc-950 border border-indigo-500 rounded px-2 py-1 text-xs text-zinc-100" /> : r.hub_id || '—'}</td>
                  <td className="px-6 py-4 font-medium text-zinc-300">{r.device_count} assigned</td>
                  <td className="px-6 py-4"><label className="inline-flex items-center gap-1.5 px-2 py-1 bg-zinc-800 hover:bg-zinc-700 rounded text-[10px] font-medium text-zinc-300 cursor-pointer"><Upload className="h-3 w-3" /><span>{r.floor_plan_image_path ? 'Replace Image' : 'Upload Plan'}</span><input type="file" accept="image/*" onChange={(e) => handleFileUpload(r.id, e)} className="hidden" /></label></td>
                  <td className="px-6 py-4 text-right space-x-2">
                    {editingRoom?.id === r.id ? (<><button onClick={handleUpdateRoom} disabled={updateRoomMutation.isPending} className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[10px] font-medium cursor-pointer">Save</button><button onClick={() => setEditingRoom(null)} className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded text-[10px] font-medium cursor-pointer">Cancel</button></>) : (<><button onClick={() => setEditingRoom(r)} className="p-1 text-zinc-400 hover:text-indigo-400 transition-colors" title="Edit Room"><Edit2 className="h-4 w-4" /></button><button onClick={() => deleteRoomMutation.mutate(r.id)} disabled={deleteRoomMutation.isPending || r.device_count > 0} className="p-1 text-zinc-500 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors" title={r.device_count > 0 ? "Cannot delete room with assigned devices" : "Delete Room"}><Trash2 className="h-4 w-4" /></button></>)}
                  </td>
                </tr>
              ))}
              {rooms.length === 0 && <tr><td colSpan={6} className="px-6 py-6 text-center text-zinc-500 text-xs">No rooms configured yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
export default RoomsTab;
