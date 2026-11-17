"""Authentication (SRS §6.18, §14.2): login with lockout, rotating refresh tokens, PIN login, password reset."""
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, BusinessRuleError, Unauthorized
from app.core.security import create_access_token, hash_secret, new_opaque_token, password_policy_error, token_digest, verify_secret
from app.models import AuthEvent, Device, PasswordResetToken, User, UserSession
from app.services.platform import audit, notify_permission
from app.utils.timeutil import utcnow


def _event(db: Session, user: User | None, username: str, event: str, ip: str | None, device: str | None = None) -> None:
    db.add(AuthEvent(user_id=user.id if user else None, username=username, event=event, ip=ip, device=device))


def _issue(db: Session, user: User, ip: str | None, user_agent: str | None, device_id: uuid.UUID | None = None) -> dict:
    s = get_settings()
    refresh = new_opaque_token()
    session = UserSession(user_id=user.id, refresh_token_hash=token_digest(refresh), ip=ip, user_agent=user_agent, device_id=device_id,
                          expires_at=utcnow() + timedelta(days=s.REFRESH_TOKEN_EXPIRE_DAYS))
    db.add(session)
    db.flush()
    access, expires_in = create_access_token(user.id, session.id, [b.id for b in user.branches])
    return {"access_token": access, "token_type": "bearer", "expires_in": expires_in, "refresh_token": refresh, "must_change_password": user.must_change_password}


def login(db: Session, username: str, password: str, ip: str | None, user_agent: str | None) -> dict:
    s = get_settings()
    now = utcnow()
    user = db.scalar(select(User).where((User.username.ilike(username)) | (User.email.ilike(username))).with_for_update())
    generic = Unauthorized("Username or password is incorrect.", code="INVALID_CREDENTIALS")
    if user is None:
        _event(db, None, username, "LoginFailed", ip)
        raise generic
    if user.status == "Inactive":
        _event(db, user, username, "LoginFailed", ip)
        raise generic
    if user.locked_until and user.locked_until > now:
        _event(db, user, username, "LoginLocked", ip)
        raise AppError("ACCOUNT_LOCKED", "Too many failed attempts. Try again later or ask an administrator to unlock the account.", 423)
    if not verify_secret(password, user.password_hash):
        window_start = now - timedelta(minutes=s.LOCKOUT_WINDOW_MINUTES)
        if user.first_failed_at is None or user.first_failed_at < window_start:
            user.first_failed_at, user.failed_attempts = now, 0
        user.failed_attempts += 1
        _event(db, user, username, "LoginFailed", ip)
        if user.failed_attempts >= s.LOCKOUT_MAX_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=s.LOCKOUT_DURATION_MINUTES)
            user.failed_attempts, user.first_failed_at = 0, None
            _event(db, user, username, "Lockout", ip)
            audit(db, None, "auth.lockout", "User", user.id, after={"locked_until": user.locked_until}, branch_id=user.branches[0].id if user.branches else None)
            if user.branches:
                notify_permission(db, user.branches[0].id, "users.manage", "System", "Account locked", f"{user.username} was locked after repeated failed sign-ins.", "/users")
        # Failed attempts must persist even though we answer 401.
        db.commit()
        raise generic
    user.failed_attempts, user.first_failed_at, user.locked_until, user.last_login_at = 0, None, None, now
    _event(db, user, username, "Login", ip)
    audit(db, None, "auth.login", "User", user.id, actor_id=user.id, branch_id=user.branches[0].id if user.branches else None)
    return _issue(db, user, ip, user_agent)


def pin_login(db: Session, device_token: str, username: str, pin: str, ip: str | None) -> dict:
    """§14.2: PIN only valid on a registered device of the user's branch."""
    device = db.scalar(select(Device).where(Device.token_hash == token_digest(device_token), Device.status == "Active"))
    user = db.scalar(select(User).where(User.username.ilike(username)))
    if device is None or user is None or user.status != "Active" or not verify_secret(pin, user.pin_hash) or device.branch_id not in {b.id for b in user.branches}:
        _event(db, user, username, "PinFailed", ip)
        db.commit()
        raise Unauthorized("PIN not accepted on this device.", code="INVALID_PIN")
    device.last_seen_at = utcnow()
    _event(db, user, username, "PinSwitch", ip, device.name)
    audit(db, None, "auth.pin_switch", "User", user.id, actor_id=user.id, branch_id=device.branch_id)
    return _issue(db, user, ip, None, device.id)


def refresh(db: Session, refresh_token: str, ip: str | None, user_agent: str | None) -> dict:
    session = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == token_digest(refresh_token)).with_for_update())
    if session is None:
        raise Unauthorized("Sign in again.", code="REFRESH_INVALID")
    if session.revoked_at is not None:
        # Reuse of a rotated token: revoke every session of the user (token theft response).
        db.execute(update(UserSession).where(UserSession.user_id == session.user_id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
        db.commit()
        raise Unauthorized("Sign in again.", code="REFRESH_REUSED")
    if session.expires_at < utcnow():
        raise Unauthorized("Your session expired. Sign in again.", code="REFRESH_EXPIRED")
    user = db.get(User, session.user_id)
    if user is None or user.status != "Active":
        raise Unauthorized("This account is not active.", code="ACCOUNT_INACTIVE")
    session.revoked_at = utcnow()
    return _issue(db, user, ip, user_agent, session.device_id)


def logout(db: Session, session_id: uuid.UUID, user: User, ip: str | None) -> None:
    session = db.get(UserSession, session_id)
    if session and session.revoked_at is None:
        session.revoked_at = utcnow()
    _event(db, user, user.username, "Logout", ip)


def revoke_all(db: Session, user_id: uuid.UUID) -> None:
    db.execute(update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_secret(current, user.password_hash):
        raise BusinessRuleError("PASSWORD_INCORRECT", "Your current password is incorrect.", details=[{"field": "current_password", "issue": "incorrect"}])
    err = password_policy_error(new, user.username)
    if err:
        raise BusinessRuleError("PASSWORD_POLICY", err, details=[{"field": "new_password", "issue": err}])
    user.password_hash, user.must_change_password = hash_secret(new), False
    audit(db, None, "auth.password_changed", "User", user.id, actor_id=user.id)


def forgot_password(db: Session, email_or_username: str) -> str | None:
    """Returns the raw token for delivery by the outbox/email adapter; the API answer is always generic."""
    user = db.scalar(select(User).where((User.email.ilike(email_or_username)) | (User.username.ilike(email_or_username))))
    if user is None or user.status != "Active":
        return None
    token = new_opaque_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_digest(token), expires_at=utcnow() + timedelta(minutes=get_settings().PASSWORD_RESET_EXPIRE_MINUTES)))
    _event(db, user, user.username, "PasswordResetRequested", None)
    return token


def reset_password(db: Session, token: str, new: str) -> None:
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_digest(token)).with_for_update())
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise BusinessRuleError("RESET_TOKEN_INVALID", "This reset link is invalid or has expired.")
    user = db.get(User, row.user_id)
    err = password_policy_error(new, user.username)
    if err:
        raise BusinessRuleError("PASSWORD_POLICY", err)
    user.password_hash, user.must_change_password, user.locked_until = hash_secret(new), False, None
    row.used_at = utcnow()
    revoke_all(db, user.id)  # §14.2: all sessions revoked after reset
    audit(db, None, "auth.password_reset", "User", user.id, actor_id=user.id)
