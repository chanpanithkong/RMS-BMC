import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.models import Branch, RoleLimit, RolePermission, User, UserSession
from app.utils.timeutil import business_date_for, utcnow

# Function scope: the session commits as soon as the route returns, before the response is sent.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


@dataclass
class Ctx:
    """Who is acting, where, and with which permissions. Built for every authenticated request."""

    db: Session
    user: User
    session_id: uuid.UUID
    branch: Branch
    permissions: set[str]
    roles: set[str]
    ip: str | None = None
    device_id: uuid.UUID | None = None
    correlation_id: str | None = None
    _limits: dict[str, Decimal] = field(default_factory=dict)

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def branch_id(self) -> uuid.UUID:
        return self.branch.id

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise Forbidden(f"Your role doesn't include {permission}.", code="PERMISSION_DENIED")

    def limit(self, key: str) -> Decimal:
        return self._limits.get(key, Decimal("0"))

    def business_date(self):
        return business_date_for(utcnow(), self.branch.timezone, self.branch.day_end_time)


def load_permissions(db: Session, user: User) -> tuple[set[str], dict[str, Decimal]]:
    role_ids = [r.id for r in user.roles]
    if not role_ids:
        return set(), {}
    perms = set(db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id.in_(role_ids))))
    limits: dict[str, Decimal] = {}
    for rl in db.scalars(select(RoleLimit).where(RoleLimit.role_id.in_(role_ids))):
        limits[rl.limit_key] = max(limits.get(rl.limit_key, Decimal("0")), rl.value)
    return perms, limits


def resolve_branch(user: User, requested: str | None) -> Branch:
    active = [b for b in user.branches if b.is_active]
    if not active:
        raise Forbidden("Your account isn't assigned to a branch.", code="NO_BRANCH")
    if requested:
        for b in active:
            if str(b.id) == requested or b.code == requested:
                return b
        raise Forbidden("You don't have access to that branch.", code="BRANCH_FORBIDDEN")
    return active[0]


def authenticate(db: Session, token: str) -> tuple[User, uuid.UUID]:
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Your session expired. Sign in again.", code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise Unauthorized("Invalid access token.", code="TOKEN_INVALID")
    session = db.get(UserSession, uuid.UUID(claims["sid"]))
    if session is None or session.revoked_at is not None:
        raise Unauthorized("This session was signed out.", code="SESSION_REVOKED")
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or user.status != "Active":
        raise Unauthorized("This account is not active.", code="ACCOUNT_INACTIVE")
    return user, session.id


def get_ctx(
    request: Request,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_branch_id: Annotated[str | None, Header()] = None,
) -> Ctx:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized()
    user, sid = authenticate(db, authorization[7:])
    perms, limits = load_permissions(db, user)
    ctx = Ctx(db=db, user=user, session_id=sid, branch=resolve_branch(user, x_branch_id), permissions=perms, roles={r.code for r in user.roles},
              ip=request.client.host if request.client else None, correlation_id=getattr(request.state, "correlation_id", None), _limits=limits)
    request.state.ctx = ctx
    return ctx


CurrentCtx = Annotated[Ctx, Depends(get_ctx)]


def require(*permissions: str):
    """Route dependency: the caller must hold every listed permission (BR-021, §13.4)."""

    def dep(ctx: CurrentCtx) -> Ctx:
        for p in permissions:
            ctx.require(p)
        return ctx

    return dep
