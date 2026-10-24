# app/routers/memberships.py
# Manage user-cluster membership (assign/remove users from clusters)
import uuid
from typing import Optional, List
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from databasev5 import get_db
from modelsv5 import Cluster, UserClusterMembership, User, UserSession
from auth import require_root, get_current_user
from app.core.csrf import validate_csrf_request
from app.services.activity_logger import log_user_activity
from schemas_auth import MembershipCreate, MembershipUpdate, MembershipResponse

router = APIRouter(
    prefix="/api/memberships",
    tags=["memberships"],
    dependencies=[Depends(validate_csrf_request)],
)

VALID_CLUSTER_ROLES = {"admin", "operator", "viewer"}


def _membership_to_response(m: UserClusterMembership, db: Session) -> MembershipResponse:
    user = db.get(User, m.user_id)
    cluster = db.get(Cluster, m.cluster_id)
    return MembershipResponse(
        id=m.id,
        user_id=m.user_id,
        username=user.username if user else None,
        display_name=user.display_name if user else None,
        cluster_id=m.cluster_id,
        cluster_name=cluster.name if cluster else None,
        role=m.role,
        created_at=m.created_at,
    )


@router.get("", response_model=List[MembershipResponse])
def list_memberships(
    cluster_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] List all memberships, optionally filtered by cluster or user."""
    q = db.query(UserClusterMembership)
    if cluster_id:
        q = q.filter(UserClusterMembership.cluster_id == cluster_id)
    if user_id:
        q = q.filter(UserClusterMembership.user_id == user_id)
    memberships = q.all()
    return [_membership_to_response(m, db) for m in memberships]


@router.post("", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
def create_membership(
    req: MembershipCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Assign a user to a cluster with a role."""
    if req.role not in VALID_CLUSTER_ROLES:
        raise HTTPException(status_code=400, detail=f"Role harus salah satu dari: {', '.join(VALID_CLUSTER_ROLES)}")

    cluster = db.get(Cluster, req.cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster tidak ditemukan")

    user = db.get(User, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    if user.role == "root":
        raise HTTPException(status_code=400, detail="Root tidak perlu ditugaskan ke cluster")

    existing = db.query(UserClusterMembership).filter(
        UserClusterMembership.user_id == req.user_id,
        UserClusterMembership.cluster_id == req.cluster_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="User sudah menjadi anggota cluster ini")

    now = datetime.now(UTC)
    membership = UserClusterMembership(
        id=str(uuid.uuid4()),
        user_id=req.user_id,
        cluster_id=req.cluster_id,
        role=req.role,
        created_at=now,
        created_by=current_user.id,
    )
    db.add(membership)
    log_user_activity(
        db, user=current_user,
        action="Menambahkan anggota ke cluster",
        category="cluster_management",
        details={"user_id": req.user_id, "cluster_id": req.cluster_id, "role": req.role},
        request=request,
        commit=False,
    )
    db.commit()
    db.refresh(membership)
    return _membership_to_response(membership, db)


@router.patch("/{membership_id}", response_model=MembershipResponse)
def update_membership(
    membership_id: str,
    req: MembershipUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Update a member's role in a cluster."""
    membership = db.get(UserClusterMembership, membership_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership tidak ditemukan")

    if req.role not in VALID_CLUSTER_ROLES:
        raise HTTPException(status_code=400, detail=f"Role harus salah satu dari: {', '.join(VALID_CLUSTER_ROLES)}")

    membership.role = req.role
    log_user_activity(
        db, user=current_user,
        action="Mengubah role anggota cluster",
        category="cluster_management",
        details={"membership_id": membership_id, "new_role": req.role},
        request=request,
        commit=False,
    )
    db.commit()
    db.refresh(membership)
    return _membership_to_response(membership, db)


@router.delete("/{membership_id}", status_code=status.HTTP_200_OK)
def remove_membership(
    membership_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_root),
):
    """[Root] Remove a user from a cluster."""
    membership = db.get(UserClusterMembership, membership_id)
    if not membership:
        raise HTTPException(status_code=404, detail="Membership tidak ditemukan")

    user_id = membership.user_id
    cluster_id = membership.cluster_id
    db.delete(membership)
    log_user_activity(
        db, user=current_user,
        action="Menghapus anggota dari cluster",
        category="cluster_management",
        details={"user_id": user_id, "cluster_id": cluster_id},
        request=request,
        commit=False,
    )
    db.commit()
    return {"status": "ok", "message": "Anggota berhasil dihapus dari cluster"}
