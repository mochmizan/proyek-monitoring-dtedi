import type {
  UserResponse,
  UserLoginPayload,
  RoomResponse,
  RoomCreate,
  RoomUpdate,
  FloorPlanUploadResponse,
  DeviceResponse,
  DevicePairRequest,
  ThresholdConfig,
  ThresholdUpdateRequest,
  DeviceCommand,
  CommandStatusResponse,
  RoomMapResponse,
  AlertListResponse,
  AlertFilterParams,
  DeviceHistoryResponse,
  HubResponse,
  HubActionResponse,
  ScheduleResponse,
  ScheduleCreate,
  ScheduleUpdate,
  SchedulePreviewResponse,
} from '../types/api';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

const BASE = import.meta.env.VITE_API_BASE || '';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/login') {
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    }
    let errorMessage = `HTTP Error ${res.status}: ${res.statusText}`;
    try {
      const errorData = await res.json();
      if (typeof errorData?.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData?.detail)) {
        errorMessage = errorData.detail
          .map((item: { msg?: string; loc?: string[] }) => item.msg || JSON.stringify(item))
          .join(', ');
      } else if (errorData?.message) {
        errorMessage = errorData.message;
      }
    } catch {
      // Ignore JSON parsing fallback
    }
    throw new ApiError(res.status, errorMessage);
  }
  return res.json() as Promise<T>;
}

// ----------------------------------------------------
// Authentication API
// ----------------------------------------------------

export async function loginUser(payload: UserLoginPayload): Promise<UserResponse> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<UserResponse>(res);
}

export async function logoutUser(): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/api/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string }>(res);
}

export async function fetchCurrentUser(): Promise<UserResponse | null> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    return null;
  }
  return handleResponse<UserResponse>(res);
}

// ----------------------------------------------------
// Rooms API
// ----------------------------------------------------

export async function fetchRooms(): Promise<RoomResponse[]> {
  const res = await fetch(`${BASE}/api/rooms`, {
    credentials: 'same-origin',
  });
  return handleResponse<RoomResponse[]>(res);
}

export async function createRoom(payload: RoomCreate): Promise<RoomResponse> {
  const res = await fetch(`${BASE}/api/rooms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<RoomResponse>(res);
}

export async function updateRoom(roomId: string, payload: RoomUpdate): Promise<RoomResponse> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<RoomResponse>(res);
}

export async function deleteRoom(roomId: string): Promise<{ status: string; room_id: string }> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; room_id: string }>(res);
}

export async function uploadFloorPlan(roomId: string, file: File): Promise<FloorPlanUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}/floor-plan`, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin',
  });
  return handleResponse<FloorPlanUploadResponse>(res);
}

export async function fetchRoomMap(roomId: string): Promise<RoomMapResponse> {
  const res = await fetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}/map`, {
    credentials: 'same-origin',
  });
  return handleResponse<RoomMapResponse>(res);
}

// ----------------------------------------------------
// Devices & Pairing API
// ----------------------------------------------------

export async function fetchDevices(status?: 'pending' | 'active' | 'all'): Promise<DeviceResponse[]> {
  const url = new URL(`${BASE}/api/devices`, window.location.origin);
  if (status) {
    url.searchParams.set('status', status);
  }
  const res = await fetch(url.toString(), {
    credentials: 'same-origin',
  });
  return handleResponse<DeviceResponse[]>(res);
}

export async function fetchDevice(devId: string): Promise<DeviceResponse> {
  const res = await fetch(`${BASE}/api/devices/${encodeURIComponent(devId)}`, {
    credentials: 'same-origin',
  });
  return handleResponse<DeviceResponse>(res);
}

export async function pairDevice(devId: string, payload: DevicePairRequest): Promise<DeviceResponse> {
  const res = await fetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<DeviceResponse>(res);
}

export async function unpairDevice(devId: string): Promise<{ status: string; dev_id: string; is_active: boolean }> {
  const res = await fetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/unpair`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; dev_id: string; is_active: boolean }>(res);
}

export async function updateThresholds(
  devId: string,
  payload: ThresholdUpdateRequest
): Promise<ThresholdConfig> {
  const res = await fetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/thresholds`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<ThresholdConfig>(res);
}

export async function sendDeviceCommand(
  devId: string,
  command: DeviceCommand
): Promise<{ status: string; command_id: string }> {
  const res = await fetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; command_id: string }>(res);
}

export async function fetchCommandStatus(commandId: string): Promise<CommandStatusResponse> {
  const res = await fetch(`${BASE}/api/commands/${encodeURIComponent(commandId)}`, {
    credentials: 'same-origin',
  });
  return handleResponse<CommandStatusResponse>(res);
}

// ----------------------------------------------------
// Alerts API
// ----------------------------------------------------

export async function fetchAlerts(params?: AlertFilterParams): Promise<AlertListResponse> {
  const url = new URL(`${BASE}/api/alerts`, window.location.origin);
  if (params) {
    if (params.rooms && params.rooms.length > 0) {
      params.rooms.forEach((r) => url.searchParams.append('rooms', r));
    }
    if (params.room) {
      url.searchParams.set('room', params.room);
    }
    if (params.devices && params.devices.length > 0) {
      params.devices.forEach((d) => url.searchParams.append('devices', d));
    }
    if (params.device) {
      url.searchParams.set('device', params.device);
    }
    if (params.severity && params.severity !== 'all' && params.severity !== 'All') {
      url.searchParams.set('severity', params.severity.toLowerCase());
    }
    if (params.status && params.status !== 'all') {
      url.searchParams.set('status', params.status.toLowerCase());
    }
    if (params.start_time) {
      url.searchParams.set('start_time', params.start_time);
    }
    if (params.end_time) {
      url.searchParams.set('end_time', params.end_time);
    }
    if (typeof params.limit === 'number') {
      url.searchParams.set('limit', params.limit.toString());
    }
    if (typeof params.offset === 'number') {
      url.searchParams.set('offset', params.offset.toString());
    }
  }

  const res = await fetch(url.toString(), {
    credentials: 'same-origin',
  });
  return handleResponse<AlertListResponse>(res);
}

// ----------------------------------------------------
// Telemetry History API
// ----------------------------------------------------

export async function fetchDeviceHistory(deviceId: string, range = '24h'): Promise<DeviceHistoryResponse> {
  const url = new URL(`${BASE}/api/devices/${encodeURIComponent(deviceId)}/history`, window.location.origin);
  if (range) {
    url.searchParams.set('range', range);
  }
  const res = await fetch(url.toString(), {
    credentials: 'same-origin',
  });
  return handleResponse<DeviceHistoryResponse>(res);
}

// ----------------------------------------------------
// Hubs API
// ----------------------------------------------------

export async function fetchHubs(): Promise<HubResponse[]> {
  const res = await fetch(`${BASE}/api/hubs`, {
    credentials: 'same-origin',
  });
  return handleResponse<HubResponse[]>(res);
}

export async function approveHub(hubId: string): Promise<HubActionResponse> {
  const res = await fetch(`${BASE}/api/hubs/${encodeURIComponent(hubId)}/approve`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<HubActionResponse>(res);
}

export async function revokeHub(hubId: string): Promise<HubActionResponse> {
  const res = await fetch(`${BASE}/api/hubs/${encodeURIComponent(hubId)}/revoke`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<HubActionResponse>(res);
}

// ----------------------------------------------------
// Schedules API — ATS flexible cron (server-scheduler)
// ----------------------------------------------------

export async function fetchSchedules(params?: { hub_id?: string; dev_id?: string; enabled?: boolean }): Promise<ScheduleResponse[]> {
  const url = new URL(`${BASE}/api/schedules`, window.location.origin);
  if (params?.hub_id) url.searchParams.set('hub_id', params.hub_id);
  if (params?.dev_id) url.searchParams.set('dev_id', params.dev_id);
  if (typeof params?.enabled === 'boolean') url.searchParams.set('enabled', String(params.enabled));
  const res = await fetch(url.toString(), { credentials: 'same-origin' });
  return handleResponse<ScheduleResponse[]>(res);
}

export async function fetchSchedule(id: string): Promise<ScheduleResponse> {
  const res = await fetch(`${BASE}/api/schedules/${encodeURIComponent(id)}`, { credentials: 'same-origin' });
  return handleResponse<ScheduleResponse>(res);
}

export async function createSchedule(payload: ScheduleCreate): Promise<ScheduleResponse> {
  const res = await fetch(`${BASE}/api/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<ScheduleResponse>(res);
}

export async function updateSchedule(id: string, payload: ScheduleUpdate): Promise<ScheduleResponse> {
  const res = await fetch(`${BASE}/api/schedules/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<ScheduleResponse>(res);
}

export async function deleteSchedule(id: string): Promise<{ status: string; id: string }> {
  const res = await fetch(`${BASE}/api/schedules/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; id: string }>(res);
}

export async function runNowSchedule(id: string): Promise<{ status: string; command_id: string }> {
  const res = await fetch(`${BASE}/api/schedules/${encodeURIComponent(id)}/run-now`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; command_id: string }>(res);
}

export async function previewScheduleCron(cronExpr: string, tz?: string): Promise<SchedulePreviewResponse> {
  const url = new URL(`${BASE}/api/schedules/preview`, window.location.origin);
  url.searchParams.set('cron_expr', cronExpr);
  if (tz) url.searchParams.set('tz', tz);
  const res = await fetch(url.toString(), { credentials: 'same-origin' });
  return handleResponse<SchedulePreviewResponse>(res);
}
