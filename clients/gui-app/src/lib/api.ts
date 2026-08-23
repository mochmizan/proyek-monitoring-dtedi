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
  RoomMapResponse,
  AlertListResponse,
  AlertFilterParams,
  DeviceHistoryResponse,
  HubResponse,
  HubActionResponse,
} from '../types/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
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
    throw new Error(errorMessage);
  }
  return res.json() as Promise<T>;
}

// ----------------------------------------------------
// Authentication API
// ----------------------------------------------------

export async function loginUser(payload: UserLoginPayload): Promise<UserResponse> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<UserResponse>(res);
}

export async function logoutUser(): Promise<{ status: string }> {
  const res = await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string }>(res);
}

export async function fetchCurrentUser(): Promise<UserResponse> {
  const res = await fetch('/api/auth/me', {
    credentials: 'same-origin',
  });
  return handleResponse<UserResponse>(res);
}

// ----------------------------------------------------
// Rooms API
// ----------------------------------------------------

export async function fetchRooms(): Promise<RoomResponse[]> {
  const res = await fetch('/api/rooms', {
    credentials: 'same-origin',
  });
  return handleResponse<RoomResponse[]>(res);
}

export async function createRoom(payload: RoomCreate): Promise<RoomResponse> {
  const res = await fetch('/api/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<RoomResponse>(res);
}

export async function updateRoom(roomId: string, payload: RoomUpdate): Promise<RoomResponse> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<RoomResponse>(res);
}

export async function deleteRoom(roomId: string): Promise<{ status: string; room_id: string }> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; room_id: string }>(res);
}

export async function uploadFloorPlan(roomId: string, file: File): Promise<FloorPlanUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/floor-plan`, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin',
  });
  return handleResponse<FloorPlanUploadResponse>(res);
}

export async function fetchRoomMap(roomId: string): Promise<RoomMapResponse> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/map`, {
    credentials: 'same-origin',
  });
  return handleResponse<RoomMapResponse>(res);
}

// ----------------------------------------------------
// Devices & Pairing API
// ----------------------------------------------------

export async function fetchDevices(status?: 'pending' | 'active' | 'all'): Promise<DeviceResponse[]> {
  const url = new URL('/api/devices', window.location.origin);
  if (status) {
    url.searchParams.set('status', status);
  }
  const res = await fetch(url.toString(), {
    credentials: 'same-origin',
  });
  return handleResponse<DeviceResponse[]>(res);
}

export async function pairDevice(devId: string, payload: DevicePairRequest): Promise<DeviceResponse> {
  const res = await fetch(`/api/devices/${encodeURIComponent(devId)}/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    credentials: 'same-origin',
  });
  return handleResponse<DeviceResponse>(res);
}

export async function unpairDevice(devId: string): Promise<{ status: string; dev_id: string; is_active: boolean }> {
  const res = await fetch(`/api/devices/${encodeURIComponent(devId)}/unpair`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; dev_id: string; is_active: boolean }>(res);
}

export async function updateThresholds(
  devId: string,
  payload: ThresholdUpdateRequest
): Promise<ThresholdConfig> {
  const res = await fetch(`/api/devices/${encodeURIComponent(devId)}/thresholds`, {
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
  const res = await fetch(`/api/devices/${encodeURIComponent(devId)}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
    credentials: 'same-origin',
  });
  return handleResponse<{ status: string; command_id: string }>(res);
}

// ----------------------------------------------------
// Alerts API
// ----------------------------------------------------

export async function fetchAlerts(params?: AlertFilterParams): Promise<AlertListResponse> {
  const url = new URL('/api/alerts', window.location.origin);
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
  const url = new URL(`/api/devices/${encodeURIComponent(deviceId)}/history`, window.location.origin);
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
  const res = await fetch('/api/hubs', {
    credentials: 'same-origin',
  });
  return handleResponse<HubResponse[]>(res);
}

export async function approveHub(hubId: string): Promise<HubActionResponse> {
  const res = await fetch(`/api/hubs/${encodeURIComponent(hubId)}/approve`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<HubActionResponse>(res);
}

export async function revokeHub(hubId: string): Promise<HubActionResponse> {
  const res = await fetch(`/api/hubs/${encodeURIComponent(hubId)}/revoke`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  return handleResponse<HubActionResponse>(res);
}

