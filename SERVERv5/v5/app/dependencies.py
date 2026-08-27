# app/dependencies.py — shared FastAPI dependencies
import secrets
from datetime import UTC, datetime
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from databasev5 import get_db
from modelsv5 import hub_table


def verify_hub_identity(
    x_hub_id: str = Header(..., alias="X-Hub-ID"),
    x_hub_key: str = Header(..., alias="X-Hub-Key"),
    db: Session = Depends(get_db),
):
    """[V5] Memverifikasi Keabsahan Hub Pengirim via Database PostgreSQL."""
    registered_hub = db.get(hub_table, x_hub_id)

    if not registered_hub or not registered_hub.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: Hub tidak terdaftar atau non-aktif!",
        )

    registered_hub_key = registered_hub.hub_key or ""
    if not secrets.compare_digest(registered_hub_key, x_hub_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akses Ditolak: API Key Hub tidak cocok!",
        )

    # [V5 PRESENCE] Perbarui heartbeat terakhir Hub pada setiap permintaan berhasil
    registered_hub.last_seen = datetime.now(UTC)
    db.commit()

    return registered_hub
