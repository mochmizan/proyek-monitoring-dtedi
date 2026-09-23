import { createFileRoute, redirect } from '@tanstack/react-router';
import { useState, useEffect, useCallback } from 'react';
import {
  Users,
  Search,
  UserPlus,
  KeyRound,
  LogOut,
  Trash2,
  ShieldAlert,
  Copy,
  Check,
  RefreshCw,
  UserCheck,
  UserX,
} from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import {
  fetchAdminUsers,
  createAdminUser,
  updateAdminUser,
  updateAdminUserStatus,
  resetAdminUserPassword,
  revokeAdminUserSessions,
  deleteAdminUser,
  ApiError,
} from '../lib/api';
import type { UserResponse, UserRole } from '../types/api';

export const Route = createFileRoute('/users')({
  beforeLoad: ({ context }) => {
    const user =
      (context as { user?: UserResponse }).user ??
      context.queryClient.getQueryData<UserResponse>(queryKeys.auth.me());
    if (!user || user.role !== 'admin') {
      throw redirect({ to: '/' });
    }
  },
  component: UserManagementPage,
});

function UserManagementPage() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<UserRole | ''>('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);

  const [showAddModal, setShowAddModal] = useState(false);
  const [tempPasswordModal, setTempPasswordModal] = useState<{ show: boolean; pass: string; title: string }>({
    show: false,
    pass: '',
    title: '',
  });
  const [copied, setCopied] = useState(false);

  const [formData, setFormData] = useState({
    username: '',
    display_name: '',
    role: 'viewer' as UserRole,
  });

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const data = await fetchAdminUsers({
        page,
        page_size: pageSize,
        search: search || undefined,
        role: roleFilter || undefined,
        is_active: statusFilter === '' ? undefined : statusFilter === 'true',
      });
      setUsers(data.items);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setErrorMsg('Akses ditolak. Halaman ini khusus Administrator.');
      } else {
        setErrorMsg(err instanceof Error ? err.message : 'Terjadi kesalahan sistem.');
      }
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, roleFilter, statusFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data = await createAdminUser(formData);
      setShowAddModal(false);
      setFormData({ username: '', display_name: '', role: 'viewer' });
      fetchUsers();

      if (!data.temp_password) {
        alert(
          `Akun ${data.username} berhasil dibuat, tetapi password sementara tidak diterima dari server. ` +
            `Gunakan tombol "Reset Password Sementara" pada baris user ini untuk mendapatkan password baru.`
        );
        return;
      }

      setTempPasswordModal({
        show: true,
        pass: data.temp_password,
        title: `Akun ${data.username} Berhasil Dibuat!`,
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal membuat user.');
    }
  };

  const handleToggleStatus = async (user: UserResponse) => {
    if (!confirm(`Apakah Anda yakin ingin ${user.is_active ? 'menonaktifkan' : 'mengaktifkan'} akun ${user.username}?`)) return;
    try {
      await updateAdminUserStatus(user.id, { is_active: !user.is_active });
      fetchUsers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal mengubah status.');
    }
  };

  const handleChangeRole = async (user: UserResponse, newRole: UserRole) => {
    if (newRole === user.role) return;
    if (user.role === 'admin') {
      // Jaga-jaga: dropdown sudah di-disable untuk role admin, tapi tetap
      // diblokir di sini juga supaya gak bisa dipanggil dengan cara lain.
      alert('Role Admin tidak dapat diubah lewat halaman ini.');
      return;
    }
    const roleLabel: Record<UserRole, string> = { admin: 'Admin', operator: 'Operator', viewer: 'Viewer' };
    if (!confirm(`Ubah role ${user.username} dari ${roleLabel[user.role]} menjadi ${roleLabel[newRole]}?`)) return;
    try {
      await updateAdminUser(user.id, { role: newRole });
      fetchUsers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal mengubah role.');
    }
  };

  const handleResetPassword = async (user: UserResponse) => {
    if (!confirm(`Reset password untuk ${user.username}? Pengguna akan dikeluarkan dari semua sesi.`)) return;
    try {
      const data = await resetAdminUserPassword(user.id);

      if (!data.temp_password) {
        alert(
          `Password ${user.username} berhasil direset, tetapi password baru tidak diterima dari server. ` +
            `Coba reset ulang, atau hubungi tim backend.`
        );
        fetchUsers();
        return;
      }

      setTempPasswordModal({
        show: true,
        pass: data.temp_password,
        title: `Reset Password ${user.username} Berhasil!`,
      });
      fetchUsers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal mereset password.');
    }
  };

  const handleRevokeSessions = async (user: UserResponse) => {
    if (!confirm(`Cabut seluruh sesi aktif milik ${user.username}? User harus login ulang.`)) return;
    try {
      const data = await revokeAdminUserSessions(user.id);
      alert(data.message);
      fetchUsers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal mencabut sesi.');
    }
  };

  const handleDeleteUser = async (user: UserResponse) => {
    if (!confirm(`HAPUS PERMANEN akun ${user.username}? Tindakan ini tidak dapat dibatalkan.`)) return;
    try {
      await deleteAdminUser(user.id);
      fetchUsers();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Gagal menghapus akun.');
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-zinc-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 text-zinc-100">
            <Users className="h-6 w-6 text-indigo-400" />
            User Management
          </h1>
          <p className="text-sm text-zinc-500">Kelola hak akses, status akun, dan keamanan pengguna dashboard.</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 px-4 py-2.5 rounded-lg text-sm font-medium transition shadow-lg shadow-indigo-600/20"
        >
          <UserPlus className="h-4 w-4" />
          Tambah Akun Baru
        </button>
      </div>

      {errorMsg && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Cari nama atau username..."
            value={search}
            onChange={(e) => {
              setPage(1);
              setSearch(e.target.value);
            }}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-indigo-500"
          />
        </div>
        <select
          value={roleFilter}
          onChange={(e) => {
            setPage(1);
            setRoleFilter(e.target.value as UserRole | '');
          }}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
        >
          <option value="">Semua Role</option>
          <option value="admin">Admin</option>
          <option value="operator">Operator</option>
          <option value="viewer">Viewer</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => {
            setPage(1);
            setStatusFilter(e.target.value);
          }}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
        >
          <option value="">Semua Status Akun</option>
          <option value="true">Aktif</option>
          <option value="false">Nonaktif</option>
        </select>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-900/80 border-b border-zinc-800 text-zinc-500">
              <tr>
                <th className="p-4">Pengguna</th>
                <th className="p-4">Role</th>
                <th className="p-4">Status Akun</th>
                <th className="p-4">Sesi</th>
                <th className="p-4">Login Terakhir</th>
                <th className="p-4 text-right">Aksi Keamanan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-zinc-500">
                    <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-indigo-400" />
                    Memuat data pengguna...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-zinc-600">
                    Tidak ada data pengguna yang ditemukan.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-zinc-800/30 transition">
                    <td className="p-4">
                      <div className="font-medium text-zinc-200">{u.display_name || u.username}</div>
                      <div className="text-xs text-zinc-500">@{u.username}</div>
                    </td>
                    <td className="p-4">
                      <select
                        value={u.role}
                        onChange={(e) => handleChangeRole(u, e.target.value as UserRole)}
                        disabled={u.role === 'admin'}
                        title={u.role === 'admin' ? 'Role Admin tidak dapat diubah lewat sini' : undefined}
                        className={`px-2.5 py-1 rounded-md text-xs font-semibold capitalize border focus:outline-none focus:ring-1 focus:ring-indigo-500 ${
                          u.role === 'admin'
                            ? 'bg-purple-500/20 text-purple-300 border-purple-500/30 cursor-not-allowed opacity-70'
                            : u.role === 'operator'
                            ? 'bg-blue-500/20 text-blue-300 border-blue-500/30 cursor-pointer'
                            : 'bg-zinc-500/20 text-zinc-300 border-zinc-500/30 cursor-pointer'
                        }`}
                      >
                        <option value="admin">Admin</option>
                        <option value="operator">Operator</option>
                        <option value="viewer">Viewer</option>
                      </select>
                    </td>
                    <td className="p-4">
                      <button
                        onClick={() => handleToggleStatus(u)}
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition ${
                          u.is_active
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20'
                            : 'bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/20'
                        }`}
                      >
                        {u.is_active ? <UserCheck className="h-3 w-3" /> : <UserX className="h-3 w-3" />}
                        {u.is_active ? 'Aktif' : 'Nonaktif'}
                      </button>
                    </td>
                    <td className="p-4">
                      <span
                        className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                          u.is_online ? 'text-emerald-400' : 'text-zinc-500'
                        }`}
                      >
                        <span className={`h-2 w-2 rounded-full ${u.is_online ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'}`} />
                        {u.is_online ? 'Online' : 'Offline'}
                      </span>
                    </td>
                    <td className="p-4 text-xs text-zinc-500">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString('id-ID') : 'Belum Pernah'}
                    </td>
                    <td className="p-4 text-right space-x-1">
                      <button
                        onClick={() => handleResetPassword(u)}
                        title="Reset Password Sementara"
                        className="p-1.5 hover:bg-zinc-800 text-amber-400 rounded transition"
                      >
                        <KeyRound className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleRevokeSessions(u)}
                        title="Cabut Semua Sesi (Kick)"
                        className="p-1.5 hover:bg-zinc-800 text-blue-400 rounded transition"
                      >
                        <LogOut className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => handleDeleteUser(u)}
                        title="Hapus Akun"
                        className="p-1.5 hover:bg-zinc-800 text-red-400 rounded transition"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 border border-zinc-800 p-6 rounded-xl w-full max-w-md shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
              <UserPlus className="h-5 w-5 text-indigo-400" />
              Buat Pengguna Baru
            </h3>
            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Username</label>
                <input
                  type="text"
                  required
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm focus:outline-none focus:border-indigo-500"
                  placeholder="operator_server"
                />
                <p className="text-[10px] text-zinc-600 mt-1">Huruf kecil, angka, dan underscore saja.</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Nama Tampilan (Display Name)</label>
                <input
                  type="text"
                  required
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm focus:outline-none focus:border-indigo-500"
                  placeholder="Operator Ruang Server"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Role</label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value as UserRole })}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm focus:outline-none focus:border-indigo-500"
                >
                  <option value="viewer">Viewer (Hanya Melihat)</option>
                  <option value="operator">Operator (Melihat & Mengendalikan IoT)</option>
                  <option value="admin">Admin (Akses Penuh Management)</option>
                </select>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-sm transition"
                >
                  Batal
                </button>
                <button type="submit" className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition">
                  Simpan & Generate Password
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {tempPasswordModal.show && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50">
          <div className="bg-zinc-900 border border-indigo-500/40 p-6 rounded-xl w-full max-w-md shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-emerald-400 flex items-center gap-2">
              <ShieldAlert className="h-5 w-5" />
              {tempPasswordModal.title}
            </h3>
            <p className="text-xs text-zinc-300">
              Salin password sementara di bawah ini. Password ini <strong>hanya ditampilkan satu kali</strong> dan tidak dapat dilihat lagi
              setelah jendela ini ditutup.
            </p>
            <div className="flex items-center justify-between bg-zinc-950 p-3 rounded-lg border border-zinc-800 font-mono text-lg text-indigo-300">
              <span>{tempPasswordModal.pass}</span>
              <button
                onClick={() => copyToClipboard(tempPasswordModal.pass)}
                className="flex items-center gap-1 text-xs bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 px-3 py-1.5 rounded transition"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Tersalin' : 'Salin'}
              </button>
            </div>
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setTempPasswordModal({ show: false, pass: '', title: '' })}
                className="w-full bg-zinc-800 hover:bg-zinc-700 py-2 rounded-lg text-sm font-medium transition"
              >
                Saya Sudah Menyalin Password Ini
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
