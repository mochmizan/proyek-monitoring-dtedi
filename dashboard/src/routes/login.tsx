import { createFileRoute, redirect, useRouter } from '@tanstack/react-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Thermometer, ShieldAlert, Loader2 } from 'lucide-react';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchCurrentUser, loginUser } from '../lib/api';

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
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.all });
      await router.invalidate();
      router.navigate({ to: search.redirect || '/' });
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
    <div className="w-full max-w-md bg-card border rounded-lg shadow-2xl p-8">
      {/* Title */}
      <div className="flex flex-col items-center gap-2 mb-8">
        <div className="size-12 rounded-full bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20">
          <Thermometer className="size-7 text-indigo-500" />
        </div>
        <h1 className="text-2xl font-bold text-foreground tracking-wider">TracerTemp IoT</h1>
        <p className="text-muted-foreground text-sm">Temperature & Environment Monitor</p>
      </div>

      {error !== null && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive text-sm p-3 rounded-md flex items-center gap-2 mb-6">
          <ShieldAlert className="size-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Enter admin, operator, or viewer"
            disabled={loginMutation.isPending}
            className="w-full bg-muted border rounded px-3.5 py-2.5 text-foreground text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            disabled={loginMutation.isPending}
            className="w-full bg-muted border rounded px-3.5 py-2.5 text-foreground text-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:opacity-50"
          />
        </div>

        <button
          type="submit"
          disabled={loginMutation.isPending}
          className="w-full bg-primary hover:bg-primary/90 disabled:opacity-50 text-primary-foreground font-medium py-2.5 rounded transition-colors text-sm cursor-pointer flex items-center justify-center gap-2"
        >
          {loginMutation.isPending ? (
            <>
              <Loader2 data-icon="inline-start" className="animate-spin" />
              <span>Signing In...</span>
            </>
          ) : (
            <span>Sign In</span>
          )}
        </button>
      </form>

      {/* Quick Login Section — dev only, stripped from prod bundle */}
      {import.meta.env.DEV && (
        <div className="mt-8 pt-6 border-t border-border/80">
          <p className="text-xs text-muted-foreground font-semibold text-center mb-4 uppercase tracking-wider">Quick Sign-In (Roles)</p>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => handleQuickLogin('admin', 'admin')}
              disabled={loginMutation.isPending}
              className="bg-muted hover:bg-muted/80 disabled:opacity-50 text-foreground text-xs py-2 px-1.5 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold">Admin</div>
              <div className="text-[10px] text-muted-foreground">Full Access</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickLogin('operator', 'operator')}
              disabled={loginMutation.isPending}
              className="bg-muted hover:bg-muted/80 disabled:opacity-50 text-foreground text-xs py-2 px-1.5 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold">Operator</div>
              <div className="text-[10px] text-muted-foreground">Control Access</div>
            </button>
            <button
              type="button"
              onClick={() => handleQuickLogin('viewer', 'viewer')}
              disabled={loginMutation.isPending}
              className="bg-muted hover:bg-muted/80 disabled:opacity-50 text-foreground text-xs py-2 px-1.5 rounded text-center transition-colors cursor-pointer"
            >
              <div className="font-semibold">Viewer</div>
              <div className="text-[10px] text-muted-foreground">Read-Only</div>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
