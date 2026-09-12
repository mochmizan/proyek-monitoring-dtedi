
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ScheduleDialog from '../ScheduleDialog';
import type { DeviceResponse, ScheduleResponse } from '@/types/api';
import * as api from '@/lib/api';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    createSchedule: vi.fn().mockResolvedValue({ id: 'new-1' }),
    updateSchedule: vi.fn().mockResolvedValue({ id: '42' }),
    previewScheduleCron: vi.fn().mockResolvedValue({ cron_expr: '0 18 * * 0', valid: true, human: 'At 18:00, only on Sunday', next_runs: [] }),
  };
});

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const mockDevices: DeviceResponse[] = [
  { dev_id: 'ATS_01', dev_name: 'Main Generator ATS', dev_type: 'ATS', hub_id: 'HUB_01', room_id: 'ROOM_01', is_active: true, status: 'online', last_seen: new Date().toISOString() },
];

const mockSchedule: ScheduleResponse = {
  id: '42', dev_id: 'ATS_01', hub_id: 'HUB_01', cron_expr: '0 18 * * 0', payload: { mode: 'manual', start_genset: 'on' }, tz: 'Asia/Jakarta', enabled: true, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
};

describe('ScheduleDialog Component', () => {
  it('renders create mode when editing is null', () => {
    renderWithClient(<ScheduleDialog open={true} onOpenChange={vi.fn()} editing={null} atsDevices={mockDevices} />);
    expect(screen.getByText(/New (ATS )?schedule/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create schedule/i })).toBeInTheDocument();
  });
  it('renders edit mode when editing is supplied', () => {
    renderWithClient(<ScheduleDialog open={true} onOpenChange={vi.fn()} editing={mockSchedule} atsDevices={mockDevices} />);
    expect(screen.getByText('Edit schedule #42')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
  });
  it('shows error when submitting without device', async () => {
    renderWithClient(<ScheduleDialog open={true} onOpenChange={vi.fn()} editing={null} atsDevices={[]} />);
    fireEvent.click(screen.getByRole('button', { name: /create schedule/i }));
    expect(await screen.findByText(/Select a device/i)).toBeInTheDocument();
  });
  it('renders builder and preview', () => {
    renderWithClient(<ScheduleDialog open={true} onOpenChange={vi.fn()} editing={null} atsDevices={mockDevices} />);
    expect(screen.getByText("Frequency")).toBeInTheDocument();
  });
  it('submits create mutation on valid create form submission', async () => {
    renderWithClient(<ScheduleDialog open={true} onOpenChange={vi.fn()} editing={null} atsDevices={mockDevices} />);
    fireEvent.click(screen.getByRole('button', { name: /create schedule/i }));
    await waitFor(() => {
      expect(api.createSchedule).toHaveBeenCalledWith(expect.objectContaining({ dev_id: 'ATS_01', cron_expr: '0 18 * * 0', tz: 'Asia/Jakarta', enabled: true }));
    });
  });
  it('submits update mutation on edit form submission', async () => {
    renderWithClient(<ScheduleDialog open={true} onOpenChange={vi.fn()} editing={mockSchedule} atsDevices={mockDevices} />);
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => {
      expect(api.updateSchedule).toHaveBeenCalledWith('42', expect.objectContaining({ dev_id: 'ATS_01', cron_expr: '0 18 * * 0', tz: 'Asia/Jakarta', enabled: true }));
    });
  });

  it('preserves user-edited cronExpr, payload, and devId on devices polling re-render', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const initialDevices: DeviceResponse[] = [
      { dev_id: 'ATS_01', dev_name: 'Main Generator ATS', dev_type: 'ATS', hub_id: 'HUB_01', room_id: 'ROOM_01', is_active: true, status: 'online', last_seen: new Date().toISOString() },
    ];

    const customSchedule: ScheduleResponse = {
      id: '99',
      dev_id: 'ATS_01',
      hub_id: 'HUB_01',
      cron_expr: '0 12 * * 1',
      payload: { mode: 'manual', start_genset: 'off' },
      tz: 'Asia/Jakarta',
      enabled: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ScheduleDialog open={true} onOpenChange={vi.fn()} editing={customSchedule} devices={initialDevices} />
      </QueryClientProvider>
    );

    // Initial time is 12:00 from customSchedule
    expect(screen.getByDisplayValue('12:00')).toBeInTheDocument();

    // User changes time from 12:00 to 09:30
    const timeInput = screen.getByDisplayValue('12:00');
    fireEvent.change(timeInput, { target: { value: '09:30' } });
    expect(screen.getByDisplayValue('09:30')).toBeInTheDocument();

    // Simulate polling refetch: devices array reference changes (new array and object instances)
    const polledDevices: DeviceResponse[] = [
      { dev_id: 'ATS_01', dev_name: 'Main Generator ATS Polled', dev_type: 'ATS', hub_id: 'HUB_01', room_id: 'ROOM_01', is_active: true, status: 'online', last_seen: new Date().toISOString() },
    ];
    rerender(
      <QueryClientProvider client={queryClient}>
        <ScheduleDialog open={true} onOpenChange={vi.fn()} editing={customSchedule} devices={polledDevices} />
      </QueryClientProvider>
    );

    // Time remains 09:30, not reset back to 12:00 or default 18:00
    expect(screen.getByDisplayValue('09:30')).toBeInTheDocument();

    // Submitting form confirms cronExpr, devId, and custom payload were preserved
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => {
      expect(api.updateSchedule).toHaveBeenCalledWith(
        '99',
        expect.objectContaining({
          dev_id: 'ATS_01',
          cron_expr: '30 9 * * 1',
          payload: { mode: 'manual', start_genset: 'off' },
          tz: 'Asia/Jakarta',
          enabled: true,
        })
      );
    });
  });

  it('preserves user-edited cronExpr and devId in create mode on devices polling re-render', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const initialDevices: DeviceResponse[] = [
      { dev_id: 'ATS_01', dev_name: 'Main Generator ATS', dev_type: 'ATS', hub_id: 'HUB_01', room_id: 'ROOM_01', is_active: true, status: 'online', last_seen: new Date().toISOString() },
    ];

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <ScheduleDialog open={true} onOpenChange={vi.fn()} editing={null} devices={initialDevices} />
      </QueryClientProvider>
    );

    // Initial time is 18:00
    expect(screen.getByDisplayValue('18:00')).toBeInTheDocument();

    // User changes time from 18:00 to 07:45
    const timeInput = screen.getByDisplayValue('18:00');
    fireEvent.change(timeInput, { target: { value: '07:45' } });
    expect(screen.getByDisplayValue('07:45')).toBeInTheDocument();

    // Simulate polling refetch: devices array reference changes
    const polledDevices: DeviceResponse[] = [
      { dev_id: 'ATS_01', dev_name: 'Main Generator ATS Polled', dev_type: 'ATS', hub_id: 'HUB_01', room_id: 'ROOM_01', is_active: true, status: 'online', last_seen: new Date().toISOString() },
      { dev_id: 'ATS_02', dev_name: 'Backup Generator ATS', dev_type: 'ATS', hub_id: 'HUB_01', room_id: 'ROOM_01', is_active: true, status: 'online', last_seen: new Date().toISOString() },
    ];
    rerender(
      <QueryClientProvider client={queryClient}>
        <ScheduleDialog open={true} onOpenChange={vi.fn()} editing={null} devices={polledDevices} />
      </QueryClientProvider>
    );

    // Time remains 07:45, not reset back to default 18:00
    expect(screen.getByDisplayValue('07:45')).toBeInTheDocument();

    // Submitting form confirms cronExpr and devId were preserved
    fireEvent.click(screen.getByRole('button', { name: /create schedule/i }));
    await waitFor(() => {
      expect(api.createSchedule).toHaveBeenCalledWith(
        expect.objectContaining({
          dev_id: 'ATS_01',
          cron_expr: '45 7 * * 0',
          tz: 'Asia/Jakarta',
          enabled: true,
        })
      );
    });
  });
});
