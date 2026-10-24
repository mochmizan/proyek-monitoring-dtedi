import { createFileRoute, redirect } from '@tanstack/react-router';
import { useState, useEffect, useCallback } from 'react';
import {
  Layers,
  Search,
  Plus,
  Users,
  RefreshCw,
  Building2,
  MapPin,
  Cpu,
  Home,
  X,
  Edit2,
  Trash2,
  UserPlus,
  ShieldCheck,
  SlidersHorizontal,
  Check,
  Link as LinkIcon,
  Unlink,
} from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import {
  fetchClusters,
  createCluster,
  updateCluster,
  deleteCluster,
  fetchClusterMembers,
  addClusterMember,
  updateClusterMemberRole,
  removeClusterMember,
  fetchClusterPermissions,
  updateClusterRolePermissions,
  fetchAdminUsers,
  fetchUnassignedClusterResources,
  createClusterRoom,
  updateClusterRoom,
  deleteClusterRoom,
  assignRoomToCluster,
  unassignRoomFromCluster,
  assignDeviceToCluster,
  unassignDeviceFromCluster,
  updateClusterDevice,
  ApiError,
} from '../lib/api';
import type {
  Cluster,
  Membership,
  UserResponse,
  UnassignedClusterResources,
} from '../types/api';

export const Route = createFileRoute('/clusters')({
  beforeLoad: ({ context }) => {
    const user =
      (context as { user?: UserResponse }).user ??
      context.queryClient.getQueryData<UserResponse>(queryKeys.auth.me());
    if (!user || user.role !== 'root') {
      throw redirect({ to: '/' });
    }
  },
  component: ClusterManagementPage,
});

const ALL_PERMISSIONS = [
  { key: 'view_dashboard', label: 'Lihat Dashboard Ringkasan', desc: 'Akses halaman utama dashboard' },
  { key: 'view_devices', label: 'Lihat Perangkat', desc: 'Melihat status dan daftar perangkat' },
  { key: 'view_monitoring', label: 'Monitoring Live Telemetri', desc: 'Melihat pembacaan sensor realtime' },
  { key: 'view_history', label: 'Riwayat & Grafik', desc: 'Akses riwayat telemetri jangka panjang' },
  { key: 'view_alerts', label: 'Riwayat Alarm / Notifikasi', desc: 'Melihat event alert dan insiden' },
  { key: 'control_devices', label: 'Kontrol Perangkat IoT', desc: 'Perintah manual genset/ATS/AC' },
  { key: 'pair_devices', label: 'Pairing Perangkat Baru', desc: 'Menghubungkan device ke ruangan/cluster' },
  { key: 'edit_devices', label: 'Edit Ambang Batas Sensor', desc: 'Konfigurasi threshold warning/critical' },
  { key: 'delete_devices', label: 'Unpair / Hapus Perangkat', desc: 'Mencabut perangkat dari cluster' },
  { key: 'manage_schedules', label: 'Kelola Jadwal Otomatisasi', desc: 'Buat/ubah/hapus cron schedule' },
  { key: 'manage_rooms', label: 'Kelola Ruangan & Denah', desc: 'Tambah/edit ruangan dan upload floor plan' },
  { key: 'manage_users', label: 'Kelola Pengguna Cluster', desc: 'Kelola akun user di level cluster' },
  { key: 'export_data', label: 'Ekspor Data & Laporan', desc: 'Mengunduh laporan telemetri dan log' },
];

export function ClusterManagementPage() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [search, setSearch] = useState('');

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingCluster, setEditingCluster] = useState<Cluster | null>(null);
  const [membersCluster, setMembersCluster] = useState<Cluster | null>(null);
  const [permissionsCluster, setPermissionsCluster] = useState<Cluster | null>(null);
  const [resourcesCluster, setResourcesCluster] = useState<Cluster | null>(null);

  // Form states
  const [formData, setFormData] = useState({ name: '', description: '', location: '' });
  const [formLoading, setFormLoading] = useState(false);

  // Member management state
  const [members, setMembers] = useState<Membership[]>([]);
  const [allUsers, setAllUsers] = useState<UserResponse[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedRole, setSelectedRole] = useState<'admin' | 'operator' | 'viewer'>('viewer');

  // Permissions state
  const [permMatrix, setPermMatrix] = useState<Record<string, Record<string, boolean>>>({
    admin: {},
    operator: {},
    viewer: {},
  });
  const [permsLoading, setPermsLoading] = useState(false);
  const [activePermRole, setActivePermRole] = useState<'admin' | 'operator' | 'viewer'>('admin');

  // Resources (Rooms & Devices) state
  const [activeResourceTab, setActiveResourceTab] = useState<'rooms' | 'devices'>('rooms');
  const [unassignedResources, setUnassignedResources] = useState<UnassignedClusterResources>({ rooms: [], devices: [] });
  const [resourcesLoading, setResourcesLoading] = useState(false);
  const [newRoomName, setNewRoomName] = useState('');
  const [selectedAssignRoomId, setSelectedAssignRoomId] = useState('');
  const [selectedAssignDevId, setSelectedAssignDevId] = useState('');
  const [selectedAssignDevRoomId, setSelectedAssignDevRoomId] = useState('');
  const [editingRoomId, setEditingRoomId] = useState<string | null>(null);
  const [editingRoomName, setEditingRoomName] = useState('');
  const [editingDevId, setEditingDevId] = useState<string | null>(null);
  const [editingDevName, setEditingDevName] = useState('');

  const loadClusters = useCallback(async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetchClusters({ page_size: 100 });
      setClusters(res.items);
      // If resources modal is currently open, refresh the selected cluster object
      setResourcesCluster((prev) => (prev ? res.items.find((c) => c.id === prev.id) || prev : null));
    } catch (err: unknown) {
      if (err instanceof ApiError) setErrorMsg(err.message);
      else setErrorMsg('Gagal memuat data cluster');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadClusters();
  }, [loadClusters]);

  // Load cluster members
  const openMembersModal = async (cluster: Cluster) => {
    setMembersCluster(cluster);
    setMembersLoading(true);
    try {
      const [membersRes, usersRes] = await Promise.all([
        fetchClusterMembers(cluster.id),
        fetchAdminUsers({ page_size: 100 }),
      ]);
      setMembers(membersRes);
      setAllUsers(usersRes.items);
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : 'Gagal memuat anggota cluster');
    } finally {
      setMembersLoading(false);
    }
  };

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!membersCluster || !selectedUserId) return;
    try {
      await addClusterMember({
        cluster_id: membersCluster.id,
        user_id: selectedUserId,
        role: selectedRole,
      });
      setSelectedUserId('');
      const updated = await fetchClusterMembers(membersCluster.id);
      setMembers(updated);
      loadClusters();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gagal menambahkan anggota');
    }
  };

  const handleUpdateMemberRole = async (membershipId: string, newRole: 'admin' | 'operator' | 'viewer') => {
    try {
      await updateClusterMemberRole(membershipId, { role: newRole });
      if (membersCluster) {
        const updated = await fetchClusterMembers(membersCluster.id);
        setMembers(updated);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gagal memperbarui peran anggota');
    }
  };

  const handleRemoveMember = async (membershipId: string) => {
    if (!confirm('Yakin ingin mencabut akses anggota ini dari cluster?')) return;
    try {
      await removeClusterMember(membershipId);
      if (membersCluster) {
        const updated = await fetchClusterMembers(membersCluster.id);
        setMembers(updated);
        loadClusters();
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gagal mencabut anggota');
    }
  };

  // Resources Modal (Rooms & Sensors)
  const openResourcesModal = async (cluster: Cluster) => {
    setResourcesCluster(cluster);
    setResourcesLoading(true);
    setEditingRoomId(null);
    setEditingDevId(null);
    try {
      const unassigned = await fetchUnassignedClusterResources();
      setUnassignedResources(unassigned);
    } catch (err) {
      console.error(err);
    } finally {
      setResourcesLoading(false);
    }
  };

  const reloadResourcesData = async (clusterId: string) => {
    setResourcesLoading(true);
    try {
      const [clustersRes, unassigned] = await Promise.all([
        fetchClusters({ page_size: 100 }),
        fetchUnassignedClusterResources(),
      ]);
      setClusters(clustersRes.items);
      const updated = clustersRes.items.find((c) => c.id === clusterId);
      if (updated) setResourcesCluster(updated);
      setUnassignedResources(unassigned);
    } catch (err) {
      console.error(err);
    } finally {
      setResourcesLoading(false);
    }
  };

  const handleCreateRoomInCluster = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resourcesCluster || !newRoomName.trim()) return;
    try {
      await createClusterRoom(resourcesCluster.id, { name: newRoomName.trim() });
      setNewRoomName('');
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal membuat ruangan');
    }
  };

  const handleAssignExistingRoom = async () => {
    if (!resourcesCluster || !selectedAssignRoomId) return;
    try {
      await assignRoomToCluster(resourcesCluster.id, selectedAssignRoomId);
      setSelectedAssignRoomId('');
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal menugaskan ruangan');
    }
  };

  const handleUnassignRoom = async (roomId: string, roomName: string) => {
    if (!resourcesCluster) return;
    if (!confirm(`Lepas ruangan "${roomName}" dari cluster "${resourcesCluster.name}"?`)) return;
    try {
      await unassignRoomFromCluster(resourcesCluster.id, roomId);
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal melepas ruangan');
    }
  };

  const handleSaveEditRoomName = async (roomId: string) => {
    if (!resourcesCluster || !editingRoomName.trim()) return;
    try {
      await updateClusterRoom(resourcesCluster.id, roomId, { name: editingRoomName.trim() });
      setEditingRoomId(null);
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal memperbarui nama ruangan');
    }
  };

  const handleDeleteRoomInCluster = async (roomId: string, roomName: string) => {
    if (!resourcesCluster) return;
    if (!confirm(`Hapus permanen ruangan "${roomName}"? Pastikan tidak ada sensor yang terhubung.`)) return;
    try {
      await deleteClusterRoom(resourcesCluster.id, roomId);
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal menghapus ruangan');
    }
  };

  const handleAssignDeviceToCluster = async () => {
    if (!resourcesCluster || !selectedAssignDevId) return;
    try {
      await assignDeviceToCluster(
        resourcesCluster.id,
        selectedAssignDevId,
        selectedAssignDevRoomId || null
      );
      setSelectedAssignDevId('');
      setSelectedAssignDevRoomId('');
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal menugaskan sensor ke cluster');
    }
  };

  const handleUnassignDevice = async (devId: string, devName: string) => {
    if (!resourcesCluster) return;
    if (!confirm(`Lepas sensor "${devName}" dari cluster "${resourcesCluster.name}"?`)) return;
    try {
      await unassignDeviceFromCluster(resourcesCluster.id, devId);
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal melepas sensor');
    }
  };

  const handleChangeDeviceRoom = async (devId: string, roomId: string) => {
    if (!resourcesCluster) return;
    try {
      await updateClusterDevice(resourcesCluster.id, devId, { room_id: roomId === 'none' ? null : roomId });
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal mengubah penugasan ruangan sensor');
    }
  };

  const handleSaveEditDevName = async (devId: string) => {
    if (!resourcesCluster || !editingDevName.trim()) return;
    try {
      await updateClusterDevice(resourcesCluster.id, devId, { dev_name: editingDevName.trim() });
      setEditingDevId(null);
      await reloadResourcesData(resourcesCluster.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal memperbarui nama sensor');
    }
  };

  // Permissions Modal
  const openPermissionsModal = async (cluster: Cluster) => {
    setPermissionsCluster(cluster);
    setPermsLoading(true);
    try {
      const data = await fetchClusterPermissions(cluster.id);
      setPermMatrix(data.permissions);
    } catch (err) {
      console.error(err);
    } finally {
      setPermsLoading(false);
    }
  };

  const handleTogglePermission = (role: string, permKey: string) => {
    setPermMatrix((prev) => ({
      ...prev,
      [role]: {
        ...prev[role],
        [permKey]: !prev[role]?.[permKey],
      },
    }));
  };

  const handleSavePermissions = async () => {
    if (!permissionsCluster) return;
    try {
      await updateClusterRolePermissions(
        permissionsCluster.id,
        activePermRole,
        permMatrix[activePermRole] || {}
      );
      alert(`Izin untuk peran ${activePermRole} berhasil diperbarui.`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gagal menyimpan izin');
    }
  };

  // Create / Update Cluster
  const handleSaveCluster = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      if (editingCluster) {
        await updateCluster(editingCluster.id, formData);
      } else {
        await createCluster(formData);
      }
      setShowCreateModal(false);
      setEditingCluster(null);
      setFormData({ name: '', description: '', location: '' });
      loadClusters();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gagal menyimpan cluster');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteCluster = async (cluster: Cluster) => {
    if (!confirm(`Hapus cluster "${cluster.name}"? Pastikan tidak ada ruangan atau perangkat yang masih terhubung.`)) {
      return;
    }
    try {
      await deleteCluster(cluster.id);
      loadClusters();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Gagal menghapus cluster');
    }
  };

  const filteredClusters = clusters.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      (c.location && c.location.toLowerCase().includes(search.toLowerCase())) ||
      (c.description && c.description.toLowerCase().includes(search.toLowerCase()))
  );

  const totalDevices = clusters.reduce((acc, c) => acc + (c.device_count || 0), 0);
  const totalRooms = clusters.reduce((acc, c) => acc + (c.room_count || 0), 0);
  const totalMembers = clusters.reduce((acc, c) => acc + (c.member_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-bold tracking-tight text-zinc-100 flex items-center gap-2">
              <Layers className="h-6 w-6 text-indigo-400" />
              Cluster Lokasi
            </h2>
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Root Super Admin
            </span>
          </div>
          <p className="text-sm text-zinc-400 mt-1">
            Kelola lokasi, pembagian akses pengguna, ruangan, dan sensor per cluster.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadClusters}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => {
              setEditingCluster(null);
              setFormData({ name: '', description: '', location: '' });
              setShowCreateModal(true);
            }}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition shadow-lg shadow-indigo-600/20"
          >
            <Plus className="h-4 w-4" />
            Tambah Cluster
          </button>
        </div>
      </div>

      {/* KPI Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-4">
          <div className="flex items-center gap-2 text-zinc-400 text-xs font-medium">
            <Building2 className="h-4 w-4 text-indigo-400" />
            Total Cluster
          </div>
          <p className="text-2xl font-bold text-zinc-100 mt-2">{clusters.length}</p>
        </div>
        <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-4">
          <div className="flex items-center gap-2 text-zinc-400 text-xs font-medium">
            <Cpu className="h-4 w-4 text-emerald-400" />
            Perangkat Terhubung
          </div>
          <p className="text-2xl font-bold text-zinc-100 mt-2">{totalDevices}</p>
        </div>
        <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-4">
          <div className="flex items-center gap-2 text-zinc-400 text-xs font-medium">
            <Home className="h-4 w-4 text-amber-400" />
            Total Ruangan
          </div>
          <p className="text-2xl font-bold text-zinc-100 mt-2">{totalRooms}</p>
        </div>
        <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-4">
          <div className="flex items-center gap-2 text-zinc-400 text-xs font-medium">
            <Users className="h-4 w-4 text-sky-400" />
            Pengguna Diberikan Akses
          </div>
          <p className="text-2xl font-bold text-zinc-100 mt-2">{totalMembers}</p>
        </div>
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Cari cluster berdasarkan nama atau lokasi..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-4 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {errorMsg}
        </div>
      )}

      {/* Cluster Grid */}
      {loading ? (
        <div className="flex justify-center p-12">
          <RefreshCw className="h-8 w-8 text-indigo-400 animate-spin" />
        </div>
      ) : filteredClusters.length === 0 ? (
        <div className="p-12 text-center rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-500">
          <Layers className="h-12 w-12 mx-auto text-zinc-600 mb-3" />
          <p className="text-base font-medium text-zinc-300">Belum ada Cluster</p>
          <p className="text-xs text-zinc-500 mt-1">
            Buat cluster lokasi pertama Anda untuk mulai mengelompokkan perangkat dan pengguna.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredClusters.map((cluster) => (
            <div
              key={cluster.id}
              className="rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition flex flex-col justify-between p-5 space-y-4 shadow-sm"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="font-bold text-lg text-zinc-100 truncate">{cluster.name}</h3>
                    {cluster.location && (
                      <p className="text-xs text-zinc-400 flex items-center gap-1 mt-0.5">
                        <MapPin className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0" />
                        <span className="truncate">{cluster.location}</span>
                      </p>
                    )}
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-semibold ${
                      cluster.is_active
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'bg-zinc-800 text-zinc-500'
                    }`}
                  >
                    {cluster.is_active ? 'Aktif' : 'Non-Aktif'}
                  </span>
                </div>

                {cluster.description && (
                  <p className="text-xs text-zinc-400 line-clamp-2">
                    {cluster.description}
                  </p>
                )}

                {/* Counters */}
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-800/80">
                  <div className="text-center p-2 rounded bg-zinc-950/50">
                    <span className="text-[10px] uppercase font-semibold text-zinc-500 block">Sensor</span>
                    <span className="text-sm font-bold text-zinc-200">{cluster.device_count || 0}</span>
                  </div>
                  <div className="text-center p-2 rounded bg-zinc-950/50">
                    <span className="text-[10px] uppercase font-semibold text-zinc-500 block">Ruangan</span>
                    <span className="text-sm font-bold text-zinc-200">{cluster.room_count || 0}</span>
                  </div>
                  <div className="text-center p-2 rounded bg-zinc-950/50">
                    <span className="text-[10px] uppercase font-semibold text-zinc-500 block">Anggota</span>
                    <span className="text-sm font-bold text-indigo-400">{cluster.member_count || 0}</span>
                  </div>
                </div>

                {/* Daftar Ruangan di Cluster */}
                <div className="pt-2 border-t border-zinc-800/60 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-medium text-zinc-400">
                    <span className="flex items-center gap-1">
                      <Home className="h-3.5 w-3.5 text-amber-400" />
                      Ruangan ({cluster.rooms?.length || 0})
                    </span>
                  </div>
                  {cluster.rooms && cluster.rooms.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto pr-1">
                      {cluster.rooms.map((r) => (
                        <span
                          key={r.id}
                          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md bg-zinc-950 text-zinc-300 border border-zinc-800"
                        >
                          <Home className="h-2.5 w-2.5 text-amber-400/80" />
                          <span>{r.name}</span>
                          {r.device_count !== undefined && (
                            <span className="text-[9px] text-zinc-500 font-mono">({r.device_count})</span>
                          )}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[11px] text-zinc-600 italic">Belum ada ruangan</p>
                  )}
                </div>

                {/* Daftar Sensor / Perangkat di Cluster */}
                <div className="pt-2 border-t border-zinc-800/60 space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-medium text-zinc-400">
                    <span className="flex items-center gap-1">
                      <Cpu className="h-3.5 w-3.5 text-emerald-400" />
                      Sensor / Perangkat ({cluster.devices?.length || 0})
                    </span>
                  </div>
                  {cluster.devices && cluster.devices.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto pr-1">
                      {cluster.devices.map((d) => (
                        <span
                          key={d.dev_id}
                          className="inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-md bg-zinc-950 text-zinc-300 border border-zinc-800"
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              d.is_active ? 'bg-emerald-400' : 'bg-zinc-600'
                            }`}
                          />
                          <span className="font-medium text-zinc-200">{d.dev_name || d.dev_id}</span>
                          <span className="text-[9px] text-indigo-400 font-mono uppercase bg-indigo-950/50 px-1 rounded border border-indigo-500/20">
                            {d.dev_type}
                          </span>
                          {d.room_name && (
                            <span className="text-[9px] text-zinc-500">[{d.room_name}]</span>
                          )}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[11px] text-zinc-600 italic">Belum ada sensor</p>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="pt-3 border-t border-zinc-800 flex items-center justify-between gap-1">
                <button
                  onClick={() => openResourcesModal(cluster)}
                  className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-amber-950/40 hover:bg-amber-900/50 text-amber-300 text-xs font-medium border border-amber-500/20 transition"
                  title="Kelola Ruangan & Sensor Cluster"
                >
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  Ruang & Sensor
                </button>
                <button
                  onClick={() => openMembersModal(cluster)}
                  className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-indigo-950/40 hover:bg-indigo-900/50 text-indigo-300 text-xs font-medium border border-indigo-500/20 transition"
                  title="Kelola Pengguna Cluster"
                >
                  <Users className="h-3.5 w-3.5" />
                  Anggota
                </button>
                <button
                  onClick={() => openPermissionsModal(cluster)}
                  className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition"
                  title="Matriks Izin Peran"
                >
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                  Izin
                </button>
                <button
                  onClick={() => {
                    setEditingCluster(cluster);
                    setFormData({
                      name: cluster.name,
                      description: cluster.description || '',
                      location: cluster.location || '',
                    });
                    setShowCreateModal(true);
                  }}
                  className="p-1.5 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 rounded-lg transition"
                  title="Edit Cluster"
                >
                  <Edit2 className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => handleDeleteCluster(cluster)}
                  className="p-1.5 hover:bg-zinc-800 text-red-400 hover:text-red-300 rounded-lg transition"
                  title="Hapus Cluster"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create / Edit Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-md shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
              <Layers className="h-5 w-5 text-indigo-400" />
              {editingCluster ? 'Edit Cluster Lokasi' : 'Tambah Cluster Baru'}
            </h3>
            <form onSubmit={handleSaveCluster} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Nama Cluster</label>
                <input
                  type="text"
                  required
                  placeholder="Contoh: Gedung DTEDI Timur, Kampus Pusat"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Lokasi Fisik (Opsional)</label>
                <input
                  type="text"
                  placeholder="Contoh: Jl. Grafika No. 2, Yogyakarta"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Deskripsi (Opsional)</label>
                <textarea
                  rows={3}
                  placeholder="Keterangan singkat mengenai fasilitas dan lingkup pemantauan..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm text-zinc-300 transition"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={formLoading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium text-white transition flex items-center gap-1.5"
                >
                  {formLoading && <RefreshCw className="h-4 w-4 animate-spin" />}
                  Simpan Cluster
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Ruangan & Sensor Management Modal */}
      {resourcesCluster && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-3xl shadow-2xl space-y-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                  <SlidersHorizontal className="h-5 w-5 text-amber-400" />
                  Pengaturan Ruangan & Sensor: {resourcesCluster.name}
                </h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Tambah, edit, atau kurangi ruangan serta atur penugasan sensor pada cluster ini.
                </p>
              </div>
              <button
                onClick={() => setResourcesCluster(null)}
                className="p-1 text-zinc-400 hover:text-zinc-200 rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Tab Selector */}
            <div className="flex border-b border-zinc-800 gap-2">
              <button
                onClick={() => setActiveResourceTab('rooms')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition flex items-center gap-1.5 ${
                  activeResourceTab === 'rooms'
                    ? 'border-amber-500 text-amber-400 font-bold'
                    : 'border-transparent text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <Home className="h-4 w-4" />
                Kelola Ruangan ({resourcesCluster.rooms?.length || 0})
              </button>
              <button
                onClick={() => setActiveResourceTab('devices')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition flex items-center gap-1.5 ${
                  activeResourceTab === 'devices'
                    ? 'border-emerald-500 text-emerald-400 font-bold'
                    : 'border-transparent text-zinc-400 hover:text-zinc-200'
                }`}
              >
                <Cpu className="h-4 w-4" />
                Kelola Sensor / Perangkat ({resourcesCluster.devices?.length || 0})
              </button>
            </div>

            {/* TAB CONTENT: RUANGAN */}
            {activeResourceTab === 'rooms' && (
              <div className="space-y-4 flex-1 overflow-y-auto pr-1">
                {/* 1. Tambah Ruangan Baru */}
                <div className="bg-zinc-950/70 p-3.5 rounded-lg border border-zinc-800 space-y-3">
                  <h4 className="text-xs font-semibold uppercase text-zinc-400 flex items-center gap-1.5">
                    <Plus className="h-4 w-4 text-amber-400" />
                    Tambah Ruangan ke Cluster
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {/* Buat Ruangan Baru */}
                    <form onSubmit={handleCreateRoomInCluster} className="flex gap-2 items-center">
                      <input
                        type="text"
                        placeholder="Nama Ruangan Baru..."
                        value={newRoomName}
                        onChange={(e) => setNewRoomName(e.target.value)}
                        className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-amber-500"
                      />
                      <button
                        type="submit"
                        disabled={!newRoomName.trim()}
                        className="px-3 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition whitespace-nowrap"
                      >
                        Buat Baru
                      </button>
                    </form>

                    {/* Tugaskan Ruangan yang Belum Ada Cluster */}
                    <div className="flex gap-2 items-center">
                      <select
                        value={selectedAssignRoomId}
                        onChange={(e) => setSelectedAssignRoomId(e.target.value)}
                        className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-amber-500"
                      >
                        <option value="">-- Pilih Ruangan Tanpa Cluster --</option>
                        {unassignedResources.rooms.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={handleAssignExistingRoom}
                        disabled={!selectedAssignRoomId}
                        className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 rounded-lg text-xs font-medium transition whitespace-nowrap flex items-center gap-1"
                      >
                        <LinkIcon className="h-3 w-3" />
                        Tugaskan
                      </button>
                    </div>
                  </div>
                </div>

                {/* 2. Daftar Ruangan di Cluster */}
                <div className="border border-zinc-800 rounded-lg overflow-hidden">
                  <div className="bg-zinc-950/80 px-4 py-2 border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase">
                    Daftar Ruangan Terdaftar
                  </div>
                  {resourcesLoading ? (
                    <div className="flex justify-center p-8">
                      <RefreshCw className="h-6 w-6 text-amber-400 animate-spin" />
                    </div>
                  ) : !resourcesCluster.rooms || resourcesCluster.rooms.length === 0 ? (
                    <div className="p-8 text-center text-zinc-500 text-sm">
                      Belum ada ruangan di cluster ini. Silakan tambahkan ruangan baru atau tugaskan ruangan yang ada di atas.
                    </div>
                  ) : (
                    <table className="w-full text-left text-sm text-zinc-300">
                      <thead className="bg-zinc-950/40 text-zinc-500 text-xs uppercase border-b border-zinc-800">
                        <tr>
                          <th className="py-2.5 px-4">Nama Ruangan</th>
                          <th className="py-2.5 px-4">Jumlah Sensor</th>
                          <th className="py-2.5 px-4 text-right">Aksi</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {resourcesCluster.rooms.map((r) => (
                          <tr key={r.id} className="hover:bg-zinc-800/40">
                            <td className="py-2.5 px-4">
                              {editingRoomId === r.id ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    type="text"
                                    value={editingRoomName}
                                    onChange={(e) => setEditingRoomName(e.target.value)}
                                    className="bg-zinc-950 border border-amber-500/60 rounded px-2 py-1 text-xs text-zinc-100"
                                    autoFocus
                                  />
                                  <button
                                    onClick={() => handleSaveEditRoomName(r.id)}
                                    className="p-1 text-emerald-400 hover:bg-zinc-800 rounded"
                                    title="Simpan Nama"
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    onClick={() => setEditingRoomId(null)}
                                    className="p-1 text-zinc-500 hover:bg-zinc-800 rounded"
                                    title="Batal"
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              ) : (
                                <div className="flex items-center gap-2">
                                  <Home className="h-4 w-4 text-amber-400/80 flex-shrink-0" />
                                  <span className="font-medium text-zinc-100">{r.name}</span>
                                  <button
                                    onClick={() => {
                                      setEditingRoomId(r.id);
                                      setEditingRoomName(r.name);
                                    }}
                                    className="text-zinc-500 hover:text-zinc-300 p-0.5"
                                    title="Edit Nama Ruangan"
                                  >
                                    <Edit2 className="h-3 w-3" />
                                  </button>
                                </div>
                              )}
                            </td>
                            <td className="py-2.5 px-4 text-xs font-mono text-zinc-400">
                              {r.device_count ?? 0} sensor
                            </td>
                            <td className="py-2.5 px-4 text-right space-x-2">
                              <button
                                onClick={() => handleUnassignRoom(r.id, r.name)}
                                className="inline-flex items-center gap-1 text-amber-400 hover:text-amber-300 text-xs px-2 py-1 rounded hover:bg-zinc-800 transition"
                                title="Lepas ruangan dari cluster ini (ruangan tetap ada tapi unassigned)"
                              >
                                <Unlink className="h-3 w-3" />
                                Lepas
                              </button>
                              <button
                                onClick={() => handleDeleteRoomInCluster(r.id, r.name)}
                                disabled={(r.device_count ?? 0) > 0}
                                className="inline-flex items-center gap-1 text-red-400 hover:text-red-300 disabled:opacity-40 text-xs px-2 py-1 rounded hover:bg-zinc-800 transition"
                                title={(r.device_count ?? 0) > 0 ? 'Ruangan masih memiliki sensor' : 'Hapus ruangan secara permanen'}
                              >
                                <Trash2 className="h-3 w-3" />
                                Hapus
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}

            {/* TAB CONTENT: SENSOR / PERANGKAT */}
            {activeResourceTab === 'devices' && (
              <div className="space-y-4 flex-1 overflow-y-auto pr-1">
                {/* 1. Tugaskan Sensor Baru */}
                <div className="bg-zinc-950/70 p-3.5 rounded-lg border border-zinc-800 space-y-3">
                  <h4 className="text-xs font-semibold uppercase text-zinc-400 flex items-center gap-1.5">
                    <Plus className="h-4 w-4 text-emerald-400" />
                    Tugaskan Sensor ke Cluster Ini
                  </h4>
                  <div className="flex flex-col sm:flex-row gap-2 items-end">
                    <div className="flex-1">
                      <label className="block text-[11px] text-zinc-500 mb-1">Pilih Sensor Tanpa Cluster</label>
                      <select
                        value={selectedAssignDevId}
                        onChange={(e) => setSelectedAssignDevId(e.target.value)}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                      >
                        <option value="">-- Pilih Sensor / Perangkat --</option>
                        {unassignedResources.devices.map((d) => (
                          <option key={d.dev_id} value={d.dev_id}>
                            {d.dev_name || d.dev_id} ({d.dev_type})
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="w-full sm:w-48">
                      <label className="block text-[11px] text-zinc-500 mb-1">Tugaskan ke Ruangan</label>
                      <select
                        value={selectedAssignDevRoomId}
                        onChange={(e) => setSelectedAssignDevRoomId(e.target.value)}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                      >
                        <option value="">-- Tanpa Ruangan --</option>
                        {resourcesCluster.rooms?.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      onClick={handleAssignDeviceToCluster}
                      disabled={!selectedAssignDevId}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition whitespace-nowrap flex items-center gap-1"
                    >
                      <LinkIcon className="h-3 w-3" />
                      Tugaskan Sensor
                    </button>
                  </div>
                </div>

                {/* 2. Daftar Sensor di Cluster */}
                <div className="border border-zinc-800 rounded-lg overflow-hidden">
                  <div className="bg-zinc-950/80 px-4 py-2 border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase">
                    Daftar Sensor Terdaftar
                  </div>
                  {resourcesLoading ? (
                    <div className="flex justify-center p-8">
                      <RefreshCw className="h-6 w-6 text-emerald-400 animate-spin" />
                    </div>
                  ) : !resourcesCluster.devices || resourcesCluster.devices.length === 0 ? (
                    <div className="p-8 text-center text-zinc-500 text-sm">
                      Belum ada sensor / perangkat yang ditugaskan di cluster ini.
                    </div>
                  ) : (
                    <table className="w-full text-left text-sm text-zinc-300">
                      <thead className="bg-zinc-950/40 text-zinc-500 text-xs uppercase border-b border-zinc-800">
                        <tr>
                          <th className="py-2.5 px-4">Nama & ID Sensor</th>
                          <th className="py-2.5 px-4">Tipe</th>
                          <th className="py-2.5 px-4">Ruangan</th>
                          <th className="py-2.5 px-4 text-right">Aksi</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800">
                        {resourcesCluster.devices.map((d) => (
                          <tr key={d.dev_id} className="hover:bg-zinc-800/40">
                            <td className="py-2.5 px-4">
                              {editingDevId === d.dev_id ? (
                                <div className="flex items-center gap-2">
                                  <input
                                    type="text"
                                    value={editingDevName}
                                    onChange={(e) => setEditingDevName(e.target.value)}
                                    className="bg-zinc-950 border border-emerald-500/60 rounded px-2 py-1 text-xs text-zinc-100"
                                    autoFocus
                                  />
                                  <button
                                    onClick={() => handleSaveEditDevName(d.dev_id)}
                                    className="p-1 text-emerald-400 hover:bg-zinc-800 rounded"
                                    title="Simpan"
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    onClick={() => setEditingDevId(null)}
                                    className="p-1 text-zinc-500 hover:bg-zinc-800 rounded"
                                    title="Batal"
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              ) : (
                                <div>
                                  <div className="flex items-center gap-1.5 font-medium text-zinc-100">
                                    <span
                                      className={`h-2 w-2 rounded-full ${
                                        d.is_active ? 'bg-emerald-400' : 'bg-zinc-600'
                                      }`}
                                    />
                                    <span>{d.dev_name || d.dev_id}</span>
                                    <button
                                      onClick={() => {
                                        setEditingDevId(d.dev_id);
                                        setEditingDevName(d.dev_name || d.dev_id);
                                      }}
                                      className="text-zinc-500 hover:text-zinc-300 p-0.5"
                                      title="Edit Nama Sensor"
                                    >
                                      <Edit2 className="h-3 w-3" />
                                    </button>
                                  </div>
                                  <p className="text-[10px] text-zinc-500 font-mono mt-0.5">{d.dev_id}</p>
                                </div>
                              )}
                            </td>
                            <td className="py-2.5 px-4">
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-950/50 text-indigo-300 border border-indigo-500/20 uppercase">
                                {d.dev_type}
                              </span>
                            </td>
                            <td className="py-2.5 px-4">
                              <select
                                value={d.room_id || 'none'}
                                onChange={(e) => handleChangeDeviceRoom(d.dev_id, e.target.value)}
                                className="bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
                              >
                                <option value="none">-- Tanpa Ruangan --</option>
                                {resourcesCluster.rooms?.map((r) => (
                                  <option key={r.id} value={r.id}>
                                    {r.name}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="py-2.5 px-4 text-right">
                              <button
                                onClick={() => handleUnassignDevice(d.dev_id, d.dev_name || d.dev_id)}
                                className="inline-flex items-center gap-1 text-red-400 hover:text-red-300 text-xs px-2.5 py-1 rounded hover:bg-zinc-800 transition"
                                title="Lepas sensor dari cluster ini"
                              >
                                <Unlink className="h-3 w-3" />
                                Lepas dari Cluster
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-zinc-800">
              <button
                onClick={() => setResourcesCluster(null)}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition"
              >
                Selesai
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Members Management Modal */}
      {membersCluster && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-2xl shadow-2xl space-y-5 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                  <Users className="h-5 w-5 text-indigo-400" />
                  Anggota Cluster: {membersCluster.name}
                </h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Tentukan pengguna dan peran mereka (Admin, Operator, Viewer) di cluster ini.
                </p>
              </div>
              <button
                onClick={() => setMembersCluster(null)}
                className="p-1 text-zinc-400 hover:text-zinc-200 rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Add Member Form */}
            <form onSubmit={handleAddMember} className="bg-zinc-950/60 p-3.5 rounded-lg border border-zinc-800 flex flex-col sm:flex-row gap-3 items-end">
              <div className="flex-1">
                <label className="block text-xs font-medium text-zinc-400 mb-1">Pilih Pengguna</label>
                <select
                  value={selectedUserId}
                  onChange={(e) => setSelectedUserId(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
                  required
                >
                  <option value="">-- Pilih Akun User --</option>
                  {allUsers
                    .filter((u) => u.role !== 'root' && !members.some((m) => m.user_id === u.id))
                    .map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.display_name} (@{u.username})
                      </option>
                    ))}
                </select>
              </div>
              <div className="w-full sm:w-36">
                <label className="block text-xs font-medium text-zinc-400 mb-1">Peran di Cluster</label>
                <select
                  value={selectedRole}
                  onChange={(e) => setSelectedRole(e.target.value as 'admin' | 'operator' | 'viewer')}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-2 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="viewer">Viewer</option>
                  <option value="operator">Operator</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <button
                type="submit"
                disabled={!selectedUserId}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition flex items-center gap-1.5 whitespace-nowrap"
              >
                <UserPlus className="h-4 w-4" />
                Tambah
              </button>
            </form>

            {/* Members List Table */}
            <div className="flex-1 overflow-y-auto min-h-[200px] border border-zinc-800 rounded-lg">
              {membersLoading ? (
                <div className="flex justify-center p-8">
                  <RefreshCw className="h-6 w-6 text-indigo-400 animate-spin" />
                </div>
              ) : members.length === 0 ? (
                <div className="p-8 text-center text-zinc-500 text-sm">
                  Belum ada anggota yang ditugaskan di cluster ini.
                </div>
              ) : (
                <table className="w-full text-left text-sm text-zinc-300">
                  <thead className="bg-zinc-950/80 text-zinc-400 text-xs uppercase border-b border-zinc-800">
                    <tr>
                      <th className="py-2.5 px-4">Pengguna</th>
                      <th className="py-2.5 px-4">Peran di Cluster</th>
                      <th className="py-2.5 px-4 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {members.map((m) => (
                      <tr key={m.id} className="hover:bg-zinc-800/40">
                        <td className="py-2.5 px-4">
                          <p className="font-medium text-zinc-100">{m.display_name || m.username}</p>
                          <p className="text-xs text-zinc-500">@{m.username}</p>
                        </td>
                        <td className="py-2.5 px-4">
                          <select
                            value={m.role}
                            onChange={(e) => handleUpdateMemberRole(m.id, e.target.value as 'admin' | 'operator' | 'viewer')}
                            className="bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-200 focus:outline-none focus:border-indigo-500"
                          >
                            <option value="admin">Admin (Akses Penuh)</option>
                            <option value="operator">Operator (Operasional)</option>
                            <option value="viewer">Viewer (Hanya Melihat)</option>
                          </select>
                        </td>
                        <td className="py-2.5 px-4 text-right">
                          <button
                            onClick={() => handleRemoveMember(m.id)}
                            className="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded hover:bg-zinc-800 transition"
                          >
                            Cabut Akses
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setMembersCluster(null)}
                className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Permissions Matrix Modal */}
      {permissionsCluster && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-2xl shadow-2xl space-y-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-emerald-400" />
                  Matriks Izin: {permissionsCluster.name}
                </h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Konfigurasikan izin fungsional per peran (Admin, Operator, Viewer) untuk cluster ini.
                </p>
              </div>
              <button
                onClick={() => setPermissionsCluster(null)}
                className="p-1 text-zinc-400 hover:text-zinc-200 rounded"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Role Tab Selector */}
            <div className="flex border-b border-zinc-800 gap-2">
              {(['admin', 'operator', 'viewer'] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setActivePermRole(r)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition capitalize ${
                    activePermRole === r
                      ? 'border-indigo-500 text-indigo-400 font-bold'
                      : 'border-transparent text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Peran {r}
                </button>
              ))}
            </div>

            {/* Permissions Checkbox List */}
            <div className="flex-1 overflow-y-auto space-y-2 border border-zinc-800 rounded-lg p-3 bg-zinc-950/40">
              {permsLoading ? (
                <div className="flex justify-center p-8">
                  <RefreshCw className="h-6 w-6 text-indigo-400 animate-spin" />
                </div>
              ) : (
                ALL_PERMISSIONS.map((perm) => {
                  const isGranted = permMatrix[activePermRole]?.[perm.key] ?? false;
                  return (
                    <label
                      key={perm.key}
                      className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-zinc-800/60 cursor-pointer transition select-none"
                    >
                      <input
                        type="checkbox"
                        checked={isGranted}
                        onChange={() => handleTogglePermission(activePermRole, perm.key)}
                        className="mt-1 h-4 w-4 rounded border-zinc-700 bg-zinc-900 text-indigo-600 focus:ring-indigo-500"
                      />
                      <div className="flex-1">
                        <span className="text-sm font-medium text-zinc-200 block">{perm.label}</span>
                        <span className="text-xs text-zinc-500 block">{perm.desc}</span>
                      </div>
                    </label>
                  );
                })
              )}
            </div>

            <div className="flex items-center justify-between pt-2">
              <p className="text-[11px] text-zinc-500">
                * Perubahan izin berlaku saat pengguna cluster melakukan request berikutnya.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPermissionsCluster(null)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-sm transition"
                >
                  Batal
                </button>
                <button
                  type="button"
                  onClick={handleSavePermissions}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition"
                >
                  Simpan Izin {activePermRole}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
