# schemas_auth.py
# Validasi Payload & Skema Respons Autentikasi HubGate V5

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class UserLoginPayload(BaseModel):
    username: str
    password: str


# ------------------------------
# SCHEMAS UNTUK USER MANAGEMENT 
# ------------------------------

# 1. Schema untuk Membuat User Baru oleh Admin
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username unik")
    display_name: str = Field(..., min_length=1, max_length=100, description="Nama lengkap/tampilan")
    role: str = Field(..., description="Role user: admin, operator, atau viewer")
    temp_password: Optional[str] = Field(None, min_length=8, description="Password sementara opsional")
    # Cluster assignment (optional — assign immediately on creation)
    cluster_id: Optional[str] = Field(None, description="ID cluster yang ditugaskan")

    @field_validator('username')
    @classmethod
    def normalize_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.isalnum() and "_" not in v:
            raise ValueError("Username hanya boleh berisi huruf, angka, dan underscore")
        return v

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"admin", "operator", "viewer", "root"}
        if v.lower() not in allowed:
            raise ValueError(f"Role harus salah satu dari: {', '.join(allowed)}")
        return v.lower()


# 2. Schema untuk Update Data User
class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = None

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"admin", "operator", "viewer"}
            if v.lower() not in allowed:
                raise ValueError(f"Role harus salah satu dari: {', '.join(allowed)}")
            return v.lower()
        return v


# 3. Schema untuk Update Status Active/Inactive
class UserStatusUpdate(BaseModel):
    is_active: bool


# 4. Schema Response Detail User (Informasi yang dikembalikan ke Frontend)
class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool
    is_online: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    cluster_memberships: Optional[list] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("cluster_memberships", mode="before")
    @classmethod
    def serialize_cluster_memberships(cls, v):
        if not v:
            return []
        result = []
        for item in v:
            if isinstance(item, dict):
                result.append(item)
            elif hasattr(item, "cluster_id"):
                c_name = getattr(item.cluster, "name", None) if getattr(item, "cluster", None) else None
                result.append({
                    "id": getattr(item, "id", None),
                    "cluster_id": item.cluster_id,
                    "role": item.role,
                    "cluster_name": c_name,
                })
        return result


# 5. Schema Response Pembuatan/Reset User (Menampilkan Password Sementara 1x)
class UserWithTempPasswordResponse(UserResponse):
    temp_password: str


# 6. Schema Response Paginated User List
class UserListResponse(BaseModel):
    items: List[UserResponse]
    total: int
    page: int
    page_size: int


# 7. Schema Request Ganti Password Mandiri oleh User
class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=10, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str, info) -> str:
        # Pydantic v2 validation
        return v


# 8. Schema Response Audit Log
class AuditLogResponse(BaseModel):
    id: str
    actor_id: Optional[str]
    action: str
    target_user_id: Optional[str]
    status: str
    ip_address: Optional[str]
    details: Optional[str]
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── CLUSTER SCHEMAS ──────────────────────────────────────────────────────────

class ClusterCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=200)


class ClusterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None


class ClusterResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    device_count: int = 0
    room_count: int = 0
    member_count: int = 0
    rooms: List[dict] = []
    devices: List[dict] = []

    model_config = ConfigDict(from_attributes=True)


class ClusterDetailResponse(ClusterResponse):
    members: list = []
    devices: list = []
    rooms: list = []
    permissions: dict = {}


class ClusterRoomCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ClusterRoomUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ClusterDeviceUpdate(BaseModel):
    dev_name: Optional[str] = None
    name: Optional[str] = None
    room_id: Optional[str] = None


class ClusterListResponse(BaseModel):
    items: List[ClusterResponse]
    total: int
    page: int
    page_size: int


class ClusterPermissionMatrix(BaseModel):
    cluster_id: str
    permissions: dict  # role -> permission -> bool


class ClusterRolePermissionUpdate(BaseModel):
    role: str = Field(..., description="Role: admin, operator, atau viewer")
    permissions: dict[str, bool] = Field(..., description="Permission name -> granted")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in {"admin", "operator", "viewer"}:
            raise ValueError("Role harus salah satu dari: admin, operator, viewer")
        return v


# ─── MEMBERSHIP SCHEMAS ───────────────────────────────────────────────────────

class MembershipCreate(BaseModel):
    user_id: str
    cluster_id: str
    role: str = Field(..., description="admin, operator, atau viewer")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in {"admin", "operator", "viewer"}:
            raise ValueError("Role harus salah satu dari: admin, operator, viewer")
        return v


class MembershipUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in {"admin", "operator", "viewer"}:
            raise ValueError("Role harus salah satu dari: admin, operator, viewer")
        return v


class MembershipResponse(BaseModel):
    id: str
    user_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    cluster_id: str
    cluster_name: Optional[str] = None
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
