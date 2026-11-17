"""Organisation, security and platform tables (SRS §10.2 Organisation, Security, Platform)."""
import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, Time, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin, VersionMixin, check_in

USER_STATUS = ("Active", "Locked", "Inactive")


class Restaurant(IdMixin, TimestampMixin, Base):
    __tablename__ = "restaurants"
    legal_name: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(150))
    name_km: Mapped[str | None] = mapped_column(String(150))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    base_currency: Mapped[str] = mapped_column(String(3), default="USD")


class Branch(IdMixin, TimestampMixin, Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("restaurant_id", "code"),)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"))
    code: Mapped[str] = mapped_column(String(10))
    name_en: Mapped[str] = mapped_column(String(120))
    name_km: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Phnom_Penh")
    day_end_time: Mapped[time] = mapped_column(Time, default=time(4, 0))
    opening_hours: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(check_in("status", USER_STATUS), name="status"),
        CheckConstraint("preferred_language IN ('en','km')", name="language"),
        Index("uq_users_username_lower", text("lower(username)"), unique=True),
        Index("uq_users_email_lower", text("lower(email)"), unique=True, postgresql_where=text("email IS NOT NULL")),
    )
    username: Mapped[str] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    pin_hash: Mapped[str | None] = mapped_column(Text)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("employees.id"), unique=True)
    preferred_language: Mapped[str] = mapped_column(String(2), default="en")
    status: Mapped[str] = mapped_column(String(10), default="Active")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    first_failed_at: Mapped[datetime | None]
    locked_until: Mapped[datetime | None]
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None]
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", lazy="selectin")
    branches: Mapped[list[Branch]] = relationship(secondary="user_branches", lazy="selectin")


class Role(IdMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    module: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code"), primary_key=True)


class RoleLimit(Base):
    """Approval limits by role (FR-CFG-017). Values are illustrative until D-04/D-05 are decided."""

    __tablename__ = "role_limits"
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    limit_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[Decimal]


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)


class UserBranch(Base):
    __tablename__ = "user_branches"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Device(IdMixin, TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (CheckConstraint(check_in("kind", ("POS", "KDS", "PrintAgent", "Web")), name="kind"), CheckConstraint(check_in("status", ("Active", "Revoked")), name="status"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(12))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="Active")
    last_seen_at: Mapped[datetime | None]


class UserSession(IdMixin, Base):
    __tablename__ = "user_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class AuthEvent(IdMixin, Base):
    """Sign-in history (FR-USER-012)."""

    __tablename__ = "auth_events"
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    username: Mapped[str] = mapped_column(String(254))
    event: Mapped[str] = mapped_column(String(30))
    ip: Mapped[str | None] = mapped_column(String(64))
    device: Mapped[str | None] = mapped_column(String(120))
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class PasswordResetToken(IdMixin, Base):
    __tablename__ = "password_reset_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class Approval(IdMixin, Base):
    """Single-use approval tokens bound to action, target, amount and requester (BR-009, BR-029, §13.4)."""

    __tablename__ = "approvals"
    __table_args__ = (CheckConstraint(check_in("status", ("Approved", "Used", "Expired")), name="status"), CheckConstraint("approver_id <> requested_by", name="separation_of_duties"))
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"))
    action: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None]
    amount: Mapped[Decimal | None]
    reason: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    limit_applied: Mapped[Decimal | None]
    status: Mapped[str] = mapped_column(String(10), default="Approved")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class NumberSequence(Base):
    """Numbering per branch, series and period (BR-001, BR-049)."""

    __tablename__ = "number_sequences"
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branches.id"), primary_key=True)
    series: Mapped[str] = mapped_column(String(20), primary_key=True)
    period: Mapped[str] = mapped_column(String(10), primary_key=True)
    next_value: Mapped[int] = mapped_column(BigInteger, default=1)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    scope: Mapped[str] = mapped_column(String(60), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class OutboxEvent(IdMixin, Base):
    __tablename__ = "outbox_events"
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    event_type: Mapped[str] = mapped_column(String(60))
    topic: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Setting(IdMixin, TimestampMixin, VersionMixin, Base):
    """Restaurant or branch settings by key (FR-CFG-*); branch_id NULL = restaurant default."""

    __tablename__ = "settings"
    __table_args__ = (Index("uq_settings_scope_key", text("coalesce(branch_id, '00000000-0000-0000-0000-000000000000'::uuid)"), "key", unique=True),)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[dict]
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AuditLog(Base):
    """Append-only, hash-chained (BR-023, FR-AUD-006). UPDATE/DELETE are blocked by a trigger."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_entity", "entity_type", "entity_id"), Index("ix_audit_logs_actor_time", "actor_user_id", "occurred_at"))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(String(10), default="User")
    device_id: Mapped[uuid.UUID | None]
    ip: Mapped[str | None] = mapped_column(String(64))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(60))
    before_data: Mapped[dict | None]
    after_data: Mapped[dict | None]
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(40))
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)


class Notification(IdMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_unread", "recipient_user_id", "read_at"),)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    data: Mapped[dict | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    read_at: Mapped[datetime | None]
