from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response
from sqlalchemy import select

from app.core.config import get_settings
from app.core.dependencies import CurrentCtx, DbSession
from app.core.exceptions import Unauthorized
from app.models import OutboxEvent, User
from app.schemas.common import Message
from app.schemas.identity import ApprovalIn, ApprovalOut, ChangePasswordIn, ForgotPasswordIn, LoginIn, MeOut, PinLoginIn, RefreshIn, ResetPasswordIn, TokenOut
from app.services import auth as svc
from app.services.platform import grant_approval

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(s.REFRESH_COOKIE_NAME, token, httponly=True, secure=s.APP_ENV not in ("development", "test"), samesite="strict",
                        max_age=s.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path="/api/v1/auth")


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


@router.post("/login", response_model=TokenOut, summary="Sign in with username or email and password")
def login(body: LoginIn, request: Request, response: Response, db: DbSession):
    ip, ua = _client(request)
    result = svc.login(db, body.username, body.password, ip, ua)
    _set_refresh_cookie(response, result.pop("refresh_token"))
    return result


@router.post("/pin-login", response_model=TokenOut, summary="Quick PIN switch on a registered POS/KDS device")
def pin_login(body: PinLoginIn, request: Request, response: Response, db: DbSession):
    result = svc.pin_login(db, body.device_token, body.username, body.pin, _client(request)[0])
    _set_refresh_cookie(response, result.pop("refresh_token"))
    return result


@router.post("/refresh", response_model=TokenOut, summary="Rotate the refresh token (HttpOnly cookie) and get a new access token")
def refresh(request: Request, response: Response, db: DbSession, body: RefreshIn | None = None,
            rms_refresh: Annotated[str | None, Cookie()] = None):
    token = (body.refresh_token if body else None) or rms_refresh
    if not token:
        raise Unauthorized("Sign in again.", code="REFRESH_MISSING")
    ip, ua = _client(request)
    result = svc.refresh(db, token, ip, ua)
    _set_refresh_cookie(response, result.pop("refresh_token"))
    return result


@router.post("/logout", response_model=Message)
def logout(ctx: CurrentCtx, response: Response):
    svc.logout(ctx.db, ctx.session_id, ctx.user, ctx.ip)
    response.delete_cookie(get_settings().REFRESH_COOKIE_NAME, path="/api/v1/auth")
    return {"message": "Signed out."}


@router.get("/me", response_model=MeOut)
def me(ctx: CurrentCtx):
    u = ctx.user
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "preferred_language": u.preferred_language, "roles": u.roles,
            "permissions": sorted(ctx.permissions), "limits": {k: str(v) for k, v in ctx._limits.items()}, "branches": [b for b in u.branches if b.is_active],
            "current_branch": ctx.branch, "business_date": ctx.business_date().isoformat(), "must_change_password": u.must_change_password,
            "restaurant": _restaurant_names(ctx)}


def _restaurant_names(ctx) -> dict:
    from app.models import Restaurant

    r = ctx.db.get(Restaurant, ctx.branch.restaurant_id)
    return {"name_en": r.name_en, "name_km": r.name_km} if r else {}


@router.post("/password/change", response_model=Message)
def change_password(body: ChangePasswordIn, ctx: CurrentCtx):
    svc.change_password(ctx.db, ctx.user, body.current_password, body.new_password)
    return {"message": "Password changed."}


@router.post("/password/forgot", response_model=Message, summary="Always returns the same message (no account enumeration)")
def forgot_password(body: ForgotPasswordIn, db: DbSession):
    token = svc.forgot_password(db, body.email_or_username)
    if token:
        user = db.scalar(select(User).where((User.email.ilike(body.email_or_username)) | (User.username.ilike(body.email_or_username))))
        db.add(OutboxEvent(event_type="email.password_reset", topic="email", payload={"user_id": str(user.id), "email": user.email, "token": token}))
    return {"message": "If the account exists, a reset link has been sent."}


@router.post("/password/reset", response_model=Message)
def reset_password(body: ResetPasswordIn, db: DbSession):
    svc.reset_password(db, body.token, body.new_password)
    return {"message": "Password updated. Sign in with your new password."}


approvals = APIRouter(prefix="/approvals", tags=["approvals"])


@approvals.post("", response_model=ApprovalOut, status_code=201, summary="Manager approval on the requesting device; returns a single-use token")
def create_approval(body: ApprovalIn, ctx: CurrentCtx):
    a = grant_approval(ctx, body.action, body.approver_username, body.approver_secret, body.amount, body.target_id, body.reason)
    return {"approval_id": a.id, "expires_at": a.expires_at, "approver": body.approver_username}
