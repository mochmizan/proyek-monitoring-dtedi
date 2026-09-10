import uuid
import secrets
from typing import Optional
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from databasev5 import get_db
from modelsv5 import User, UserSession, UserAuditLog
from auth import get_current_user, require_role, hash_password
from schemas_auth import (
    UserCreate,
    UserUpdate,
    UserStatusUpdate,
    UserResponse,
    UserWithTempPasswordResponse,
    UserListResponse,
    AuditLogResponse
)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"]
)

# Helper function untuk mencatat Audit Log
def log_action(
    db: Session,
    actor_id: str,
    action: str,
    target_user_id: Optional[str],
    status_str: str,
    request: Request,
    details: Optional[str] = None
):
    ip_addr = request.client.host if request.client else None
    audit = UserAuditLog(
        actor_id=actor_id,
        action=action,
        target_user_id=target_user_id,
        status=status_str,
        ip_address=ip_addr,
        details=details
    )
    db.add(audit)
    db.commit()


# Helper function untuk menghitung status is_online
def check_is_online(db: Session, user_id: str) -> bool:
    now = datetime.now(UTC)
    active_session = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.expires_at > now
    ).first()
    return active_session is not None


# ----------------------------------------------------
# ENDPOINTS (KHUSUS ROLE ADMIN)
# ----------------------------------------------------

# 1. GET /api/admin/users - Daftar Pengguna
@router.get("", response_model=UserListResponse)
def get_users(
    search: Optional[str] = Query(None, description="Cari nama atau username"),
    role: Optional[str] = Query(None, description="Filter berdasarkan role"),
    is_active: Optional[bool] = Query(None, description="Filter status aktif"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    query = db.query(User)

    if search:
        search_term = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(User.username).like(search_term),
                func.lower(User.display_name).like(search_term)
            )
        )

    if role:
        query = query.filter(User.role == role.lower())

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    total = query.count()
    offset = (page - 1) * page_size
    users = query.offset(offset).limit(page_size).all()

    # Sertakan status is_online
    items = []
    for u in users:
        u_dict = UserResponse.from_orm(u)
        u_dict.is_online = check_is_online(db, u.id)
        items.append(u_dict)

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


# 2. POST /api/admin/users - Membuat Akun Baru
@router.post("", response_model=UserWithTempPasswordResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    req: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    # Cek keunikan username
    existing = db.query(User).filter(func.lower(User.username) == req.username).first()
    if existing:
        log_action(db, current_user.id, "CREATE_USER", None, "FAILED", request, f"Username {req.username} already exists")
        raise HTTPException(status_code=400, detail="Username sudah digunakan")

    # Generate temp password jika tidak diisi
    temp_pwd = req.temp_password if req.temp_password else secrets.token_urlsafe(10)
    pwd_hash = hash_password(temp_pwd)

    new_user = User(
        username=req.username,
        password_hash=pwd_hash,
        display_name=req.display_name,
        role=req.role,
        is_active=True,
        must_change_password=True,
        created_by=current_user.id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_action(db, current_user.id, "CREATE_USER", new_user.id, "SUCCESS", request, f"Created user {new_user.username} with role {new_user.role}")

    resp = UserWithTempPasswordResponse.from_orm(new_user)
    resp.is_online = False
    resp.temp_password = temp_pwd
    return resp


# 3. GET /api/admin/users/{user_id} - Detail User
@router.get("/{user_id}", response_model=UserResponse)
def get_user_detail(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    resp = UserResponse.from_orm(target_user)
    resp.is_online = check_is_online(db, target_user.id)
    return resp


# 4. PATCH /api/admin/users/{user_id} - Update User
@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    req: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    # Guard 1: Admin tidak bisa menurunkan rolenya sendiri
    if current_user.id == target_user.id and req.role and req.role != "admin":
        raise HTTPException(status_code=400, detail="Anda tidak dapat menurunkan role Anda sendiri")

    # Guard 2: Mencegah penurunan role admin terakhir
    if req.role and req.role != "admin" and target_user.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Tidak dapat mengubah role admin terakhir di sistem")

    if req.display_name is not None:
        target_user.display_name = req.display_name
    if req.role is not None:
        target_user.role = req.role

    target_user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(target_user)

    log_action(db, current_user.id, "UPDATE_USER", target_user.id, "SUCCESS", request, f"Updated profile/role for {target_user.username}")

    resp = UserResponse.from_orm(target_user)
    resp.is_online = check_is_online(db, target_user.id)
    return resp


# 5. PATCH /api/admin/users/{user_id}/status - Toggle Status Aktif/Nonaktif
@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: str,
    req: UserStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    # Guard: Admin tidak bisa menonaktifkan akunnya sendiri
    if current_user.id == target_user.id and not req.is_active:
        raise HTTPException(status_code=400, detail="Anda tidak dapat menonaktifkan akun Anda sendiri")

    # Guard: Mencegah menonaktifkan admin terakhir
    if not req.is_active and target_user.role == "admin":
        active_admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan admin terakhir di sistem")

    target_user.is_active = req.is_active
    target_user.updated_at = datetime.now(UTC)

    # Jika dinonaktifkan, cabut seluruh sesinya
    if not req.is_active:
        db.query(UserSession).filter(UserSession.user_id == target_user.id).delete()

    db.commit()
    db.refresh(target_user)

    action_name = "ACTIVATE_USER" if req.is_active else "DEACTIVATE_USER"
    log_action(db, current_user.id, action_name, target_user.id, "SUCCESS", request)

    resp = UserResponse.from_orm(target_user)
    resp.is_online = check_is_online(db, target_user.id)
    return resp


# 6. POST /api/admin/users/{user_id}/reset-password - Reset Password oleh Admin
@router.post("/{user_id}/reset-password", response_model=UserWithTempPasswordResponse)
def reset_user_password(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    temp_pwd = secrets.token_urlsafe(10)
    target_user.password_hash = hash_password(temp_pwd)
    target_user.must_change_password = True
    target_user.updated_at = datetime.now(UTC)

    # Cabut seluruh sesi lama
    db.query(UserSession).filter(UserSession.user_id == target_user.id).delete()

    db.commit()
    db.refresh(target_user)

    log_action(db, current_user.id, "RESET_PASSWORD", target_user.id, "SUCCESS", request)

    resp = UserWithTempPasswordResponse.from_orm(target_user)
    resp.is_online = False
    resp.temp_password = temp_pwd
    return resp


# 7. POST /api/admin/users/{user_id}/revoke-sessions - Revoke Sesi
@router.post("/{user_id}/revoke-sessions", status_code=status.HTTP_200_OK)
def revoke_user_sessions(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    deleted_count = db.query(UserSession).filter(UserSession.user_id == target_user.id).delete()
    db.commit()

    log_action(db, current_user.id, "REVOKE_SESSIONS", target_user.id, "SUCCESS", request, f"Revoked {deleted_count} active sessions")
    return {"status": "success", "message": f"Berhasil mencabut {deleted_count} sesi aktif."}


# 8. DELETE /api/admin/users/{user_id} - Hapus Pengguna
@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    # Guard: Admin tidak bisa menghapus dirinya sendiri
    if current_user.id == target_user.id:
        raise HTTPException(status_code=400, detail="Anda tidak dapat menghapus akun Anda sendiri")

    # Guard: Mencegah menghapus admin terakhir
    if target_user.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Tidak dapat menghapus admin terakhir di sistem")

    # Hapus sesi & hapus user
    db.query(UserSession).filter(UserSession.user_id == target_user.id).delete()
    db.delete(target_user)
    db.commit()

    log_action(db, current_user.id, "DELETE_USER", user_id, "SUCCESS", request, f"Deleted user {target_user.username}")
    return {"status": "success", "message": "Pengguna berhasil dihapus"}