import { createRootRouteWithContext, Link, Outlet, redirect, useLocation, useRouter, useRouterState, isRedirect } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { QueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { queryKeys } from '../lib/queryKeys';
import { fetchCurrentUser, logoutUser, fetchAlerts } from '../lib/api';
import { POLL_ALERTS_MS } from '../lib/constants';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { TooltipProvider } from '../components/ui/tooltip';
import { AppSidebar } from '../components/sidebar/AppSidebar';
import { SidebarTrigger } from '../components/sidebar/SidebarTrigger';
import { useSidebarKeyboard } from '../hooks/useSidebarKeyboard';

export interface MyRouterContext {
  queryClient: QueryClient;
}

function RootError({ error }: { error: Error }) {
  return (
    <div className="w-full min-h-screen bg-zinc-950 flex flex-col items-center justify-center p-6 text-center gap-4">
      <h1 className="text-xl font-bold text-zinc-100">Application Error</h1>
      <p className="text-sm text-zinc-400 max-w-md">{error.message || 'Unexpected error'}</p>
      <button onClick={() => window.location.reload()} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-sm font-medium cursor-pointer">Reload</button>
    </div>
  );
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
  beforeLoad: async ({ context, location }) => {
    if (location.pathname === '/login') {
      return;
    }

    try {
      const user = await context.queryClient.ensureQueryData({
        queryKey: queryKeys.auth.me(),
        queryFn: fetchCurrentUser,
        staleTime: 60000,
      });
      if (!user) {
        throw redirect({
          to: '/login',
          search: {
            redirect: location.href,
          },
        });
      }
      return { user };
    } catch (error: unknown) {
      if (isRedirect(error)) throw error;
      throw redirect({
        to: '/login',
        search: {
          redirect: location.href,
        },
      });
    }
  },
  component: RootLayout,
  errorComponent: RootError,
});

function RootLayout() {
  const location = useLocation();
  const router = useRouter();
  const isNavigating = useRouterState({ select: (s) => s.status === 'pending' });
  const queryClient = useQueryClient();
  const isLoginPage = location.pathname === '/login';

  useSidebarKeyboard();

  const { data: currentUser } = useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchCurrentUser,
    staleTime: 60000,
  });

  const { data: alertsData } = useQuery({
    queryKey: queryKeys.alerts.list({ limit: 100 }),
    queryFn: () => fetchAlerts({ limit: 100 }),
    refetchInterval: POLL_ALERTS_MS,
    refetchIntervalInBackground: false,
    enabled: !isLoginPage && !!currentUser,
  });

  const logoutMutation = useMutation({
    mutationFn: logoutUser,
    onSuccess: async () => {
      queryClient.setQueryData(queryKeys.auth.me(), null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.all });
      router.navigate({ to: '/login' });
    },
  });

  const handleLogout = () => {
    logoutMutation.mutate();
  };

  // If path is /login, render without the dashboard shell
  if (isLoginPage) {
    return (
      <div className="w-full min-h-screen bg-zinc-950 flex items-center justify-center p-4">
        {isNavigating && <div className="fixed top-0 left-0 right-0 h-1 bg-indigo-500 z-60 animate-pulse" />}
        <Outlet />
      </div>
    );
  }

  // Count active / unresolved alerts in the last 24 hours
  const recentAlerts = alertsData?.alerts || [];
  const alertCount = recentAlerts.filter((alert) => {
    const alertTime = new Date(alert.timestamp).getTime();
    const now = Date.now();
    return now - alertTime <= 24 * 60 * 60 * 1000 && !alert.resolved_at;
  }).length;

  const role = currentUser?.role || 'viewer';
  const isAdmin = role === 'admin';

  return (
    <TooltipProvider>
      <div className="flex h-screen w-screen p-0 gap-0 overflow-hidden bg-zinc-950 text-zinc-100">
        {isNavigating && (
          <div className="fixed top-0 left-0 right-0 h-1 bg-indigo-500 z-60 animate-pulse" />
        )}

        {/* Desktop Sidebar & Mobile Radix Drawer */}
        <AppSidebar
          currentUser={currentUser}
          role={role}
          isAdmin={isAdmin}
          alertCount={alertCount}
          onLogout={handleLogout}
          isLoggingOut={logoutMutation.isPending}
        />

        {/* Main Canvas Area */}
        <div className="flex-1 flex flex-col min-w-0 h-full rounded-none bg-zinc-900/40 backdrop-blur-xl border-0 shadow-none overflow-hidden relative">
          {/* Sticky Inset Header */}
          <header className="h-14 sm:h-16 border-b border-zinc-800/80 bg-zinc-900/70 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between flex-shrink-0 z-10">
            <div className="flex items-center gap-3">
              <SidebarTrigger />
              <h2 className="text-lg font-semibold text-zinc-100 capitalize">
                {location.pathname === '/' ? 'Dashboard Overview' : location.pathname.substring(1).replace('/', ' / ')}
              </h2>
            </div>

            {/* Telemetry Indicator & Alert Bell */}
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-1.5 bg-emerald-500/10 px-2.5 py-1 rounded-none border border-emerald-500/20">
                <span className="h-2 w-2 rounded-none bg-emerald-500 animate-pulse" />
                <span className="text-xs font-semibold text-emerald-400">Live Gateway Connected</span>
              </div>
              <Link
                to="/alerts"
                search={{}}
                className="relative p-2 rounded-none text-zinc-400 hover:text-zinc-100 transition-colors"
                title="Alerts History"
              >
                <Bell className="h-5 w-5" />
                {alertCount > 0 && (
                  <span className="absolute top-1.5 right-1.5 h-4 min-w-[16px] px-1 rounded-none bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                    {alertCount}
                  </span>
                )}
              </Link>
            </div>
          </header>

          {/* Main Content Area */}
          <main className="flex-1 min-w-0 overflow-y-auto p-4 sm:p-6 relative">
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}

