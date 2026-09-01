import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeviceControls } from '../Controls';
import type { DeviceResponse } from '../../../types/api';
import * as api from '../../../lib/api';

vi.mock('../../../lib/api', async () => {
  const actual = await vi.importActual('../../../lib/api');
  return {
    ...actual,
    updateThresholds: vi.fn(),
    sendDeviceCommand: vi.fn(),
  };
});

function renderControls(device: DeviceResponse, role: string = 'admin') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DeviceControls device={device} role={role} />
    </QueryClientProvider>
  );
}

const mockDevice: DeviceResponse = {
  dev_id: 'TS-TEST-01',
  dev_name: 'Temperature Node 01',
  dev_type: 'TS',
  hub_id: 'HUB-01',
  is_active: true,
  status: 'online',
  threshold_config: {
    warning: 28,
    critical: 32,
    hysteresis: 0.5,
    debounce_seconds: 60,
  },
};

describe('DeviceControls Component', () => {
  it('renders baseline server values correctly', () => {
    renderControls(mockDevice);

    const warnInput = screen.getByLabelText(/Warning Threshold/i) as HTMLInputElement;
    const critInput = screen.getByLabelText(/Critical Threshold/i) as HTMLInputElement;
    const hystInput = screen.getByLabelText(/Hysteresis/i) as HTMLInputElement;
    const debInput = screen.getByLabelText(/Debounce Window/i) as HTMLInputElement;

    expect(warnInput.value).toBe('28');
    expect(critInput.value).toBe('32');
    expect(hystInput.value).toBe('0.5');
    expect(debInput.value).toBe('60');

    // Reset button should not be present when clean
    expect(screen.queryByText('Reset to Server Values')).not.toBeInTheDocument();
  });

  it('regression: focused input is not overwritten by background server prop updates', () => {
    const { rerender } = renderControls(mockDevice);

    const warnInput = screen.getByLabelText(/Warning Threshold/i) as HTMLInputElement;

    // Focus and start editing
    fireEvent.focus(warnInput);
    fireEvent.change(warnInput, { target: { value: '29.5' } });
    expect(warnInput.value).toBe('29.5');

    // Background poll updates device prop to new values
    const updatedDevice: DeviceResponse = {
      ...mockDevice,
      threshold_config: {
        warning: 30,
        critical: 35,
        hysteresis: 0.8,
        debounce_seconds: 90,
      },
    };

    const queryClient = new QueryClient();
    rerender(
      <QueryClientProvider client={queryClient}>
        <DeviceControls device={updatedDevice} role="admin" />
      </QueryClientProvider>
    );

    // Form value should NOT be overwritten
    expect(warnInput.value).toBe('29.5');
  });

  it('dirty form values are not overwritten by background server prop updates', () => {
    const { rerender } = renderControls(mockDevice);

    const critInput = screen.getByLabelText(/Critical Threshold/i) as HTMLInputElement;

    // Edit and blur
    fireEvent.focus(critInput);
    fireEvent.change(critInput, { target: { value: '34' } });
    fireEvent.blur(critInput);
    expect(critInput.value).toBe('34');

    // Reset button should now be visible
    expect(screen.getByText('Reset to Server Values')).toBeInTheDocument();

    // Background poll updates device prop
    const updatedDevice: DeviceResponse = {
      ...mockDevice,
      threshold_config: {
        warning: 29,
        critical: 36,
        hysteresis: 0.6,
        debounce_seconds: 80,
      },
    };

    const queryClient = new QueryClient();
    rerender(
      <QueryClientProvider client={queryClient}>
        <DeviceControls device={updatedDevice} role="admin" />
      </QueryClientProvider>
    );

    // Should retain user value 34 despite background poll
    expect(critInput.value).toBe('34');
  });

  it('clicking "Reset to Server Values" resets input values to server baseline and clears dirty state', () => {
    renderControls(mockDevice);

    const warnInput = screen.getByLabelText(/Warning Threshold/i) as HTMLInputElement;
    const critInput = screen.getByLabelText(/Critical Threshold/i) as HTMLInputElement;

    fireEvent.change(warnInput, { target: { value: '30' } });
    fireEvent.change(critInput, { target: { value: '35' } });

    expect(warnInput.value).toBe('30');
    expect(critInput.value).toBe('35');

    const resetButton = screen.getByText('Reset to Server Values');
    expect(resetButton).toBeInTheDocument();

    // Click Reset
    fireEvent.click(resetButton);

    // Form values should return to mockDevice baseline
    expect(warnInput.value).toBe('28');
    expect(critInput.value).toBe('32');

    // Reset button should disappear
    expect(screen.queryByText('Reset to Server Values')).not.toBeInTheDocument();
  });

  it('successful threshold submission updates inputs from response and resets dirty state', async () => {
    vi.mocked(api.updateThresholds).mockResolvedValueOnce({
      warning: 29.0,
      critical: 33.0,
      hysteresis: 0.6,
      debounce_seconds: 45,
    });

    renderControls(mockDevice);

    const warnInput = screen.getByLabelText(/Warning Threshold/i) as HTMLInputElement;
    const critInput = screen.getByLabelText(/Critical Threshold/i) as HTMLInputElement;

    fireEvent.change(warnInput, { target: { value: '29' } });
    fireEvent.change(critInput, { target: { value: '33' } });

    expect(screen.getByText('Reset to Server Values')).toBeInTheDocument();

    const saveButton = screen.getByRole('button', { name: /Save Thresholds/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.updateThresholds).toHaveBeenCalledWith('TS-TEST-01', {
        warning: 29,
        critical: 33,
        hysteresis: 0.5,
        debounce_seconds: 60,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Thresholds updated successfully')).toBeInTheDocument();
      expect(screen.queryByText('Reset to Server Values')).not.toBeInTheDocument();
    });
  });

  it('disables ATS command inputs and button while dispatch is pending', async () => {
    const mockATSDevice: DeviceResponse = {
      dev_id: 'ATS-TEST-01',
      dev_name: 'ATS Generator 01',
      dev_type: 'ATS',
      hub_id: 'HUB-01',
      is_active: true,
      status: 'online',
    };

    let resolveCommand!: (val: { status: string; command_id: string }) => void;
    vi.mocked(api.sendDeviceCommand).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCommand = resolve;
        })
    );

    renderControls(mockATSDevice, 'admin');

    const modeSelect = screen.getByLabelText(/Operating Mode/i) as HTMLSelectElement;
    fireEvent.change(modeSelect, { target: { value: 'auto' } });

    const submitBtn = screen.getByRole('button', { name: /Send Command/i });
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);

    // Immediately after click, dispatch is pending
    await waitFor(() => {
      expect(screen.getByText(/Dispatching.../i)).toBeInTheDocument();
      expect(modeSelect).toBeDisabled();
      expect(screen.getByRole('button', { name: /Dispatching.../i })).toBeDisabled();
    });

    // Resolve API response
    resolveCommand({ status: 'queued', command_id: 'cmd-ats-01' });

    await waitFor(() => {
      expect(screen.getByText(/Queued on server — waiting for edge hub delivery.../i)).toBeInTheDocument();
      expect(modeSelect).toBeDisabled();
      expect(screen.getByRole('button', { name: /Awaiting Hub Delivery.../i })).toBeDisabled();
    });
  });

  it('disables AC command inputs and button while dispatch is pending', async () => {
    const mockACDevice: DeviceResponse = {
      dev_id: 'AC-TEST-01',
      dev_name: 'Server Room AC',
      dev_type: 'AC',
      hub_id: 'HUB-01',
      is_active: true,
      status: 'online',
    };

    let resolveCommand!: (val: { status: string; command_id: string }) => void;
    vi.mocked(api.sendDeviceCommand).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCommand = resolve;
        })
    );

    renderControls(mockACDevice, 'operator');

    const ac1Btn = screen.getByRole('button', { name: /Unit AC 1/i });
    const ac2Btn = screen.getByRole('button', { name: /Unit AC 2/i });
    const powerOnBtn = screen.getByRole('button', { name: /Power ON/i });
    const submitBtn = screen.getByRole('button', { name: /Send AC IR Command/i });

    expect(ac1Btn).not.toBeDisabled();
    expect(ac2Btn).not.toBeDisabled();
    expect(powerOnBtn).not.toBeDisabled();
    expect(submitBtn).not.toBeDisabled();

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.sendDeviceCommand).toHaveBeenCalledWith('AC-TEST-01', {
        target: 'AC1',
        action: 'ON',
      });
    });

    // Buttons should be disabled during dispatch
    expect(ac1Btn).toBeDisabled();
    expect(ac2Btn).toBeDisabled();
    expect(powerOnBtn).toBeDisabled();
    expect(screen.getByRole('button', { name: /Queuing IR Command.../i })).toBeDisabled();

    resolveCommand({ status: 'delivered', command_id: 'cmd-ac-01' });

    await waitFor(() => {
      expect(screen.getByText(/Delivered to edge hub at/i)).toBeInTheDocument();
    });
  });

  it('viewer role cannot access command controls', () => {
    const mockACDevice: DeviceResponse = {
      dev_id: 'AC-TEST-01',
      dev_name: 'Server Room AC',
      dev_type: 'AC',
      hub_id: 'HUB-01',
      is_active: true,
      status: 'online',
    };

    renderControls(mockACDevice, 'viewer');
    expect(screen.getByText(/Your current role \(viewer\) does not have permission/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Send AC IR Command/i })).not.toBeInTheDocument();
  });
});
