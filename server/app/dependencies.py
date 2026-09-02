# app/dependencies.py — shared FastAPI dependencies
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import secrets
import threading
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from databasev5 import get_db
from modelsv5 import hub_table


@dataclass
class HubCacheEntry:
    hub_name: str
    hub_key: str
    is_active: bool
    last_db_persist_ts: float  # monotonic epoch


class HubAuthCache:
    """In-memory thread-safe throttled hub authentication and heartbeat cache.
    Features a lock-free read path for high throughput:
    Cached entries are read without acquiring a lock; the mutex is acquired only
    during cache miss population, timestamp update, or cache invalidation."""

    def __init__(self, throttle_seconds: float = 30.0):
        self.throttle_seconds = throttle_seconds
        self._cache: dict[str, HubCacheEntry] = {}
        self._lock = threading.Lock()

    def get_or_load(self, hub_id: str, db: Session) -> Optional[HubCacheEntry]:
        """Retrieve entry from memory cache (lock-free read path).
        On cache miss, acquires lock and queries the database."""
        # 1. Lock-free read path
        entry = self._cache.get(hub_id)
        if entry is not None:
            return entry

        # 2. Cache miss: Double-checked locking
        with self._lock:
            entry = self._cache.get(hub_id)
            if entry is not None:
                return entry

            hub = db.get(hub_table, hub_id)
            if not hub:
                return None

            entry = HubCacheEntry(
                hub_name=hub.hub_name or "",
                hub_key=hub.hub_key or "",
                is_active=bool(hub.is_active),
                last_db_persist_ts=0.0,  # 0.0 ensures first request qualifies for DB persist
            )
            self._cache[hub_id] = entry
            return entry

    def should_persist_heartbeat(self, hub_id: str) -> bool:
        """Determines if the hub's heartbeat should be staged to the database.
        Returns True and updates last_db_persist_ts if >= throttle_seconds have elapsed.
        Lock-free fast-path return False when throttle period has not elapsed."""
        entry = self._cache.get(hub_id)
        if entry is None:
            return True

        now = time.monotonic()
        # Fast lock-free check
        if now - entry.last_db_persist_ts < self.throttle_seconds:
            return False

        # Acquire lock to update timestamp atomically
        with self._lock:
            if now - entry.last_db_persist_ts >= self.throttle_seconds:
                entry.last_db_persist_ts = now
                return True
            return False

    def invalidate(self, hub_id: str) -> None:
        """Evict entry from memory cache on state transitions."""
        with self._lock:
            self._cache.pop(hub_id, None)

    def clear(self) -> None:
        """Clear entire cache (used for test teardown and resets)."""
        with self._lock:
            self._cache.clear()


hub_auth_cache = HubAuthCache(throttle_seconds=30.0)


def stage_hub_heartbeat(hub: hub_table) -> bool:
    """Helper to stage last_seen and status='online' on the hub ORM instance
    if the throttle window has elapsed. Does NOT commit to the DB session."""
    if hub_auth_cache.should_persist_heartbeat(hub.hub_id):
        hub.last_seen = datetime.now(UTC)
        hub.status = "online"
        return True
    return False


def verify_hub_identity(
    x_hub_id: str = Header(..., alias="X-Hub-ID"),
    x_hub_key: str = Header(..., alias="X-Hub-Key"),
    db: Session = Depends(get_db),
) -> hub_table:
    """[V5] Verifies hub credentials using HubAuthCache and stages heartbeat without committing.
    Eliminates auth double-commit (CRIT-01): Telemetry and heartbeat commit atomically in endpoint handlers."""
    entry = hub_auth_cache.get_or_load(x_hub_id, db)
    if not entry or not entry.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!",
        )

    if not secrets.compare_digest(entry.hub_key, x_hub_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: API Key Hub tidak cocok!",
        )

    hub = db.get(hub_table, x_hub_id)
    if not hub or not hub.is_active:
        hub_auth_cache.invalidate(x_hub_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!",
        )

    # Throttled heartbeat staging: updates hub.last_seen if >= 30s elapsed
    # Zero db.commit() calls here (CRIT-01 fix)!
    stage_hub_heartbeat(hub)

    return hub
