# app/services/alert_engine.py — threshold evaluation extracted from hubgatev5.py
import uuid
from datetime import UTC, datetime
from sqlalchemy.orm import Session

# imports are lazy inside function to avoid circular deps at module load,
# but top-level imports for types are also okay since modelsv5 does not import this module
from modelsv5 import device_threshold_config, event_log


def evaluate_device_thresholds(
    db: Session,
    dev,
    payload: dict,
    timestamp: datetime,
) -> None:
    """
    [V5 Milestone 4] Synchronously evaluates threshold rules for incoming telemetry.
    Supports temperature threshold evaluation with debouncing and hysteresis recovery,
    and ATS emergency alert evaluation.
    """
    now_ts = timestamp or datetime.now(UTC)

    # 1. Temperature Evaluation (TS, AC, or any device reporting TEMP)
    if "TEMP" in payload and payload["TEMP"] is not None:
        try:
            temp = float(payload["TEMP"])
        except (ValueError, TypeError):
            temp = None

        if temp is not None:
            thresh = db.get(device_threshold_config, dev.dev_id)
            if thresh:
                warning = float(thresh.warning)
                critical = float(thresh.critical)
                hysteresis = float(thresh.hysteresis) if thresh.hysteresis is not None else 0.5
                debounce_seconds = int(thresh.debounce_seconds) if thresh.debounce_seconds is not None else 60
            else:
                warning = 28.0
                critical = 32.0
                hysteresis = 0.5
                debounce_seconds = 60

            severity = None
            threshold_val = None
            if temp >= critical:
                severity = "critical"
                threshold_val = critical
            elif temp >= warning:
                severity = "warning"
                threshold_val = warning

            if severity is not None:
                recent_alert = (
                    db.query(event_log)
                    .filter(
                        event_log.dev_id == dev.dev_id,
                        event_log.metric == "temperature",
                    )
                    .order_by(event_log.timestamp.desc())
                    .first()
                )

                suppress = False
                if recent_alert and recent_alert.timestamp:
                    t_recent = recent_alert.timestamp
                    t_curr = now_ts
                    if t_curr.tzinfo is not None and t_recent.tzinfo is None:
                        t_recent = t_recent.replace(tzinfo=UTC)
                    elif t_curr.tzinfo is None and t_recent.tzinfo is not None:
                        t_curr = t_curr.replace(tzinfo=UTC)

                    elapsed = abs((t_curr - t_recent).total_seconds())
                    if elapsed < debounce_seconds:
                        if recent_alert.severity == severity:
                            suppress = True
                        elif recent_alert.severity == "critical" and severity == "warning":
                            suppress = True

                if not suppress:
                    alarm_code = f"TEMP_{severity.upper()}"
                    dev_label = dev.dev_name or dev.dev_id
                    message = f"Device {dev_label} temperature {temp:.1f}°C exceeded {severity} threshold ({threshold_val:.1f}°C)"
                    new_alert = event_log(
                        event_id=uuid.uuid4().hex,
                        alarm=alarm_code,
                        timestamp=now_ts,
                        message=message,
                        dev_id=dev.dev_id,
                        room_id=dev.room_id,
                        metric="temperature",
                        severity=severity,
                        value=temp,
                        threshold=threshold_val,
                        resolved_at=None,
                    )
                    db.add(new_alert)

            # Hysteresis Recovery
            if temp < (warning - hysteresis):
                open_alerts = (
                    db.query(event_log)
                    .filter(
                        event_log.dev_id == dev.dev_id,
                        event_log.metric == "temperature",
                        event_log.resolved_at.is_(None),
                    )
                    .all()
                )
                for alert in open_alerts:
                    alert.resolved_at = now_ts

    # 2. ATS Emergency Evaluation
    if "EMERGENCY" in payload and payload["EMERGENCY"] is not None:
        is_emergency = bool(payload["EMERGENCY"])
        if is_emergency:
            thresh = db.get(device_threshold_config, dev.dev_id)
            debounce_seconds = int(thresh.debounce_seconds) if thresh and thresh.debounce_seconds is not None else 60

            recent_alert = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == dev.dev_id,
                    event_log.metric == "emergency",
                )
                .order_by(event_log.timestamp.desc())
                .first()
            )

            suppress = False
            if recent_alert and recent_alert.timestamp:
                t_recent = recent_alert.timestamp
                t_curr = now_ts
                if t_curr.tzinfo is not None and t_recent.tzinfo is None:
                    t_recent = t_recent.replace(tzinfo=UTC)
                elif t_curr.tzinfo is None and t_recent.tzinfo is not None:
                    t_curr = t_curr.replace(tzinfo=UTC)

                elapsed = abs((t_curr - t_recent).total_seconds())
                if elapsed < debounce_seconds and recent_alert.severity == "critical":
                    suppress = True

            if not suppress:
                dev_label = dev.dev_name or dev.dev_id
                new_alert = event_log(
                    event_id=uuid.uuid4().hex,
                    alarm="ATS_EMERGENCY",
                    timestamp=now_ts,
                    message=f"Device {dev_label} reported EMERGENCY state",
                    dev_id=dev.dev_id,
                    room_id=dev.room_id,
                    metric="emergency",
                    severity="critical",
                    value=1.0,
                    threshold=1.0,
                    resolved_at=None,
                )
                db.add(new_alert)
        else:
            open_alerts = (
                db.query(event_log)
                .filter(
                    event_log.dev_id == dev.dev_id,
                    event_log.metric == "emergency",
                    event_log.resolved_at.is_(None),
                )
                .all()
            )
            for alert in open_alerts:
                alert.resolved_at = now_ts
