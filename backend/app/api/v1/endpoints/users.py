import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, or_, select

from app.core.dependencies import Ctx, require
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.core.security import hash_secret, password_policy_error, pin_policy_error
from app.models import AuthEvent, Branch, Permission, Role, RoleLimit, RolePermission, User, UserBranch, UserRole, UserSession
from app.permissions.catalog import PERMISSIONS
from app.schemas.common import Message, Page
from app.schemas.identity import (AuthEventOut, PermissionOut, ReasonIn, ResetCredentialIn, RoleCreate, RoleLimitsIn, RoleOut, RolePermissionsIn, SessionOut, UserCreate,
                                  UserOut, UserUpdate)
from app.services.auth import revoke_all
from app.services.platform import audit
from app.utils.timeutil import utcnow

router = APIRouter(prefix="/users", tags=["users"])
roles_router = APIRouter(tags=["roles"])
View = Annotated[Ctx, Depends(require("users.view"))]
Manage = Annotated[Ctx, Depends(require("users.manage"))]


def _user(ctx: Ctx, user_id: uuid.UUID) -> User:
    user = ctx.db.get(User, user_id)
    # Branch scope: users outside the caller's branches look like 404 (BR-025).
    if user is None or not ({b.id for b in user.branches} & {b.id for b in ctx.user.branches}):
        raise NotFound("User")
    return user


def _snapshot(u: User) -> dict:
    return {"username": u.username, "full_name": u.full_name, "email": u.email, "status": u.status, "roles": sorted(r.code for r in u.roles), "branches": sorted(str(b.id) for b in u.branches)}


def _set_roles(ctx: Ctx, user: User, codes: list[str]) -> None:
    if user.id == ctx.user_id:
        raise Forbidden("You can't change your own roles.", code="SELF_GRANT")  # BR-021, FR-USER-013
    roles = list(ctx.db.scalars(select(Role).where(Role.code.in_(codes))))
    if len(roles) != len(set(codes)):
        raise BusinessRuleError("ROLE_UNKNOWN", "One or more roles don't exist.")
    ctx.db.execute(delete(UserRole).where(UserRole.user_id == user.id))
    ctx.db.add_all([UserRole(user_id=user.id, role_id=r.id) for r in roles])


def _set_branches(ctx: Ctx, user: User, ids: list[uuid.UUID]) -> None:
    allowed = {b.id for b in ctx.user.branches}
    if not set(ids) <= allowed or ctx.db.scalar(select(func.count()).select_from(Branch).where(Branch.id.in_(ids))) != len(set(ids)):
        raise Forbidden("You can only assign branches you manage.", code="BRANCH_FORBIDDEN")
    ctx.db.execute(delete(UserBranch).where(UserBranch.user_id == user.id))
    ctx.db.add_all([UserBranch(user_id=user.id, branch_id=b, is_default=i == 0) for i, b in enumerate(ids)])


@router.get("", response_model=Page[UserOut])
def list_users(ctx: View, q: str | None = None, status: str | None = None, role: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(User).join(UserBranch).where(UserBranch.branch_id.in_([b.id for b in ctx.user.branches])).distinct()
    if q:
        stmt = stmt.where(or_(User.username.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(User.status == status)
    if role:
        stmt = stmt.where(User.id.in_(select(UserRole.user_id).join(Role).where(Role.code == role)))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(User.full_name).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, ctx: Manage):
    if err := password_policy_error(body.temporary_password, body.username):
        raise BusinessRuleError("PASSWORD_POLICY", err, details=[{"field": "temporary_password", "issue": err}])
    if body.pin and (err := pin_policy_error(body.pin)):
        raise BusinessRuleError("PIN_POLICY", err, details=[{"field": "pin", "issue": err}])
    if ctx.db.scalar(select(User.id).where(func.lower(User.username) == body.username.lower())):
        raise Conflict("USERNAME_EXISTS", "That username is taken.")
    if body.email and ctx.db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise Conflict("EMAIL_EXISTS", "That email is already used by another account.")
    user = User(username=body.username, full_name=body.full_name, email=body.email, phone=body.phone, preferred_language=body.preferred_language,
                password_hash=hash_secret(body.temporary_password), pin_hash=hash_secret(body.pin) if body.pin else None, must_change_password=True)
    ctx.db.add(user)
    ctx.db.flush()
    _set_roles(ctx, user, body.role_codes)
    _set_branches(ctx, user, body.branch_ids)
    ctx.db.flush()
    ctx.db.refresh(user)
    audit(ctx.db, ctx, "user.create", "User", user.id, after=_snapshot(user))
    return user


@router.get("/auth-events", response_model=Page[AuthEventOut], summary="Sign-in history (FR-USER-012)")
def auth_events(ctx: View, username: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(AuthEvent)
    if username:
        stmt = stmt.where(AuthEvent.username.ilike(username))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(AuthEvent.occurred_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, ctx: View):
    return _user(ctx, user_id)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, ctx: Manage):
    user = _user(ctx, user_id)
    before = _snapshot(user)
    data = body.model_dump(exclude_unset=True)
    for f in ("full_name", "email", "phone", "preferred_language"):
        if f in data:
            setattr(user, f, data[f])
    if body.role_codes is not None:
        _set_roles(ctx, user, body.role_codes)
    if body.branch_ids is not None:
        _set_branches(ctx, user, body.branch_ids)
    ctx.db.flush()
    ctx.db.refresh(user)
    audit(ctx.db, ctx, "user.update", "User", user.id, before=before, after=_snapshot(user))
    return user


@router.post("/{user_id}/deactivate", response_model=UserOut, summary="Deactivate and revoke all sessions (FR-USER-002)")
def deactivate(user_id: uuid.UUID, body: ReasonIn, ctx: Manage):
    user = _user(ctx, user_id)
    if user.id == ctx.user_id:
        raise Forbidden("You can't deactivate your own account.", code="SELF_DEACTIVATE")
    user.status = "Inactive"
    revoke_all(ctx.db, user.id)
    audit(ctx.db, ctx, "user.deactivate", "User", user.id, after={"status": "Inactive"}, reason=body.reason)
    return user


@router.post("/{user_id}/activate", response_model=UserOut)
def activate(user_id: uuid.UUID, ctx: Manage):
    user = _user(ctx, user_id)
    user.status, user.locked_until, user.failed_attempts = "Active", None, 0
    audit(ctx.db, ctx, "user.activate", "User", user.id, after={"status": "Active"})
    return user


@router.post("/{user_id}/unlock", response_model=UserOut)
def unlock(user_id: uuid.UUID, ctx: Manage):
    user = _user(ctx, user_id)
    user.locked_until, user.failed_attempts, user.first_failed_at = None, 0, None
    audit(ctx.db, ctx, "user.unlock", "User", user.id)
    return user


@router.post("/{user_id}/reset-credentials", response_model=Message, summary="Administrator password and/or PIN reset; forces change at next login")
def reset_credentials(user_id: uuid.UUID, body: ResetCredentialIn, ctx: Manage):
    user = _user(ctx, user_id)
    if body.temporary_password:
        if err := password_policy_error(body.temporary_password, user.username):
            raise BusinessRuleError("PASSWORD_POLICY", err)
        user.password_hash, user.must_change_password = hash_secret(body.temporary_password), True
        revoke_all(ctx.db, user.id)
    if body.pin:
        if err := pin_policy_error(body.pin):
            raise BusinessRuleError("PIN_POLICY", err)
        user.pin_hash = hash_secret(body.pin)
    audit(ctx.db, ctx, "user.reset_credentials", "User", user.id, after={"password": bool(body.temporary_password), "pin": bool(body.pin)})
    return {"message": "Credentials reset."}


@router.get("/{user_id}/sessions", response_model=list[SessionOut])
def sessions(user_id: uuid.UUID, ctx: View):
    _user(ctx, user_id)
    return ctx.db.scalars(select(UserSession).where(UserSession.user_id == user_id).order_by(UserSession.created_at.desc()).limit(50)).all()


@router.delete("/sessions/{session_id}", response_model=Message)
def revoke_session(session_id: uuid.UUID, ctx: Manage):
    s = ctx.db.get(UserSession, session_id)
    if s is None:
        raise NotFound("Session")
    _user(ctx, s.user_id)
    s.revoked_at = s.revoked_at or utcnow()
    audit(ctx.db, ctx, "user.session_revoke", "UserSession", s.id)
    return {"message": "Session revoked."}


# ---------------------------------------------------------------- roles and permissions
def _role_out(ctx: Ctx, role: Role) -> dict:
    perms = sorted(ctx.db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)))
    limits = {rl.limit_key: str(rl.value) for rl in ctx.db.scalars(select(RoleLimit).where(RoleLimit.role_id == role.id))}
    return {**{c: getattr(role, c) for c in ("id", "code", "name", "description", "is_system")}, "permissions": perms, "limits": limits}


def _editable_role(ctx: Ctx, role_id: uuid.UUID) -> Role:
    role = ctx.db.get(Role, role_id)
    if role is None:
        raise NotFound("Role")
    if role.code in ctx.roles:
        raise Forbidden("You can't change a role you hold.", code="SELF_GRANT")
    return role


@roles_router.get("/permissions", response_model=list[PermissionOut], tags=["roles"])
def list_permissions(ctx: View):
    return ctx.db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all()


@roles_router.get("/roles", response_model=list[RoleOut])
def list_roles(ctx: View):
    return [_role_out(ctx, r) for r in ctx.db.scalars(select(Role).order_by(Role.name))]


@roles_router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(body: RoleCreate, ctx: Annotated[Ctx, Depends(require("roles.manage"))]):
    unknown = set(body.permissions) - set(PERMISSIONS)
    if unknown:
        raise BusinessRuleError("PERMISSION_UNKNOWN", f"Unknown permissions: {', '.join(sorted(unknown))}")
    if ctx.db.scalar(select(Role.id).where(Role.code == body.code)):
        raise Conflict("ROLE_EXISTS", "A role with this code already exists.")
    role = Role(code=body.code, name=body.name, description=body.description, is_system=False)
    ctx.db.add(role)
    ctx.db.flush()
    ctx.db.add_all([RolePermission(role_id=role.id, permission_code=p) for p in set(body.permissions)])
    audit(ctx.db, ctx, "role.create", "Role", role.id, after={"code": role.code, "permissions": sorted(body.permissions)})
    return _role_out(ctx, role)


@roles_router.put("/roles/{role_id}/permissions", response_model=RoleOut)
def set_role_permissions(role_id: uuid.UUID, body: RolePermissionsIn, ctx: Annotated[Ctx, Depends(require("roles.manage"))]):
    role = _editable_role(ctx, role_id)
    unknown = set(body.permissions) - set(PERMISSIONS)
    if unknown:
        raise BusinessRuleError("PERMISSION_UNKNOWN", f"Unknown permissions: {', '.join(sorted(unknown))}")
    before = _role_out(ctx, role)["permissions"]
    ctx.db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    ctx.db.add_all([RolePermission(role_id=role.id, permission_code=p) for p in set(body.permissions)])
    ctx.db.flush()
    audit(ctx.db, ctx, "role.permissions", "Role", role.id, before={"permissions": before}, after={"permissions": sorted(body.permissions)})
    return _role_out(ctx, role)


@roles_router.put("/roles/{role_id}/limits", response_model=RoleOut, summary="Approval limits by role (FR-CFG-017)")
def set_role_limits(role_id: uuid.UUID, body: RoleLimitsIn, ctx: Annotated[Ctx, Depends(require("roles.manage"))]):
    role = _editable_role(ctx, role_id)
    before = _role_out(ctx, role)["limits"]
    ctx.db.execute(delete(RoleLimit).where(RoleLimit.role_id == role.id))
    ctx.db.add_all([RoleLimit(role_id=role.id, limit_key=k, value=v) for k, v in body.limits.items()])
    ctx.db.flush()
    audit(ctx.db, ctx, "role.limits", "Role", role.id, before=before, after={k: str(v) for k, v in body.limits.items()})
    return _role_out(ctx, role)
