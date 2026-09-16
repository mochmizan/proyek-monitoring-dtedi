# server/app/services/activity_logger.py
"""Centralized Activity Logger Service enforcing Role-Based Access Control (RBAC) logging rules.

RBAC Rules:
1. Global (All Roles):
   - Admin, Operator, and Viewer MUST have their 'Login' and 'Logout' activities logged.
2. Admin:
   - Log all configuration changes (rooms, devices, thresholds, hubs, schedules),
     account management (create/update/delete users, password resets),
     device controls, and system adjustments.
3. Operator:
   - Only log device control executions explicitly (e.g., 'Turn on AC', 'Start/Stop Genset').
4. Viewer:
   - Read-only access: DO NOT log any viewing activities. ONLY log 'Login' and 'Logout'.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from modelsv5 import ActivityLog, User

logger = logging.getLogger("activity_logger")

AUTH_ACTIONS = {"login", "logout"}
DEVICE_CONTROL_CATEGORIES = {"device_control"}
ADMIN_ALLOWED_CATEGORIES = {
    "auth",
    "device_control",
    "config",
    "account_management",
    "system_adjustment",
    "general",
}


def should_log_activity(role: Optional[str], action: str, category: str) -> bool:
    """Determine whether an action should be recorded based on RBAC rules."""
    norm_role = (role or "").strip().lower()
    norm_action = action.strip().lower()
    norm_cat = category.strip().lower()

    # Global Rule: Login & Logout are logged for ALL roles
    if norm_action in AUTH_ACTIONS or norm_cat == "auth":
        return True

    # Viewer: Never log non-auth actions
    if norm_role == "viewer":
        return False

    # Operator: Only log device control executions
    if norm_role == "operator":
        return norm_cat in DEVICE_CONTROL_CATEGORIES

    # Admin: Log configuration changes, account management, device controls, system adjustments
    if norm_role == "admin":
        return norm_cat in ADMIN_ALLOWED_CATEGORIES

    # Default fallback: allow if not viewer and belongs to recognized categories
    return norm_cat in DEVICE_CONTROL_CATEGORIES


def log_user_activity(
    db: Session,
    user: Optional[User] = None,
    user_name: Optional[str] = None,
    role: Optional[str] = None,
    user_id: Optional[str] = None,
    action: str = "",
    details: Optional[dict[str, Any]] = None,
    category: str = "general",
    status_str: str = "success",
    request: Optional[Request] = None,
    commit: bool = True,
) -> Optional[ActivityLog]:
    """Record a user activity log entry if permitted by RBAC rules."""
    # Resolve user details
    resolved_username = user.username if user else (user_name or "unknown")
    resolved_role = user.role if user else (role or "unknown")
    resolved_user_id = user.id if user else user_id

    # Check RBAC logging policy
    if not should_log_activity(resolved_role, action, category):
        return None

    # Resolve client IP
    ip_addr = None
    if request:
        if request.headers.get("x-real-ip"):
            ip_addr = request.headers.get("x-real-ip")
        elif request.headers.get("x-forwarded-for"):
            ip_addr = request.headers.get("x-forwarded-for").split(",")[0].strip()
        elif request.client:
            ip_addr = request.client.host

    activity_payload = {
        "action": action,
        "details": details or {},
        "category": category,
        "status": status_str,
    }
    if ip_addr:
        activity_payload["ip_address"] = ip_addr

    log_entry = ActivityLog(
        id=str(uuid.uuid4()),
        user_name=resolved_username,
        user_id=resolved_user_id,
        role=resolved_role,
        activity=activity_payload,
        created_at=datetime.now(UTC),
    )

    try:
        db.add(log_entry)
        if commit:
            db.commit()
    except Exception as exc:
        logger.error(f"Failed to save activity log: {exc}")
        if commit:
            db.rollback()
        raise

    return log_entry
