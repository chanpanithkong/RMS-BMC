import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORM, Strict


class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class PinLoginIn(Strict):
    device_token: str
    username: str
    pin: str = Field(pattern=r"^\d{4,6}$")


class RefreshIn(Strict):
    refresh_token: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool = False


class ChangePasswordIn(Strict):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class ForgotPasswordIn(Strict):
    email_or_username: str


class ResetPasswordIn(Strict):
    token: str
    new_password: str = Field(min_length=10, max_length=200)


class BranchOut(ORM):
    id: uuid.UUID
    code: str
    name_en: str
    name_km: str | None
    timezone: str


class RoleBrief(ORM):
    id: uuid.UUID
    code: str
    name: str


class MeOut(BaseModel):
    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    preferred_language: str
    roles: list[RoleBrief]
    permissions: list[str]
    limits: dict[str, str]
    branches: list[BranchOut]
    current_branch: BranchOut
    business_date: str
    must_change_password: bool


class UserOut(ORM):
    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    phone: str | None
    preferred_language: str
    status: str
    roles: list[RoleBrief]
    branches: list[BranchOut]
    last_login_at: datetime | None
    mfa_enabled: bool
    must_change_password: bool


class UserCreate(Strict):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    preferred_language: Literal["en", "km"] = "en"
    role_codes: list[str] = Field(min_length=1)
    branch_ids: list[uuid.UUID] = Field(min_length=1)
    temporary_password: str = Field(min_length=10, max_length=200)
    pin: str | None = Field(None, pattern=r"^\d{4,6}$")


class UserUpdate(Strict):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    preferred_language: Literal["en", "km"] | None = None
    role_codes: list[str] | None = None
    branch_ids: list[uuid.UUID] | None = None


class ResetCredentialIn(Strict):
    temporary_password: str | None = Field(None, min_length=10)
    pin: str | None = Field(None, pattern=r"^\d{4,6}$")


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=500)


class SessionOut(ORM):
    id: uuid.UUID
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None


class AuthEventOut(ORM):
    id: uuid.UUID
    username: str
    event: str
    ip: str | None
    device: str | None
    occurred_at: datetime


class RoleOut(ORM):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[str] = []
    limits: dict[str, str] = {}


class RoleCreate(Strict):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,29}$")
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    permissions: list[str] = []


class RolePermissionsIn(Strict):
    permissions: list[str]


class RoleLimitsIn(Strict):
    limits: dict[str, Decimal]


class PermissionOut(ORM):
    code: str
    module: str
    description: str


class ApprovalIn(Strict):
    action: Literal["discount", "void", "refund", "stock_adjustment", "cash_variance", "payment_void"]
    approver_username: str
    approver_secret: str = Field(description="Approver's password or PIN, entered on the requesting device")
    amount: Decimal | None = Field(None, ge=0)
    target_id: uuid.UUID | None = None
    reason: str | None = Field(None, max_length=500)


class ApprovalOut(BaseModel):
    approval_id: uuid.UUID
    expires_at: datetime
    approver: str
