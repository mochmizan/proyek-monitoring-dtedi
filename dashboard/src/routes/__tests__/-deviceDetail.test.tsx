import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeviceDetailPage, Route } from '../device.$deviceId';
import * as api from '../../lib/api';
import type { DeviceResponse, DeviceHistoryResponse, AlertListResponse } from '../../types/api';

vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual('../../lib/api');
  return {
    ...actual,
    fetchCurrentUser: vi.fn(),
    fetchDevice: vi.fn(),
    fetchRooms: vi.fn(),
    fetchAlerts: vi.fn(),
    fetchDeviceHistory: vi.fn(),
  };
});

vi.mock('@tanstack/react-router', async () => {
  const actual = await vi.importActual('@tanstack/react-router');
  return {
    ...actual,
    useRouter: () => ({ navigate: vi.fn() }),
  };
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe('DeviceDetailPage Component Polling & ATS State', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(Route, 'useParams').mockReturnValue({ deviceId: 'DEV-ATS-01' } as any);
    vi.spyOn(Route, 'useSearch').mockReturnValue({ range: '24h' } as any);

    vi.mocked(api.fetchCurrentUser).mockResolvedValue({
      username: 'admin',
      display_name: 'Admin User',
      role: 'admin',
    });

    vi.mocked(api.fetchRooms).mockResolvedValue([
      { id: 'room-1', name: 'Server Room 1', device_count: 2 },
    ]);

    const mockAlerts: AlertListResponse = {
      total: 0,
      alerts: [],
    };
    vi.mocked(api.fetchAlerts).mockResolvedValue(mockAlerts);
  });

  it('renders ATS state badge and Controller State card from device details and history', async () => {
    const mockDevice: DeviceResponse = {
      dev_id: 'DEV-ATS-01',
      dev_name: 'ATS Main Unit',
      dev_type: 'ATS',
      hub_id: 'HUB-01',
      is_active: true,
      status: 'online',
      room_id: 'room-1',
      created_at: '2026-09-01T00:00:00Z',
      latest_reading: {
        state: 'PLN_ONLINE',
        pln: 221.5,
        genset: 0.0,
        aki: 12.6,
      },
    };

    const mockHistory: DeviceHistoryResponse = {
      dev_id: 'DEV-ATS-01',
      dev_type: 'ATS',
      range: '24h',
      total_points: 1,
      points: [
        {
          timestamp: '2026-09-01T10:00:00Z',
          pln: 221.5,
          genset: 0.0,
          aki: 12.6,
          state: 'PLN_ONLINE',
        },
      ],
    };

    vi.mocked(api.fetchDevice).mockResolvedValue(mockDevice);
    vi.mocked(api.fetchDeviceHistory).mockResolvedValue(mockHistory);

    const { wrapper } = createWrapper();
    render(<DeviceDetailPage />, { wrapper });

    await waitFor(() => {
      expect(screen.getByText('ATS Main Unit')).toBeInTheDocument();
    });

    // Check online status badge
    expect(screen.getByText('Online')).toBeInTheDocument();

    // Check Controller State in summary cards
    expect(screen.getByText('Controller State')).toBeInTheDocument();
    expect(screen.getAllByText('PLN_ONLINE').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('PLN Voltage')).toBeInTheDocument();
    expect(screen.getByText('221.5 V')).toBeInTheDocument();
  });

  it('automatically polls fetchDevice and fetchDeviceHistory every ~15s while staring at the screen', async () => {
    vi.useFakeTimers();

    const mockDevice: DeviceResponse = {
      dev_id: 'DEV-ATS-01',
      dev_name: 'ATS Main Unit',
      dev_type: 'ATS',
      hub_id: 'HUB-01',
      is_active: true,
      status: 'online',
      room_id: 'room-1',
      created_at: '2026-09-01T00:00:00Z',
      latest_reading: {
        state: 'PLN_ONLINE',
        pln: 220.0,
        genset: 0.0,
        aki: 12.6,
      },
    };

    const mockHistory: DeviceHistoryResponse = {
      dev_id: 'DEV-ATS-01',
      dev_type: 'ATS',
      range: '24h',
      total_points: 1,
      points: [
        {
          timestamp: '2026-09-01T10:00:00Z',
          pln: 220.0,
          genset: 0.0,
          aki: 12.6,
          state: 'PLN_ONLINE',
        },
      ],
    };

    vi.mocked(api.fetchDevice).mockResolvedValue(mockDevice);
    vi.mocked(api.fetchDeviceHistory).mockResolvedValue(mockHistory);

    const { wrapper } = createWrapper();
    render(<DeviceDetailPage />, { wrapper });

    // Initial mount fetches
    expect(api.fetchDevice).toHaveBeenCalledTimes(1);
    expect(api.fetchDeviceHistory).toHaveBeenCalledTimes(1);

    // Advance by 18 seconds (covering base 15s + 15% max jitter = 17.25s)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(18000);
    });

    // Both device detail and history should have polled at least once more
    expect(vi.mocked(api.fetchDevice).mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(vi.mocked(api.fetchDeviceHistory).mock.calls.length).toBeGreaterThanOrEqual(2);

    // Advance another 18 seconds (total 36s)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(18000);
    });

    expect(vi.mocked(api.fetchDevice).mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(vi.mocked(api.fetchDeviceHistory).mock.calls.length).toBeGreaterThanOrEqual(3);

    vi.useRealTimers();
  });
});
