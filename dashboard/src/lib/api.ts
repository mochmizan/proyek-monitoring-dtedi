import type {
  UserResponse,
  UserLoginPayload,
  ChangePasswordPayload,
  UserWithTempPasswordResponse,
  UserListResponse,
  AdminUserCreatePayload,
  AdminUserUpdatePayload,
  AdminUserStatusPayload,
  AdminUserListParams,
  AuditLogResponse,
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
  RoomSparklinesResponse,
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
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

const BASE = import.meta.env.VITE_API_BASE || '';

// ----------------------------------------------------
// CSRF Helper & Handler
// ----------------------------------------------------

let csrfToken: string | null = null;
let csrfTokenPromise: Promise<string> | null = null;
let csrfGeneration = 0;

export function ensureCsrfToken(): Promise<string> {
  if (csrfToken) {
    return Promise.resolve(csrfToken);
  }

  if (!csrfTokenPromise) {
    const generation = csrfGeneration;
    const request = (async () => {
      const res = await fetch(`${BASE}/api/auth/csrf-token`, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { 'Cache-Control': 'no-store' },
      });
      const data = await handleResponse<{ csrf_token: string }>(res);
      if (generation !== csrfGeneration) {
        throw new Error('CSRF token request was superseded');
      }
      csrfToken = data.csrf_token;
      return csrfToken;
    })();
    csrfTokenPromise = request;
    request.then(
      () => {
        if (csrfTokenPromise === request) csrfTokenPromise = null;
      },
      () => {
        if (csrfTokenPromise === request) csrfTokenPromise = null;
      },
    );
  }

  return csrfTokenPromise;
}

export function clearCsrfToken(): void {
  csrfGeneration += 1;
  csrfToken = null;
  csrfTokenPromise = null;
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const RETRYABLE_CSRF_CODES = new Set(['CSRF_TOKEN_INVALID', 'CSRF_TOKEN_MISSING']);

function requestPath(input: string | URL): string {
  return new URL(String(input), 'http://localhost').pathname;
}

function hasReplayableBody(body: BodyInit | null | undefined): boolean {
  return typeof ReadableStream === 'undefined' || !(body instanceof ReadableStream);
}

async function responseErrorCode(res: Response): Promise<string | undefined> {
  try {
    const data = (await res.clone().json()) as { detail?: { code?: string } };
    return data.detail?.code;
  } catch {
    return undefined;
  }
}

export async function apiFetch(
  input: string | URL,
  init: RequestInit = {}
): Promise<Response> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  const requiresCsrf = UNSAFE_METHODS.has(method) && requestPath(input) !== '/api/auth/login';

  if (requiresCsrf) {
    headers.set('X-CSRF-Token', await ensureCsrfToken());
  }

  let response = await fetch(input, {
    ...init,
    headers,
    credentials: 'same-origin',
  });

  if (requiresCsrf && response.status === 403 && hasReplayableBody(init.body)) {
    const code = await responseErrorCode(response);
    if (code && RETRYABLE_CSRF_CODES.has(code)) {
      const rejectedToken = headers.get('X-CSRF-Token');
      if (csrfToken === rejectedToken) {
        clearCsrfToken();
      }
      headers.set('X-CSRF-Token', await ensureCsrfToken());
      response = await fetch(input, {
        ...init,
        headers,
        credentials: 'same-origin',
      });
    }
  }

  return response;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/login') {
      clearCsrfToken();
      window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    }
    let errorMessage = `HTTP Error ${res.status}: ${res.statusText}`;
    let errorCode: string | undefined;
    try {
      const errorData = await res.json();
      if (typeof errorData?.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (errorData?.detail && typeof errorData.detail === 'object' && !Array.isArray(errorData.detail)) {
        errorCode = typeof errorData.detail.code === 'string' ? errorData.detail.code : undefined;
        errorMessage = typeof errorData.detail.message === 'string' ? errorData.detail.message : errorMessage;
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
    throw new ApiError(res.status, errorMessage, errorCode);
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
    credentials: 'same-origin',
    body: JSON.stringify(payload),
  });
  return handleResponse<UserResponse>(res);
}

export async function logoutUser(): Promise<{ status: string }> {
  try {
    const res = await apiFetch(`${BASE}/api/auth/logout`, {
      method: 'POST',
    });
    return await handleResponse<{ status: string }>(res);
  } finally {
    clearCsrfToken();
  }
}

export async function fetchCurrentUser(): Promise<UserResponse | null> {
  const res = await apiFetch(`${BASE}/api/auth/me`);
  if (res.status === 401) {
    clearCsrfToken();
    return null;
  }
  return handleResponse<UserResponse>(res);
}

export async function changePassword(payload: ChangePasswordPayload): Promise<{ status: string; message: string }> {
  const res = await apiFetch(`${BASE}/api/auth/change-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<{ status: string; message: string }>(res);
}

// ----------------------------------------------------
// Admin: User Management API (/api/admin/users)
// ----------------------------------------------------

export async function fetchAdminUsers(params?: AdminUserListParams): Promise<UserListResponse> {
  const url = new URL(`${BASE}/api/admin/users`, window.location.origin);
  if (params?.search) url.searchParams.set('search', params.search);
  if (params?.role) url.searchParams.set('role', params.role);
  if (typeof params?.is_active === 'boolean') url.searchParams.set('is_active', String(params.is_active));
  url.searchParams.set('page', String(params?.page ?? 1));
  url.searchParams.set('page_size', String(params?.page_size ?? 10));
  const res = await apiFetch(url.toString());
  return handleResponse<UserListResponse>(res);
}

export async function createAdminUser(payload: AdminUserCreatePayload): Promise<UserWithTempPasswordResponse> {
  const res = await apiFetch(`${BASE}/api/admin/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<UserWithTempPasswordResponse>(res);
}

export async function updateAdminUser(userId: string, payload: AdminUserUpdatePayload): Promise<UserResponse> {
  const res = await apiFetch(`${BASE}/api/admin/users/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<UserResponse>(res);
}

export async function updateAdminUserStatus(userId: string, payload: AdminUserStatusPayload): Promise<UserResponse> {
  const res = await apiFetch(`${BASE}/api/admin/users/${encodeURIComponent(userId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<UserResponse>(res);
}

export async function resetAdminUserPassword(userId: string): Promise<UserWithTempPasswordResponse> {
  const res = await apiFetch(`${BASE}/api/admin/users/${encodeURIComponent(userId)}/reset-password`, {
    method: 'POST',
  });
  return handleResponse<UserWithTempPasswordResponse>(res);
}

export async function revokeAdminUserSessions(userId: string): Promise<{ status: string; message: string }> {
  const res = await apiFetch(`${BASE}/api/admin/users/${encodeURIComponent(userId)}/revoke-sessions`, {
    method: 'POST',
  });
  return handleResponse<{ status: string; message: string }>(res);
}

export async function deleteAdminUser(userId: string): Promise<{ status: string; message: string }> {
  const res = await apiFetch(`${BASE}/api/admin/users/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  });
  return handleResponse<{ status: string; message: string }>(res);
}

export async function fetchAdminAuditLogs(limit = 50): Promise<AuditLogResponse[]> {
  const url = new URL(`${BASE}/api/admin/users/audit-logs`, window.location.origin);
  url.searchParams.set('limit', String(limit));
  const res = await apiFetch(url.toString());
  return handleResponse<AuditLogResponse[]>(res);
}

// ----------------------------------------------------
// Rooms API
// ----------------------------------------------------

export async function fetchRooms(): Promise<RoomResponse[]> {
  const res = await apiFetch(`${BASE}/api/rooms`);
  return handleResponse<RoomResponse[]>(res);
}

export async function createRoom(payload: RoomCreate): Promise<RoomResponse> {
  const res = await apiFetch(`${BASE}/api/rooms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<RoomResponse>(res);
}

export async function updateRoom(roomId: string, payload: RoomUpdate): Promise<RoomResponse> {
  const res = await apiFetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<RoomResponse>(res);
}

export async function deleteRoom(roomId: string): Promise<{ status: string; room_id: string }> {
  const res = await apiFetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}`, {
    method: 'DELETE',
  });
  return handleResponse<{ status: string; room_id: string }>(res);
}

export async function uploadFloorPlan(roomId: string, file: File): Promise<FloorPlanUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await apiFetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}/floor-plan`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<FloorPlanUploadResponse>(res);
}

export async function fetchRoomMap(roomId: string): Promise<RoomMapResponse> {
  const res = await apiFetch(`${BASE}/api/rooms/${encodeURIComponent(roomId)}/map`);
  return handleResponse<RoomMapResponse>(res);
}

export async function fetchRoomSparklines(range = '6h', maxPoints = 24): Promise<RoomSparklinesResponse> {
  const url = new URL(`${BASE}/api/rooms/sparklines`, window.location.origin);
  url.searchParams.set('range', range);
  url.searchParams.set('max_points', String(maxPoints));
  const res = await apiFetch(url.toString());
  return handleResponse<RoomSparklinesResponse>(res);
}

// ----------------------------------------------------
// Devices & Pairing API
// ----------------------------------------------------

export async function fetchDevices(status?: 'pending' | 'active' | 'all', dev_type?: string): Promise<DeviceResponse[]> {
  const url = new URL(`${BASE}/api/devices`, window.location.origin);
  if (status) {
    url.searchParams.set('status', status);
  }
  if (dev_type) {
    url.searchParams.set('dev_type', dev_type);
  }
  const res = await apiFetch(url.toString());
  return handleResponse<DeviceResponse[]>(res);
}

export async function fetchDevice(devId: string): Promise<DeviceResponse> {
  const res = await apiFetch(`${BASE}/api/devices/${encodeURIComponent(devId)}`);
  return handleResponse<DeviceResponse>(res);
}

export async function pairDevice(devId: string, payload: DevicePairRequest): Promise<DeviceResponse> {
  const res = await apiFetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<DeviceResponse>(res);
}

export async function unpairDevice(devId: string): Promise<{ status: string; dev_id: string; is_active: boolean }> {
  const res = await apiFetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/unpair`, {
    method: 'POST',
  });
  return handleResponse<{ status: string; dev_id: string; is_active: boolean }>(res);
}

export async function updateThresholds(
  devId: string,
  payload: ThresholdUpdateRequest
): Promise<ThresholdConfig> {
  const res = await apiFetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/thresholds`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<ThresholdConfig>(res);
}

export async function sendDeviceCommand(
  devId: string,
  command: DeviceCommand
): Promise<{ status: string; command_id: string }> {
  const res = await apiFetch(`${BASE}/api/devices/${encodeURIComponent(devId)}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
  });
  return handleResponse<{ status: string; command_id: string }>(res);
}

export async function fetchCommandStatus(commandId: string): Promise<CommandStatusResponse> {
  const res = await apiFetch(`${BASE}/api/commands/${encodeURIComponent(commandId)}`);
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

  const res = await apiFetch(url.toString());
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
  const res = await apiFetch(url.toString());
  return handleResponse<DeviceHistoryResponse>(res);
}

// ----------------------------------------------------
// Hubs API
// ----------------------------------------------------

export async function fetchHubs(): Promise<HubResponse[]> {
  const res = await apiFetch(`${BASE}/api/hubs`);
  return handleResponse<HubResponse[]>(res);
}

export async function approveHub(hubId: string): Promise<HubActionResponse> {
  const res = await apiFetch(`${BASE}/api/hubs/${encodeURIComponent(hubId)}/approve`, {
    method: 'POST',
  });
  return handleResponse<HubActionResponse>(res);
}

export async function revokeHub(hubId: string): Promise<HubActionResponse> {
  const res = await apiFetch(`${BASE}/api/hubs/${encodeURIComponent(hubId)}/revoke`, {
    method: 'POST',
  });
  return handleResponse<HubActionResponse>(res);
}

// ----------------------------------------------------
// Schedules API
// ----------------------------------------------------

export async function fetchSchedules(params?: { hub_id?: string; dev_id?: string; enabled?: boolean }): Promise<ScheduleResponse[]> {
  const url = new URL(`${BASE}/api/schedules`, window.location.origin);
  if (params?.hub_id) url.searchParams.set('hub_id', params.hub_id);
  if (params?.dev_id) url.searchParams.set('dev_id', params.dev_id);
  if (typeof params?.enabled === 'boolean') url.searchParams.set('enabled', String(params.enabled));
  const res = await apiFetch(url.toString());
  return handleResponse<ScheduleResponse[]>(res);
}

export async function fetchSchedule(id: string): Promise<ScheduleResponse> {
  const res = await apiFetch(`${BASE}/api/schedules/${encodeURIComponent(id)}`);
  return handleResponse<ScheduleResponse>(res);
}

export async function createSchedule(payload: ScheduleCreate): Promise<ScheduleResponse> {
  const res = await apiFetch(`${BASE}/api/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<ScheduleResponse>(res);
}

export async function updateSchedule(id: string, payload: ScheduleUpdate): Promise<ScheduleResponse> {
  const res = await apiFetch(`${BASE}/api/schedules/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse<ScheduleResponse>(res);
}

export async function deleteSchedule(id: string): Promise<{ status: string; id: string }> {
  const res = await apiFetch(`${BASE}/api/schedules/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  return handleResponse<{ status: string; id: string }>(res);
}

export async function runNowSchedule(id: string): Promise<{ status: string; command_id: string }> {
  const res = await apiFetch(`${BASE}/api/schedules/${encodeURIComponent(id)}/run-now`, {
    method: 'POST',
  });
  return handleResponse<{ status: string; command_id: string }>(res);
}

export async function previewScheduleCron(cronExpr: string, tz?: string): Promise<SchedulePreviewResponse> {
  const url = new URL(`${BASE}/api/schedules/preview`, window.location.origin);
  url.searchParams.set('cron_expr', cronExpr);
  if (tz) url.searchParams.set('tz', tz);
  const res = await apiFetch(url.toString());
  return handleResponse<SchedulePreviewResponse>(res);
}
