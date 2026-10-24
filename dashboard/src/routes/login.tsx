import { createFileRoute, redirect, useRouter } from '@tanstack/react-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Cpu, ShieldAlert, Loader2 } from 'lucide-react';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { ensureCsrfToken, fetchCurrentUser, loginUser } from '../lib/api';

const loginSearchSchema = z.object({
  redirect: z.string().optional(),
});

export const Route = createFileRoute('/login')({
  validateSearch: (search) => loginSearchSchema.parse(search),
  beforeLoad: async ({ context, search }) => {
    try {
      const user = await context.queryClient.ensureQueryData({
        queryKey: queryKeys.auth.me(),
        queryFn: fetchCurrentUser,
      });
      if (user) {
        if (user.must_change_password) {
          throw redirect({ to: '/change-password' });
        }
        throw redirect({ to: search.redirect || '/' });
      }
    } catch (err) {
      if (typeof err === 'object' && err !== null && 'to' in err) {
        throw err;
      }
      // Allow unauthenticated users to render the login page
    }
  },
  component: LoginPage,
});

function LoginPage() {
  const router = useRouter();
  const search = Route.useSearch();
  const queryClient = useQueryClient();
  
  const [username, setUsername] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: loginUser,
    onSuccess: async (data) => {
      queryClient.setQueryData(queryKeys.auth.me(), data);
      try {
        await ensureCsrfToken();
        await router.invalidate();

        if (data.must_change_password) {
          await router.navigate({ to: '/change-password' });
          return;
        }

        await router.navigate({ to: search.redirect || '/' });
      } catch {
        setError('Login berhasil, tetapi sesi keamanan gagal disiapkan. Silakan coba lagi atau muat ulang halaman.');
      }
    },
    onError: (err: Error) => {
      setError(err.message || 'Invalid username or password');
      setPassword('');
    },
  });

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password');
      return;
    }

    loginMutation.mutate({
      username: username.trim(),
      password: password.trim(),
    });
  };

  const handleQuickLogin = (quickUser: string, quickPass: string) => {
    setError(null);
    setUsername(quickUser);
    setPassword(quickPass);
    loginMutation.mutate({
      username: quickUser,
      password: quickPass,
    });
  };

  return (
    <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl p-8">
      {/* Title */}
      <div className="flex flex-col items-center gap-2 mb-8">
        <div className="h-12 w-12 rounded-full bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
          <Cpu className="h-7 w-7 text-indigo-500" />
        </div>
        <h1 className="text-2xl font-bold text-zinc-100 tracking-wider">Proyek Monitoring</h1>
        <p className="text-zinc-500 text-sm">Temperature & Environment Monitor</p>
      </div>

      {error !== null && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm p-3 rounded-md flex items-center gap-2 mb-6">
          <ShieldAlert className="h-5 w-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Enter admin, operator, or viewer"
            disabled={loginMutation.isPending}
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3.5 py-2.5 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            disabled={loginMutation.isPending}
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3.5 py-2.5 text-zinc-100 text-sm focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
        </div>

        <button
          type="submit"
          disabled={loginMutation.isPending}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors text-sm cursor-pointer flex items-center justify-center gap-2"
        >
          {loginMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Signing In...</span>
            </>
          ) : (
            <span>Sign In</span>
          )}
        </button>
      </form>

      {/* Quick Login Section — dev only, stripped from prod bundle */}
      {import.meta.env.DEV && (
        <div className="mt-8 pt-6 border-t border-zinc-800/80">
          <p className="text-xs text-zinc-500 font-semibold text-center mb-4 uppercase tracking-wider">Quick Sign-In (Roles)</p>
          <div className="grid grid-cols-4 gap-1.5">
            <button
              type="button"
              onClick={() => handleQuickLogin('root', 'root123')}
              disabled={loginMutation.isPending}
              className="bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-700/50 disabled:opacity-50 text-indigo-200 text-xs py-2 px-1 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold text-indigo-300">Root</div>
              <div className="text-[10px] text-indigo-400/80">Super Admin</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickLogin('admin_a', 'admina123')}
              disabled={loginMutation.isPending}
              className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 text-xs py-2 px-1 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold">Admin A</div>
              <div className="text-[10px] text-zinc-500">Cluster Admin</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickLogin('operator', 'operator123')}
              disabled={loginMutation.isPending}
              className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 text-xs py-2 px-1 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold">Operator</div>
              <div className="text-[10px] text-zinc-500">Control</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickLogin('viewer1', 'viewer123')}
              disabled={loginMutation.isPending}
              className="bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-200 text-xs py-2 px-1 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold">Viewer</div>
              <div className="text-[10px] text-zinc-500">Read-Only</div>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
