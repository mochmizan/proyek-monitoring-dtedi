# schemas_auth.py
# Validasi Payload & Skema Respons Autentikasi HubGate V5

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class UserLoginPayload(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    display_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


# ------------------------------
# SCHEMAS UNTUK USER MANAGEMENT 
# ------------------------------

# 1. Schema untuk Membuat User Baru oleh Admin
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username unik")
    display_name: str = Field(..., min_length=1, max_length=100, description="Nama lengkap/tampilan")
    role: str = Field(..., description="Role user: admin, operator, atau viewer")
    temp_password: Optional[str] = Field(None, min_length=8, description="Password sementara opsional")

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
        allowed = {"admin", "operator", "viewer"}
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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True