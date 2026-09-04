export const queryKeys = {
  auth: {
    all: ['auth'] as const,
    me: () => [...queryKeys.auth.all, 'me'] as const,
  },
  devices: {
    all: ['devices'] as const,
    list: (status?: string, dev_type?: string) => [...queryKeys.devices.all, 'list', { status, dev_type }] as const,
    detail: (id: string) => [...queryKeys.devices.all, 'detail', id] as const,
    history: (id: string, range?: string) => [...queryKeys.devices.all, 'history', id, { range }] as const,
    pending: () => [...queryKeys.devices.all, 'pending'] as const,
    active: () => [...queryKeys.devices.all, 'active'] as const,
  },
  rooms: {
    all: ['rooms'] as const,
    list: () => [...queryKeys.rooms.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.rooms.all, 'detail', id] as const,
    map: (id: string) => [...queryKeys.rooms.all, 'map', id] as const,
    sparklines: (range = '6h', maxPoints = 24) => ['rooms', 'sparklines', range, maxPoints] as const,
  },
  alerts: {
    all: ['alerts'] as const,
    list: (filters?: Record<string, unknown>) => [...queryKeys.alerts.all, 'list', filters] as const,
  },
  hubs: {
    all: ['hubs'] as const,
    list: () => [...queryKeys.hubs.all, 'list'] as const,
  },
  schedules: {
    all: ['schedules'] as const,
    list: (filters?: Record<string, unknown>) => [...queryKeys.schedules.all, 'list', filters] as const,
    detail: (id: string) => [...queryKeys.schedules.all, 'detail', id] as const,
    preview: (cron: string, tz?: string) => [...queryKeys.schedules.all, 'preview', cron, tz] as const,
  },
  commands: {
    all: ['commands'] as const,
    detail: (id: string) => [...queryKeys.commands.all, 'detail', id] as const,
  },
};
