import { createFileRoute, redirect } from '@tanstack/react-router';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { useState, useEffect, useId } from 'react';
import { z } from 'zod';
import {
  ScrollText,
  Search,
  RefreshCw,
  Eye,
  Copy,
  Check,
  ShieldAlert,
  X,
  Activity,
  User,
  Clock,
  Globe,
  Filter,
} from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import { getActivityLogs } from '../lib/api';
import type { ActivityLogItem, UserResponse } from '../types/api';
import { formatWIBDateTime } from '../lib/dateUtils';
import { Pagination } from '../components/ui/pagination';
import { Button } from '../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../components/ui/dialog';
import { cn } from '../lib/utils';

const activityLogsSearchSchema = z.object({
  page: z.number().int().min(1).catch(1).optional(),
  username: z.string().catch('').optional(),
  role: z.string().catch('').optional(),
  limit: z.number().int().min(1).max(200).catch(50).optional(),
});

export const Route = createFileRoute('/activity-logs')({
  validateSearch: (search) => activityLogsSearchSchema.parse(search),
  beforeLoad: ({ context }) => {
    const user =
      (context as { user?: UserResponse }).user ??
      context.queryClient.getQueryData<UserResponse>(queryKeys.auth.me());
    if (!user || (user.role !== 'admin' && user.role !== 'root' && user.role !== 'super_admin')) {
      throw redirect({ to: '/' });
    }
  },
  component: ActivityLogsPage,
});

const DEFAULT_PAGE_SIZE = 50;

function ActivityLogsPage() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();

  const searchId = useId();
  const roleSelectId = useId();

  const currentPage = search.page ?? 1;
  const currentUsername = search.username ?? '';
  const currentRole = search.role ?? '';
  const pageSize = search.limit ?? DEFAULT_PAGE_SIZE;

  const [usernameInput, setUsernameInput] = useState(currentUsername);
  const [selectedLog, setSelectedLog] = useState<ActivityLogItem | null>(null);
  const [copied, setCopied] = useState(false);

  // Synchronize local input state if URL search param changes externally
  useEffect(() => {
    setUsernameInput(currentUsername);
  }, [currentUsername]);

  // Debounced update for username search
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = usernameInput.trim();
      if (trimmed !== currentUsername) {
        navigate({
          search: (prev) => ({
            ...prev,
            username: trimmed || undefined,
            page: 1,
          }),
          resetScroll: false,
        });
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [usernameInput, currentUsername, navigate]);

  const { data, isFetching, refetch } = useQuery({
    queryKey: queryKeys.activityLogs.list({
      page: currentPage,
      limit: pageSize,
      username: currentUsername || undefined,
      role: currentRole || undefined,
    }),
    queryFn: () =>
      getActivityLogs({
        page: currentPage,
        limit: pageSize,
        username: currentUsername || undefined,
        role: currentRole || undefined,
      }),
    placeholderData: keepPreviousData,
    staleTime: 10000,
  });

  const logs = data?.items ?? [];
  const totalLogs = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalLogs / pageSize));

  const handleRoleChange = (roleValue: string) => {
    navigate({
      search: (prev) => ({
        ...prev,
        role: roleValue || undefined,
        page: 1,
      }),
      resetScroll: false,
    });
  };

  const handleClearFilters = () => {
    setUsernameInput('');
    navigate({
      search: (prev) => ({
        ...prev,
        username: undefined,
        role: undefined,
        page: 1,
      }),
      resetScroll: false,
    });
  };

  const handleCopyJson = async (jsonString: string) => {
    try {
      await navigator.clipboard.writeText(jsonString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      setCopied(false);
    }
  };

  const hasActiveFilters = Boolean(currentUsername || currentRole);

  const getRoleBadgeClass = (role?: string | null) => {
    switch ((role || '').toLowerCase()) {
      case 'admin':
        return 'bg-purple-500/20 text-purple-300 border-purple-500/30';
      case 'operator':
        return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
      case 'viewer':
        return 'bg-zinc-500/20 text-zinc-300 border-zinc-500/30';
      default:
        return 'bg-zinc-800 text-zinc-400 border-zinc-700';
    }
  };

  const getCategoryBadgeClass = (category?: string | null) => {
    switch ((category || '').toLowerCase()) {
      case 'auth':
        return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
      case 'commands':
      case 'device_control':
        return 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30';
      case 'devices':
        return 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30';
      case 'rooms':
        return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
      case 'account_management':
        return 'bg-rose-500/15 text-rose-400 border-rose-500/30';
      case 'config':
      case 'system_adjustment':
        return 'bg-orange-500/15 text-orange-400 border-orange-500/30';
      default:
        return 'bg-zinc-800 text-zinc-300 border-zinc-700';
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-indigo-400">
              <ScrollText className="h-5 w-5" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-100">
              Riwayat Aktivitas Pengguna
            </h1>
          </div>
          <p className="text-xs text-zinc-400 mt-1 pl-10">
            Log audit komprehensif tindakan pengguna sistem, autentikasi, kontrol perangkat, dan konfigurasi.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs h-9 bg-zinc-900 border-zinc-800 hover:bg-zinc-800 text-zinc-200"
          >
            <RefreshCw className={cn('h-3.5 w-3.5 mr-1.5', isFetching && 'animate-spin text-indigo-400')} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-zinc-900/90 border border-zinc-800 rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
          <Filter className="h-3.5 w-3.5" />
          <span>Filter & Pencarian</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          {/* Search Username */}
          <div className="relative md:col-span-2">
            <label htmlFor={searchId} className="sr-only">Cari username</label>
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-500" />
            <input
              id={searchId}
              type="text"
              placeholder="Cari berdasarkan username pengguna..."
              value={usernameInput}
              onChange={(e) => setUsernameInput(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-md pl-9 pr-9 py-2 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            {usernameInput && (
              <button
                type="button"
                onClick={() => setUsernameInput('')}
                className="absolute right-2.5 top-2.5 text-zinc-500 hover:text-zinc-300"
                title="Hapus pencarian"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Role Dropdown */}
          <div>
            <label htmlFor={roleSelectId} className="sr-only">Filter Role</label>
            <select
              id={roleSelectId}
              value={currentRole}
              onChange={(e) => handleRoleChange(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-md px-3 py-2 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500 transition-colors"
            >
              <option value="">Semua Role</option>
              <option value="admin">Admin</option>
              <option value="operator">Operator</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>

          {/* Clear Filters Button */}
          <div className="flex items-center">
            {hasActiveFilters ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearFilters}
                className="text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 h-9 px-3 w-full sm:w-auto"
              >
                <X className="h-3.5 w-3.5 mr-1" />
                Reset Filter
              </Button>
            ) : (
              <span className="text-xs text-zinc-500 italic pl-1 hidden md:inline">
                Menampilkan semua log
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Activity Logs Table */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden shadow-xl">
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-zinc-400" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
              Daftar Log Aktivitas ({totalLogs})
            </h3>
          </div>
          {isFetching && (
            <span className="text-[11px] text-indigo-400 animate-pulse flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping" />
              Menyinkronkan...
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-zinc-300">
            <thead className="bg-zinc-950 text-[10px] font-semibold uppercase text-zinc-500 border-b border-zinc-800">
              <tr>
                <th className="px-6 py-3.5">Waktu</th>
                <th className="px-6 py-3.5">Pengguna & Role</th>
                <th className="px-6 py-3.5">Aksi & Kategori</th>
                <th className="px-6 py-3.5">Status</th>
                <th className="px-6 py-3.5">IP Address</th>
                <th className="px-6 py-3.5 text-right">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {logs.map((log) => {
                const isSuccess = log.activity?.status?.toLowerCase() === 'success';
                return (
                  <tr
                    key={log.id}
                    className="hover:bg-zinc-800/30 transition-colors group"
                  >
                    {/* Waktu */}
                    <td className="px-6 py-4 text-zinc-400 font-mono whitespace-nowrap">
                      {formatWIBDateTime(log.created_at)}
                    </td>

                    {/* Pengguna & Role */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <div className="font-semibold text-zinc-100">
                          {log.user_name}
                        </div>
                        <span
                          className={cn(
                            'px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border',
                            getRoleBadgeClass(log.role)
                          )}
                        >
                          {log.role || 'unknown'}
                        </span>
                      </div>
                      {log.user_id && (
                        <div className="text-[10px] text-zinc-500 font-mono">
                          ID: {log.user_id.slice(0, 8)}...
                        </div>
                      )}
                    </td>

                    {/* Aksi & Kategori */}
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-zinc-200">
                          {log.activity?.action || '—'}
                        </span>
                        {log.activity?.category && (
                          <span
                            className={cn(
                              'px-2 py-0.5 rounded text-[10px] font-medium border uppercase tracking-wider',
                              getCategoryBadgeClass(log.activity.category)
                            )}
                          >
                            {log.activity.category}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Status */}
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-[10px] font-semibold inline-flex items-center gap-1.5 border',
                          isSuccess
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : 'bg-red-500/10 text-red-400 border-red-500/20'
                        )}
                      >
                        <span
                          className={cn(
                            'h-1.5 w-1.5 rounded-full',
                            isSuccess ? 'bg-emerald-400' : 'bg-red-400'
                          )}
                        />
                        {log.activity?.status ? log.activity.status.toUpperCase() : 'UNKNOWN'}
                      </span>
                    </td>

                    {/* IP Address */}
                    <td className="px-6 py-4 font-mono text-zinc-400 text-[11px] whitespace-nowrap">
                      {log.activity?.ip_address || '—'}
                    </td>

                    {/* Tombol Detail JSON */}
                    <td className="px-6 py-4 text-right whitespace-nowrap">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedLog(log)}
                        className="h-8 px-2.5 text-xs text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 gap-1.5"
                        title="Lihat Detail JSON"
                      >
                        <Eye className="h-3.5 w-3.5 text-indigo-400" />
                        <span>Detail</span>
                      </Button>
                    </td>
                  </tr>
                );
              })}

              {logs.length === 0 && !isFetching && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-zinc-500">
                    <ShieldAlert className="h-9 w-9 mx-auto mb-2 text-zinc-700" />
                    <p className="text-sm font-medium text-zinc-400">
                      Tidak ada log aktivitas yang ditemukan.
                    </p>
                    <p className="text-xs text-zinc-600 mt-1">
                      {hasActiveFilters
                        ? 'Coba sesuaikan kata kunci atau filter pencarian Anda.'
                        : 'Belum ada rekaman aktivitas yang tercatat.'}
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={totalLogs}
          pageSize={pageSize}
          onPageChange={(page) =>
            navigate({
              search: (prev) => ({ ...prev, page }),
              resetScroll: false,
            })
          }
          isLoading={isFetching}
          itemLabel="aktivitas"
        />
      </div>

      {/* JSON Details Dialog */}
      <Dialog open={Boolean(selectedLog)} onOpenChange={(open) => !open && setSelectedLog(null)}>
        <DialogContent className="sm:max-w-2xl bg-zinc-900 border-zinc-800 text-zinc-100">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base text-zinc-100">
              <ScrollText className="h-4 w-4 text-indigo-400" />
              <span>Detail Log Aktivitas</span>
            </DialogTitle>
            <DialogDescription className="text-xs text-zinc-400">
              ID Log: <span className="font-mono text-zinc-300">{selectedLog?.id}</span>
            </DialogDescription>
          </DialogHeader>

          {selectedLog && (
            <div className="space-y-4 py-2 text-xs">
              {/* Metadata Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-zinc-950 border border-zinc-800/80 rounded-lg">
                <div>
                  <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                    <User className="h-3 w-3" /> Pengguna
                  </div>
                  <div className="font-semibold text-zinc-200 mt-0.5 truncate">
                    {selectedLog.user_name}
                  </div>
                  <div className="text-[10px] text-zinc-500 uppercase mt-0.5">
                    {selectedLog.role || '—'}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                    <Activity className="h-3 w-3" /> Aksi
                  </div>
                  <div className="font-semibold text-zinc-200 mt-0.5 truncate">
                    {selectedLog.activity?.action || '—'}
                  </div>
                  <div className="text-[10px] text-zinc-500 uppercase mt-0.5">
                    {selectedLog.activity?.category || '—'}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                    <Clock className="h-3 w-3" /> Waktu
                  </div>
                  <div className="font-mono text-zinc-300 mt-0.5 text-[11px]">
                    {formatWIBDateTime(selectedLog.created_at)}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] text-zinc-500 uppercase flex items-center gap-1">
                    <Globe className="h-3 w-3" /> IP Address
                  </div>
                  <div className="font-mono text-zinc-300 mt-0.5 text-[11px]">
                    {selectedLog.activity?.ip_address || '—'}
                  </div>
                </div>
              </div>

              {/* JSON Payload Details */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                    Isi Details (JSON)
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      handleCopyJson(
                        JSON.stringify(selectedLog.activity?.details ?? {}, null, 2)
                      )
                    }
                    className="h-7 px-2.5 text-xs gap-1.5 bg-zinc-950 border-zinc-800 text-zinc-300 hover:text-zinc-100 hover:bg-zinc-800"
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                    <span>{copied ? 'Tersalin!' : 'Salin JSON'}</span>
                  </Button>
                </div>

                <pre className="p-3.5 bg-zinc-950 border border-zinc-800 rounded-md text-xs font-mono text-zinc-300 overflow-x-auto max-h-[300px] whitespace-pre-wrap break-all select-all">
                  {JSON.stringify(selectedLog.activity?.details ?? {}, null, 2)}
                </pre>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedLog(null)}
              className="text-xs bg-zinc-950 border-zinc-800 text-zinc-300 hover:bg-zinc-800"
            >
              Tutup
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
