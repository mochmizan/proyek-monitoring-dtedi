import { createFileRoute, redirect } from '@tanstack/react-router';
import { useState } from 'react';
import { cn } from '../lib/utils';
import { Layers, Cpu, Sliders } from 'lucide-react';
import { z } from 'zod';
import { queryKeys } from '../lib/queryKeys';
import { fetchCurrentUser } from '../lib/api';
import { RoomsTab } from '../components/settings/RoomsTab';
import { DevicesTab } from '../components/settings/DevicesTab';
import { HubsTab } from '../components/settings/HubsTab';

const settingsSearchSchema = z.object({
  tab: z.enum(['rooms', 'devices', 'thresholds']).catch('rooms').optional(),
});

export const Route = createFileRoute('/settings')({
  beforeLoad: async ({ context }) => {
    try {
      const user = await context.queryClient.ensureQueryData({ queryKey: queryKeys.auth.me(), queryFn: fetchCurrentUser });
      if (!user || user.role !== 'admin') throw redirect({ to: '/' });
    } catch { throw redirect({ to: '/' }); }
  },
  validateSearch: (search) => settingsSearchSchema.parse(search),
  component: SettingsPage,
});

function SettingsPage() {
  const search = Route.useSearch() as { tab?: 'rooms' | 'devices' | 'thresholds' };
  const [activeTab, setActiveTab] = useState<'rooms' | 'devices' | 'thresholds'>(search.tab ?? 'rooms');

  return (
    <div className="space-y-8">
      <div><h1 className="text-2xl font-bold text-zinc-100">System Administration</h1><p className="text-xs text-zinc-500 mt-1">Manage facility rooms, self-discovered device pairing, and global telemetry threshold configuration.</p></div>
      <div className="flex border-b border-zinc-800 gap-4 text-sm font-semibold">
        <button onClick={() => setActiveTab('rooms')} className={cn("pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer", activeTab === 'rooms' ? "border-indigo-500 text-indigo-400" : "border-transparent text-zinc-500 hover:text-zinc-300")}><Layers className="h-4 w-4" /><span>Rooms Management</span></button>
        <button onClick={() => setActiveTab('devices')} className={cn("pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer", activeTab === 'devices' ? "border-indigo-500 text-indigo-400" : "border-transparent text-zinc-500 hover:text-zinc-300")}><Cpu className="h-4 w-4" /><span>Device Pairing</span></button>
        <button onClick={() => setActiveTab('thresholds')} className={cn("pb-3 px-1 border-b-2 flex items-center gap-2 transition-colors cursor-pointer", activeTab === 'thresholds' ? "border-indigo-500 text-indigo-400" : "border-transparent text-zinc-500 hover:text-zinc-300")}><Sliders className="h-4 w-4" /><span>Global Thresholds</span></button>
      </div>
      {activeTab === 'rooms' && <RoomsTab />}
      {activeTab === 'devices' && <DevicesTab />}
      {activeTab === 'thresholds' && <HubsTab />}
    </div>
  );
}
