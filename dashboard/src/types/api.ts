export type UserRole = 'root' | 'admin' | 'operator' | 'viewer';

export interface UserClusterMembershipInfo {
  cluster_id: string;
  cluster_name: string;
  role: string;
}

// Bentuk asli sesuai schemas_auth.py (UserResponse kedua, yang dipakai
// login/me/admin — Python override class pertama yang cuma 3 field).
export interface UserResponse {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  must_change_password: boolean;
  is_online: boolean;
  last_login_at?: string | null;
  created_at: string;
  updated_at?: string | null;
  cluster_memberships?: UserClusterMembershipInfo[];
}

export interface UserWithTempPasswordResponse extends UserResponse {
  temp_password: string;
}

export interface UserListResponse {
  items: UserResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserLoginPayload {
  username: string;
  password: string;
}

export interface ChangePasswordPayload {
  old_password: string;
  new_password: string;
}

// Payload admin — persis schemas_auth.py: UserCreate, UserUpdate, UserStatusUpdate
export interface AdminUserCreatePayload {
  username: string;
  display_name: string;
  role: UserRole;
  temp_password?: string;
  cluster_id?: string;
  cluster_role?: 'admin' | 'operator' | 'viewer';
}

export interface AdminUserUpdatePayload {
  display_name?: string;
  role?: UserRole;
}

export interface AdminUserStatusPayload {
  is_active: boolean;
}

export interface AdminUserListParams {
  search?: string;
  role?: UserRole;
  cluster_id?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}

export interface AuditLogResponse {
  id: string;
  actor_id: string | null;
  action: string;
  target_user_id: string | null;
  status: string;
  ip_address: string | null;
  details: string | null;
  timestamp: string;
}

export interface ActivityDetails {
  [key: string]: unknown;
}

export interface ActivityLogItem {
  id: string;
  user_name: string;
  user_id: string | null;
  role: UserRole | string;
  activity: {
    action: string;
    category: string;
    details: ActivityDetails;
    status: string;
    ip_address?: string | null;
  };
  created_at: string;
}

export interface ActivityLogsResponse {
  items: ActivityLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ActivityLogsParams {
  page?: number;
  limit?: number;
  username?: string;
  role?: string;
}

export interface RoomResponse {
  id: string;
  name: string;
  hub_id?: string | null;
  floor_plan_image_path?: string | null;
  device_count: number;
  created_at?: string | null;
  cluster_id?: string | null;
  cluster_name?: string | null;
}

export interface RoomCreate {
  name: string;
  hub_id?: string | null;
  floor_plan_image_path?: string | null;
  cluster_id?: string | null;
}

export interface RoomUpdate {
  name?: string | null;
  hub_id?: string | null;
  floor_plan_image_path?: string | null;
  cluster_id?: string | null;
}

export interface FloorPlanUploadResponse {
  room_id: string;
  floor_plan_url: string;
  message: string;
}

export interface RoomSparklinePoint {
  timestamp: string;
  temp: number | null;
  humid: number | null;
}

export type RoomSparklinesResponse = Record<string, { points: RoomSparklinePoint[] }>;

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
  latest_reading?: Record<string, any> | null;
  cluster_id?: string | null;
  cluster_name?: string | null;
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
  cluster_id?: string | null;
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
  latest_reading?: Record<string, any> | null;
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
  cluster_id?: string;
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
  temp_min?: number | null;
  temp_max?: number | null;
  humid_min?: number | null;
  humid_max?: number | null;
  pln_min?: number | null;
  pln_max?: number | null;
  genset_min?: number | null;
  genset_max?: number | null;
  aki_min?: number | null;
  aki_max?: number | null;
}

export interface DeviceHistoryResponse {
  dev_id: string;
  dev_type: string;
  range: string;
  total_points: number;
  points: TelemetryHistoryPoint[];
  bucket_seconds?: number | null;
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
  is_active?: boolean;
  last_seen?: string | null;
  device_count: number;
  devices: HubDeviceSummary[];
}

export interface HubActionResponse {
  status: string;
  hub_id: string;
  hub_key?: string;
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

// ==========================================
// CLUSTERS & MEMBERSHIPS (Multi-Cluster System)
// ==========================================

export interface Cluster {
  id: string;
  name: string;
  description?: string | null;
  location?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
  created_by?: string | null;
  device_count: number;
  room_count: number;
  member_count: number;
}

export interface ClusterDetail extends Cluster {
  members: Membership[];
  devices: DeviceResponse[];
  rooms: RoomResponse[];
  permissions: Record<string, Record<string, boolean>>;
}

export interface ClusterListResponse {
  items: Cluster[];
  total: number;
  page: number;
  page_size: number;
}

export interface ClusterCreatePayload {
  name: string;
  description?: string;
  location?: string;
}

export interface ClusterUpdatePayload {
  name?: string;
  description?: string;
  location?: string;
  is_active?: boolean;
}

export interface Membership {
  id: string;
  user_id: string;
  username?: string;
  display_name?: string;
  cluster_id: string;
  cluster_name?: string;
  role: 'admin' | 'operator' | 'viewer';
  created_at: string;
}

export interface MembershipCreatePayload {
  user_id: string;
  cluster_id: string;
  role: 'admin' | 'operator' | 'viewer';
}

export interface MembershipUpdatePayload {
  role: 'admin' | 'operator' | 'viewer';
}

export interface ClusterPermissionMatrix {
  cluster_id: string;
  permissions: Record<string, Record<string, boolean>>;
}


