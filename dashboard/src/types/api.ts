export type UserRole = 'admin' | 'operator' | 'viewer';

export interface UserResponse {
  username: string;
  display_name: string;
  role: UserRole;
}

export interface UserLoginPayload {
  username: string;
  password: string;
}

export interface RoomResponse {
  id: string;
  name: string;
  hub_id?: string | null;
  floor_plan_image_path?: string | null;
  device_count: number;
  created_at?: string | null;
}

export interface RoomCreate {
  name: string;
  hub_id?: string | null;
  floor_plan_image_path?: string | null;
}

export interface RoomUpdate {
  name?: string | null;
  hub_id?: string | null;
  floor_plan_image_path?: string | null;
}

export interface FloorPlanUploadResponse {
  room_id: string;
  floor_plan_url: string;
  message: string;
}

export interface ThresholdConfig {
  warning: number;
  critical: number;
  hysteresis: number;
  debounce_seconds: number;
}

export interface ThresholdUpdateRequest {
  warning: number;
  critical: number;
  hysteresis?: number;
  debounce_seconds?: number;
}

export interface DeviceResponse {
  dev_id: string;
  dev_name?: string | null;
  dev_type?: string | null;
  hub_id?: string | null;
  is_active: boolean;
  status?: 'online' | 'offline' | 'pending';
  last_seen?: string | null;
  room_id?: string | null;
  marker_x?: number | null;
  marker_y?: number | null;
  created_at?: string | null;
  threshold_config?: ThresholdConfig | null;
}

export interface DevicePairRequest {
  dev_name: string;
  room_id: string;
  marker_x?: number | null;
  marker_y?: number | null;
  warning_threshold?: number | null;
  critical_threshold?: number | null;
  hysteresis?: number | null;
  debounce_seconds?: number | null;
}

export interface ATSCommand {
  mode?: 'auto' | 'manual';
  start_genset?: 'on' | 'off';
  reset?: 'rst';
}

export interface ACCommand {
  target: 'AC1' | 'AC2';
  action: 'ON' | 'OFF' | 'SET_TEMP';
  temp?: number;
}

export type DeviceCommand = ATSCommand | ACCommand | Record<string, unknown>;

export interface CommandStatusResponse {
  command_id: string;
  dev_id: string;
  hub_id: string;
  payload: Record<string, unknown>;
  status: string;
  created_at?: string | null;
  delivered_at?: string | null;
}

export interface RoomMapMarker {
  dev_id: string;
  dev_name?: string | null;
  dev_type?: string | null;
  marker_x?: number | null;
  marker_y?: number | null;
  is_active: boolean;
  status?: string | null;
  latest_reading?: Record<string, unknown> | null;
}

export interface RoomMapResponse {
  room_id: string;
  room_name: string;
  has_image: boolean;
  floor_plan_url?: string | null;
  devices: RoomMapMarker[];
}

export interface AlertResponse {
  event_id: string;
  dev_id?: string | null;
  dev_name?: string | null;
  room_id?: string | null;
  room_name?: string | null;
  metric?: string | null;
  severity?: 'warning' | 'critical' | string | null;
  value?: number | null;
  threshold?: number | null;
  timestamp: string;
  resolved_at?: string | null;
  message?: string | null;
}

export interface AlertListResponse {
  total: number;
  alerts: AlertResponse[];
}

export interface AlertFilterParams {
  rooms?: string[];
  room?: string;
  devices?: string[];
  device?: string;
  severity?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
  offset?: number;
}

export interface TelemetryHistoryPoint {
  timestamp: string;
  temp?: number | null;
  humid?: number | null;
  pln?: number | null;
  genset?: number | null;
  aki?: number | null;
  state?: string | null;
}

export interface DeviceHistoryResponse {
  dev_id: string;
  dev_type: string;
  range: string;
  total_points: number;
  points: TelemetryHistoryPoint[];
}

export interface HubDeviceSummary {
  dev_id: string;
  dev_name?: string | null;
  dev_type?: string | null;
  last_seen?: string | null;
}

export interface HubResponse {
  hub_id: string;
  hub_name: string;
  room?: string | null;
  status: 'online' | 'offline';
  last_seen?: string | null;
  device_count: number;
  devices: HubDeviceSummary[];
}

export interface HubActionResponse {
  status: string;
  hub_id: string;
}

export interface ScheduleResponse {
  id: string;
  dev_id: string;
  hub_id?: string | null;
  cron_expr: string;
  payload: Record<string, unknown>;
  tz: string;
  enabled: boolean;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  next_run_at?: string | null;
  human?: string | null;
}

export interface ScheduleCreate {
  dev_id: string;
  hub_id?: string | null;
  cron_expr: string;
  payload: Record<string, unknown>;
  tz?: string;
  enabled?: boolean;
}

export interface ScheduleUpdate {
  dev_id?: string | null;
  hub_id?: string | null;
  cron_expr?: string | null;
  payload?: Record<string, unknown> | null;
  tz?: string | null;
  enabled?: boolean | null;
}

export interface SchedulePreviewResponse {
  cron_expr: string;
  valid: boolean;
  human?: string | null;
  next_runs?: string[] | null;
  error?: string | null;
}

