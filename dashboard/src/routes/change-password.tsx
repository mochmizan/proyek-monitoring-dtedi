import { createFileRoute, redirect, useRouter } from '@tanstack/react-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { KeyRound, ShieldAlert, Loader2, CheckCircle2 } from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import { fetchCurrentUser, changePassword, clearCsrfToken } from '../lib/api';
import type { UserResponse } from '../types/api';

export const Route = createFileRoute('/change-password')({
  beforeLoad: async ({ context }) => {
    let user: UserResponse | null = null;
    try {
      user = await context.queryClient.ensureQueryData({
        queryKey: queryKeys.auth.me(),
        queryFn: fetchCurrentUser,
      });
    } catch {
      // Belum login sama sekali -> lempar ke halaman login
      throw redirect({ to: '/login' });
    }

    if (!user) {
      throw redirect({ to: '/login' });
    }

    // Kalau user ini sebenarnya tidak wajib ganti password,
    // jangan biarkan dia nyasar buka halaman ini secara manual.
    if (!user.must_change_password) {
      throw redirect({ to: '/' });
    }
  },
  component: ChangePasswordPage,
});

function ChangePasswordPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mutation = useMutation({
    mutationFn: changePassword,
    onSuccess: async () => {
      setSuccess(true);
      // must_change_password sekarang false di backend.
      // Sesuai spesifikasi: user diminta login ulang setelah ganti password.
      queryClient.removeQueries({ queryKey: queryKeys.auth.all });
      clearCsrfToken();
      setTimeout(() => {
        router.navigate({ to: '/login' });
      }, 1500);
    },
    onError: (err: Error) => {
      setError(err.message || 'Gagal mengganti password');
    },
  });

  const validate = (): string | null => {
    if (!oldPassword.trim() || !newPassword.trim() || !confirmPassword.trim()) {
      return 'Semua kolom wajib diisi';
    }
    if (newPassword.length < 10) {
      return 'Password baru minimal 10 karakter';
    }
    if (newPassword !== confirmPassword) {
      return 'Konfirmasi password baru tidak cocok';
    }
    if (newPassword === oldPassword) {
      return 'Password baru tidak boleh sama dengan password lama';
    }
    return null;
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    mutation.mutate({ old_password: oldPassword, new_password: newPassword });
  };

  if (success) {
    return (
      <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl p-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="h-12 w-12 rounded-full bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
            <CheckCircle2 className="h-7 w-7 text-emerald-500" />
          </div>
          <h1 className="text-xl font-bold text-zinc-100">Password Berhasil Diganti</h1>
          <p className="text-zinc-500 text-sm">Silakan login ulang menggunakan password baru Anda...</p>
          <Loader2 className="h-5 w-5 animate-spin text-zinc-500 mt-2" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl p-8">
      {/* Title */}
      <div className="flex flex-col items-center gap-2 mb-8">
        <div className="h-12 w-12 rounded-full bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
          <KeyRound className="h-7 w-7 text-indigo-500" />
        </div>
        <h1 className="text-2xl font-bold text-zinc-100 tracking-wider">Ganti Password</h1>
        <p className="text-zinc-500 text-sm text-center">
          Anda menggunakan password sementara. Buat password baru untuk melanjutkan.
        </p>
      </div>

      {error !== null && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm p-3 rounded-md flex items-center gap-2 mb-6">
          <ShieldAlert className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Password Sementara (Lama)
          </label>
          <input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            placeholder="Password yang diberikan admin"
            disabled={mutation.isPending}
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3.5 py-2.5 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Password Baru
          </label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="Minimal 10 karakter"
            disabled={mutation.isPending}
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3.5 py-2.5 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
            Konfirmasi Password Baru
          </label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Ulangi password baru"
            disabled={mutation.isPending}
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3.5 py-2.5 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
        </div>

        <button
          type="submit"
          disabled={mutation.isPending}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors text-sm cursor-pointer flex items-center justify-center gap-2"
        >
          {mutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Menyimpan...</span>
            </>
          ) : (
            <span>Ganti Password</span>
          )}
        </button>
      </form>
    </div>
  );
}
