import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()  # Argon2id (NFR-SEC-003)


def hash_secret(plain: str) -> str:
    return _hasher.hash(plain)


def verify_secret(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, plain)
    except (VerificationError, InvalidHashError):
        return False


def password_policy_error(password: str, username: str) -> str | None:
    if len(password) < 10:
        return "Use at least 10 characters."
    if password.lower() == username.lower():
        return "The password can't be the same as the username."
    return None


def pin_policy_error(pin: str) -> str | None:
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        return "The PIN must be 4–6 digits."
    if pin in "0123456789" or pin in "9876543210" or len(set(pin)) == 1:
        return "The PIN can't be sequential or repeated digits."
    return None


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID, branch_ids: list[uuid.UUID]) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    expires = s.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "branches": [str(b) for b in branch_ids],
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM), expires


def decode_access_token(token: str) -> dict:
    s = get_settings()
    data = jwt.decode(token, s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])
    if data.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return data
