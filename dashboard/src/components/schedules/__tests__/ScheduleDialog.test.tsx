
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
    previewScheduleCron: vi.fn().mockResolvedValue({ cron_expr: '0 18 * * 0', valid: true, human: 'At 6:00 PM, only on Sunday', next_runs: [] }),
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
});
