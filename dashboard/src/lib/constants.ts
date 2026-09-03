// Polling Frequencies (ms)
export const POLL_FAST_MS = 3000;              // High-frequency live view polling (rooms, devices, alerts)
export const POLL_ALERTS_BADGE_MS = 5000;       // Bell badge unread alert polling in root header
export const POLL_HISTORY_REALTIME_MS = 15000;  // Telemetry chart polling for 6h/24h views
export const POLL_SPARKLINES_MS = 30000;        // Room sparkline envelope two-pass CTE aggregation
export const POLL_COMMAND_STATUS_MS = 1500;     // Hardware downlink command delivery polling

// Cache Stale Times (ms)
export const STALE_TELEMETRY_MS = 10000;        // Live telemetry cache validity
export const STALE_SPARKLINES_MS = 25000;       // Sparkline cache validity
export const STALE_METADATA_MS = 60000;         // Static device metadata & threshold config
export const STALE_USER_MS = 60000;             // Current user profile cache

// Command Lifecycle Timeouts (ms)
export const COMMAND_DELIVERY_TIMEOUT_MS = 12000; // Radio downlink ACK wait ceiling
export const COMMAND_AUTO_DISMISS_MS = 8000;       // Success badge banner dismissal

// Telemetry Gap Thresholds (minutes)
export const GAP_FLOOR_MIN = 5;                 // Minimum gap duration before rendering outage hatch

// Backwards compatibility aliases
export const POLL_MS = POLL_FAST_MS;
export const POLL_ALERTS_MS = POLL_ALERTS_BADGE_MS;
export const STALE_MS = STALE_TELEMETRY_MS;
