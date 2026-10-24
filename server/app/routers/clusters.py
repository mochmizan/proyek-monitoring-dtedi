# app/routers/clusters.py
# CRUD untuk Cluster (Lokasi/Tempat) — hanya Root yang dapat mengaksesnya
import uuid
from typing import Optional, List
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from databasev5 import get_db
from modelsv5 import (
    Cluster, UserClusterMembership, ClusterRolePermission,
    User, dev_table, rooms
)
from auth import require_root, get_current_user, check_cluster_permission, DEFAULT_PERMISSIONS
from app.core.csrf import validate_csrf_request
from app.services.activity_logger import log_user_activity
from schemas_auth import (
    ClusterCreate, ClusterUpdate, ClusterResponse, ClusterListResponse,
    ClusterDetailResponse, ClusterPermissionMatrix, ClusterRolePermissionUpdate,
    ClusterRoomCreate, ClusterRoomUpdate, ClusterDeviceUpdate, MembershipResponse,
)

router = APIRouter(
    prefix="/api/clusters",
    tags=["clusters"],
    dependencies=[Depends(validate_csrf_request)],
)

# ─── HELPERS ────────────────────────────────────────────────────────────────

def _cluster_to_response(cluster: Cluster, db: Session) -> ClusterResponse:
    cluster_devices = db.query(dev_table).filter(dev_table.cluster_id == cluster.id).order_by(dev_table.dev_name).all()
    cluster_rooms = db.query(rooms).filter(rooms.cluster_id == cluster.id).order_by(rooms.name).all()
    member_count = db.query(UserClusterMembership).filter(
        UserClusterMembership.cluster_id == cluster.id
    ).count()

    room_list = [
        {
            "id": r.id,
            "name": r.name,
            "device_count": db.query(dev_table).filter(dev_table.room_id == r.id).count(),
        }
        for r in cluster_rooms
    ]
    device_list = [
        {
            "dev_id": d.dev_id,
            "dev_name": d.dev_name or d.dev_id,
            "dev_type": d.dev_type,
            "is_active": d.is_active,
            "room_id": d.room_id,
            "room_name": d.room.name if d.room else None,
        }
        for d in cluster_devices
    ]

    return ClusterResponse(
        id=cluster.id,
        name=cluster.name,
        description=cluster.description,
        location=cluster.location,
        is_active=cluster.is_active,
        created_at=cluster.created_at,
        updated_at=cluster.updated_at,
        created_by=cluster.created_by,
        device_count=len(cluster_devices),
        room_count=len(cluster_rooms),
        member_count=member_count,
        rooms=room_list,
        devices=device_list,
    )


def _get_effective_permissions(cluster_id: str, db: Session) -> dict:
    """Return merged permission matrix: defaults overridden by explicit DB rows."""
    import copy
    effective = copy.deepcopy(DEFAULT_PERMISSIONS)
    rows = db.query(ClusterRolePermission).filter(
        ClusterRolePermission.cluster_id == cluster_id
    ).all()
    for row in rows:
        if row.role in effective:
            effective[row.role][row.permission] = row.granted
    return effective


# ─── ENDPOINTS (ROOT ONLY) ───────────────────────────────────────────────────

@router.get("", response_model=ClusterListResponse)
def list_clusters(
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] List all clusters with pagination."""
    q = db.query(Cluster)
    if search:
        term = f"%{search.strip().lower()}%"
        q = q.filter(or_(
            func.lower(Cluster.name).like(term),
            func.lower(Cluster.description).like(term),
            func.lower(Cluster.location).like(term),
        ))
    if is_active is not None:
        q = q.filter(Cluster.is_active == is_active)

    total = q.count()
    clusters = q.order_by(Cluster.name).offset((page - 1) * page_size).limit(page_size).all()
    items = [_cluster_to_response(c, db) for c in clusters]
    return ClusterListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ClusterResponse, status_code=status.HTTP_201_CREATED)
def create_cluster(
    req: ClusterCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Create a new cluster/location."""
    existing = db.query(Cluster).filter(func.lower(Cluster.name) == req.name.strip().lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama cluster sudah digunakan")

    now = datetime.now(UTC)
    cluster = Cluster(
        id=str(uuid.uuid4()),
        name=req.name.strip(),
        description=req.description,
        location=req.location,
        is_active=True,
        created_at=now,
        updated_at=now,
        created_by=current_user.id,
    )
    db.add(cluster)
    db.flush()

    log_user_activity(
        db, user=current_user,
        action="Membuat cluster baru",
        category="cluster_management",
        details={"cluster_id": cluster.id, "name": cluster.name},
        request=request,
        commit=False,
    )
    db.commit()
    db.refresh(cluster)
    return _cluster_to_response(cluster, db)


@router.get("/my-clusters", response_model=List[ClusterResponse])
def get_my_clusters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns clusters accessible to the current user (root = all, member = own clusters)."""
    if current_user.role == "root":
        clusters = db.query(Cluster).filter(Cluster.is_active == True).order_by(Cluster.name).all()
    else:
        memberships = db.query(UserClusterMembership).filter(
            UserClusterMembership.user_id == current_user.id
        ).all()
        cluster_ids = [m.cluster_id for m in memberships]
        clusters = db.query(Cluster).filter(
            Cluster.id.in_(cluster_ids),
            Cluster.is_active == True,
        ).order_by(Cluster.name).all()
    return [_cluster_to_response(c, db) for c in clusters]


@router.get("/unassigned-resources")
def get_unassigned_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Get list of rooms and devices not assigned to any cluster."""
    unassigned_rooms = db.query(rooms).filter(rooms.cluster_id == None).order_by(rooms.name).all()  # noqa: E711
    unassigned_devices = db.query(dev_table).filter(dev_table.cluster_id == None).order_by(dev_table.dev_name).all()  # noqa: E711

    return {
        "rooms": [{"id": r.id, "name": r.name} for r in unassigned_rooms],
        "devices": [
            {
                "dev_id": d.dev_id,
                "dev_name": d.dev_name or d.dev_id,
                "dev_type": d.dev_type,
                "is_active": d.is_active,
            }
            for d in unassigned_devices
        ]
    }


@router.get("/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get cluster detail. Root sees all; members see only their clusters."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")

    if current_user.role != "root":
        membership = db.query(UserClusterMembership).filter(
            UserClusterMembership.user_id == current_user.id,
            UserClusterMembership.cluster_id == cluster_id,
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Akses ditolak ke cluster ini")

    # Build detail with devices, rooms, members
    members = db.query(UserClusterMembership).filter(
        UserClusterMembership.cluster_id == cluster_id
    ).all()
    member_list = []
    for m in members:
        u = db.get(User, m.user_id)
        if u:
            member_list.append({
                "user_id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": m.role,
                "is_active": u.is_active,
            })

    devices = db.query(dev_table).filter(dev_table.cluster_id == cluster_id).all()
    device_list = [{"dev_id": d.dev_id, "dev_name": d.dev_name, "dev_type": d.dev_type, "is_active": d.is_active} for d in devices]

    room_list_q = db.query(rooms).filter(rooms.cluster_id == cluster_id).all()
    room_list = [{"id": r.id, "name": r.name} for r in room_list_q]

    permissions = _get_effective_permissions(cluster_id, db)

    base = _cluster_to_response(cluster, db)
    base_data = base.model_dump()
    base_data.update(
        members=member_list,
        devices=device_list,
        rooms=room_list,
        permissions=permissions,
    )
    return ClusterDetailResponse(**base_data)


@router.get("/{cluster_id}/members", response_model=List[MembershipResponse])
def get_cluster_members(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Get list of members in a cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")
    memberships = db.query(UserClusterMembership).filter(
        UserClusterMembership.cluster_id == cluster_id
    ).all()
    from app.routers.memberships import _membership_to_response
    return [_membership_to_response(m, db) for m in memberships]


@router.patch("/{cluster_id}", response_model=ClusterResponse)
def update_cluster(
    cluster_id: str,
    req: ClusterUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Update cluster info."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")

    if req.name is not None:
        name_lower = req.name.strip().lower()
        duplicate = db.query(Cluster).filter(
            func.lower(Cluster.name) == name_lower,
            Cluster.id != cluster_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="Nama cluster sudah digunakan")
        cluster.name = req.name.strip()

    if req.description is not None:
        cluster.description = req.description
    if req.location is not None:
        cluster.location = req.location
    if req.is_active is not None:
        cluster.is_active = req.is_active

    cluster.updated_at = datetime.now(UTC)
    log_user_activity(
        db, user=current_user,
        action="Mengubah cluster",
        category="cluster_management",
        details={"cluster_id": cluster_id},
        request=request,
        commit=False,
    )
    db.commit()
    db.refresh(cluster)
    return _cluster_to_response(cluster, db)


@router.delete("/{cluster_id}", status_code=status.HTTP_200_OK)
def delete_cluster(
    cluster_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Delete an empty cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")

    device_count = db.query(dev_table).filter(dev_table.cluster_id == cluster_id).count()
    if device_count > 0:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus cluster yang masih memiliki perangkat")
    room_count = db.query(rooms).filter(rooms.cluster_id == cluster_id).count()
    if room_count > 0:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus cluster yang masih memiliki ruangan")

    cluster_name = cluster.name
    db.delete(cluster)
    log_user_activity(
        db, user=current_user,
        action="Menghapus cluster",
        category="cluster_management",
        details={"cluster_id": cluster_id, "name": cluster_name},
        request=request,
        commit=False,
    )
    db.commit()
    return {"status": "ok", "message": f"Cluster '{cluster_name}' berhasil dihapus"}


@router.post("/{cluster_id}/assign-device")
def assign_device_to_cluster(
    cluster_id: str,
    request: Request,
    dev_id: str = Query(..., description="Device ID to assign"),
    room_id: Optional[str] = Query(None, description="Optional room ID within the cluster"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Assign a device/sensor to a cluster, optionally into a room."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")
    device = db.get(dev_table, dev_id)
    if not device:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan")

    device.cluster_id = cluster_id
    if room_id:
        room = db.get(rooms, room_id)
        if room and room.cluster_id == cluster_id:
            device.room_id = room_id
    device.is_active = True
    db.commit()

    log_user_activity(
        db, user=current_user,
        action="Assign perangkat ke cluster",
        category="cluster_management",
        details={"dev_id": dev_id, "cluster_id": cluster_id, "room_id": device.room_id},
        request=request,
    )
    return {"status": "ok", "dev_id": dev_id, "cluster_id": cluster_id, "room_id": device.room_id}


@router.post("/{cluster_id}/unassign-device")
def unassign_device_from_cluster(
    cluster_id: str,
    request: Request,
    dev_id: str = Query(..., description="Device ID to unassign"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Unassign a device/sensor from a cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")
    device = db.get(dev_table, dev_id)
    if not device or device.cluster_id != cluster_id:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan di cluster ini")

    device.cluster_id = None
    device.room_id = None
    db.commit()

    log_user_activity(
        db, user=current_user,
        action="Lepas perangkat dari cluster",
        category="cluster_management",
        details={"dev_id": dev_id, "cluster_id": cluster_id},
        request=request,
    )
    return {"status": "ok", "dev_id": dev_id, "cluster_id": None}


@router.patch("/{cluster_id}/devices/{dev_id}")
def update_cluster_device(
    cluster_id: str,
    dev_id: str,
    req: ClusterDeviceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Update device settings in a cluster (name, assigned room)."""
    device = db.get(dev_table, dev_id)
    if not device or device.cluster_id != cluster_id:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan di cluster ini")

    target_name = req.dev_name or req.name
    if target_name is not None and target_name.strip():
        device.dev_name = target_name.strip()
    if req.room_id is not None:
        if req.room_id in ("", "none", None):
            device.room_id = None
        else:
            r = db.get(rooms, req.room_id)
            if not r or r.cluster_id != cluster_id:
                raise HTTPException(status_code=400, detail="Ruangan tidak valid atau di luar cluster ini")
            device.room_id = req.room_id

    db.commit()
    log_user_activity(
        db, user=current_user,
        action="Mengubah perangkat di cluster",
        category="cluster_management",
        details={"dev_id": dev_id, "cluster_id": cluster_id, "room_id": device.room_id},
        request=request,
    )
    return {
        "status": "ok",
        "dev_id": device.dev_id,
        "dev_name": device.dev_name,
        "name": device.dev_name,
        "room_id": device.room_id,
    }


@router.post("/{cluster_id}/assign-room")
def assign_room_to_cluster(
    cluster_id: str,
    request: Request,
    room_id: str = Query(..., description="Room ID to assign"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Assign an existing room to a cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")
    room = db.get(rooms, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Ruangan tidak ditemukan")

    room.cluster_id = cluster_id
    db.commit()

    log_user_activity(
        db, user=current_user,
        action="Assign ruangan ke cluster",
        category="cluster_management",
        details={"room_id": room_id, "cluster_id": cluster_id},
        request=request,
    )
    return {"status": "ok", "room_id": room_id, "cluster_id": cluster_id}


@router.post("/{cluster_id}/unassign-room")
def unassign_room_from_cluster(
    cluster_id: str,
    request: Request,
    room_id: str = Query(..., description="Room ID to unassign"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Unassign a room from a cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")
    room = db.get(rooms, room_id)
    if not room or room.cluster_id != cluster_id:
        raise HTTPException(status_code=404, detail="Ruangan tidak ditemukan di cluster ini")

    room.cluster_id = None
    db.commit()

    log_user_activity(
        db, user=current_user,
        action="Lepas ruangan dari cluster",
        category="cluster_management",
        details={"room_id": room_id, "cluster_id": cluster_id, "room_name": room.name},
        request=request,
    )
    return {"status": "ok", "room_id": room_id, "cluster_id": None}


@router.post("/{cluster_id}/rooms", status_code=status.HTTP_201_CREATED)
def create_cluster_room(
    cluster_id: str,
    req: ClusterRoomCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Create a new room directly inside a cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")

    clean_name = req.name.strip()
    existing = db.query(rooms).filter(func.lower(rooms.name) == clean_name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama ruangan sudah digunakan")

    room_id = f"room_{uuid.uuid4().hex[:12]}"
    new_room = rooms(
        id=room_id,
        name=clean_name,
        cluster_id=cluster_id,
        created_at=datetime.now(UTC),
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)

    log_user_activity(
        db, user=current_user,
        action="Membuat ruangan di cluster",
        category="cluster_management",
        details={"room_id": room_id, "room_name": clean_name, "cluster_id": cluster_id},
        request=request,
    )
    return {"status": "ok", "id": new_room.id, "name": new_room.name, "cluster_id": cluster_id}


@router.patch("/{cluster_id}/rooms/{room_id}")
def update_cluster_room(
    cluster_id: str,
    room_id: str,
    req: ClusterRoomUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Edit room name in a cluster."""
    room = db.get(rooms, room_id)
    if not room or room.cluster_id != cluster_id:
        raise HTTPException(status_code=404, detail="Ruangan tidak ditemukan di cluster ini")

    clean_name = req.name.strip()
    existing = db.query(rooms).filter(
        func.lower(rooms.name) == clean_name.lower(),
        rooms.id != room_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Nama ruangan sudah digunakan")

    old_name = room.name
    room.name = clean_name
    db.commit()

    log_user_activity(
        db, user=current_user,
        action="Mengubah nama ruangan di cluster",
        category="cluster_management",
        details={"room_id": room_id, "old_name": old_name, "new_name": clean_name, "cluster_id": cluster_id},
        request=request,
    )
    return {"status": "ok", "id": room.id, "name": room.name}


@router.delete("/{cluster_id}/rooms/{room_id}")
def delete_cluster_room(
    cluster_id: str,
    room_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Delete room in a cluster (if no assigned devices)."""
    room = db.get(rooms, room_id)
    if not room or room.cluster_id != cluster_id:
        raise HTTPException(status_code=404, detail="Ruangan tidak ditemukan di cluster ini")

    assigned_devs = db.query(dev_table).filter(dev_table.room_id == room_id).count()
    if assigned_devs > 0:
        raise HTTPException(status_code=400, detail="Tidak dapat menghapus ruangan yang masih memiliki sensor/perangkat")

    room_name = room.name
    db.delete(room)
    db.commit()

    log_user_activity(
        db, user=current_user,
        action="Menghapus ruangan di cluster",
        category="cluster_management",
        details={"room_id": room_id, "room_name": room_name, "cluster_id": cluster_id},
        request=request,
    )
    return {"status": "ok", "message": f"Ruangan '{room_name}' berhasil dihapus"}


@router.get("/{cluster_id}/permissions", response_model=ClusterPermissionMatrix)
def get_cluster_permissions(
    cluster_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Get effective permission matrix for a cluster."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")
    permissions = _get_effective_permissions(cluster_id, db)
    return ClusterPermissionMatrix(cluster_id=cluster_id, permissions=permissions)


@router.put("/{cluster_id}/permissions")
def update_cluster_permissions(
    cluster_id: str,
    req: ClusterRolePermissionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Update permission matrix for a cluster role."""
    cluster = db.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")

    for perm, granted in req.permissions.items():
        row = db.query(ClusterRolePermission).filter(
            ClusterRolePermission.cluster_id == cluster_id,
            ClusterRolePermission.role == req.role,
            ClusterRolePermission.permission == perm,
        ).first()
        if row:
            row.granted = granted
        else:
            db.add(ClusterRolePermission(
                id=str(uuid.uuid4()),
                cluster_id=cluster_id,
                role=req.role,
                permission=perm,
                granted=granted,
            ))

    log_user_activity(
        db, user=current_user,
        action="Mengubah permission cluster",
        category="cluster_management",
        details={"cluster_id": cluster_id, "role": req.role},
        request=request,
        commit=False,
    )
    db.commit()
    return {"status": "ok", "cluster_id": cluster_id, "role": req.role}
