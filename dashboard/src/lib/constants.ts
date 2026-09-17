// 4-Tier Polling Frequencies (ms)
export const POLL_TIER1_COMMAND_MS = 1500;     // Tier 1: Hardware downlink command delivery polling (Fixed, no jitter)
export const POLL_TIER2_ALERTS_MS = 6000;       // Tier 2: Alerts & Critical Status (+/- 15% jitter)
export const POLL_TIER3_PRESENCE_MS = 15000;    // Tier 3: Operational Presence & Metadata (+/- 15% jitter)
export const POLL_TIER4_TRENDS_MS = 60000;      // Tier 4: Analytical Trends & Sparklines (+/- 15% jitter)

// Matching Cache Stale Times (ms) - Enforces staleTime >= refetchInterval
export const STALE_TIER1_COMMAND_MS = 0;        // Tier 1: Real-time ephemeral commands
export const STALE_TIER2_ALERTS_MS = 6000;      // Tier 2: Alerts & telemetry cache validity
export const STALE_TIER3_PRESENCE_MS = 15000;   // Tier 3: Devices & hubs presence cache validity
export const STALE_TIER4_TRENDS_MS = 60000;     // Tier 4: Sparkline & trend envelope validity
export const STALE_METADATA_MS = 300000;        // Static reference configuration & rooms metadata (5 minutes)
export const STALE_USER_MS = 60000;             // Current user profile cache (1 minute)

// Command Lifecycle Timeouts (ms)
export const COMMAND_DELIVERY_TIMEOUT_MS = 12000; // Radio downlink ACK wait ceiling
export const COMMAND_AUTO_DISMISS_MS = 8000;       // Success badge banner dismissal

// Telemetry Gap Thresholds (minutes)
export const GAP_FLOOR_MIN = 5;                 // Minimum gap duration before rendering outage hatch (legacy fallback)

// Type-aware gap threshold minimums (minutes) before rendering outage hatch/break
export const GAP_FLOOR_BY_TYPE_MIN: Record<string, number> = {
  ATS: 3,
  AC: 6,
  ACC: 6,
  TS: 15,
  DEFAULT: 3,
};

// Nominal reporting cadence metadata for UI display & telemetry expectations
export interface CadenceMetadata {
  label: string;
  intervalSec: number;
}

export const CADENCE_BY_TYPE: Record<string, CadenceMetadata> = {
  ATS: { label: '1m RBE', intervalSec: 60 },
  TS: { label: '5m RBE', intervalSec: 300 },
  AC: { label: '2m RBE', intervalSec: 120 },
  ACC: { label: '2m RBE', intervalSec: 120 },
  DEFAULT: { label: '1m RBE', intervalSec: 60 },
};

// Backwards compatibility aliases mapped to new tiered constants
export const POLL_COMMAND_STATUS_MS = POLL_TIER1_COMMAND_MS;
export const POLL_FAST_MS = POLL_TIER2_ALERTS_MS;
export const POLL_ALERTS_BADGE_MS = POLL_TIER2_ALERTS_MS;
export const POLL_HISTORY_REALTIME_MS = POLL_TIER3_PRESENCE_MS;
export const POLL_SPARKLINES_MS = POLL_TIER4_TRENDS_MS;
export const POLL_MS = POLL_TIER2_ALERTS_MS;
export const POLL_ALERTS_MS = POLL_TIER2_ALERTS_MS;
export const STALE_TELEMETRY_MS = STALE_TIER2_ALERTS_MS;
export const STALE_SPARKLINES_MS = STALE_TIER4_TRENDS_MS;
export const STALE_MS = STALE_TIER2_ALERTS_MS;
