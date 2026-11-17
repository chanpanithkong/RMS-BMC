"""Rate limiting for public endpoints (FR-ONL-012, RK-11).

Fixed one-minute windows per client IP and route group. With REDIS_URL set the counters are shared by all API
workers; without it each worker counts on its own, which is fine for a single-process deployment.
"""
import threading
import time

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import AppError

_lock = threading.Lock()
_counts: dict[tuple[str, str, int], int] = {}


class RateLimited(AppError):
    status_code = 429

    def __init__(self, retry_after: int):
        super().__init__("RATE_LIMITED", "Too many requests. Please wait a moment and try again.", retry_after_seconds=retry_after)


def _redis():
    url = get_settings().REDIS_URL
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, socket_timeout=0.2)
    except Exception:  # noqa: BLE001 - fall back to in-process counting
        return None


def limit(group: str, per_minute: int | None = None):
    def dependency(request: Request) -> None:
        cap = per_minute or get_settings().PUBLIC_RATE_LIMIT_PER_MINUTE
        ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = (group, ip, window)
        r = _redis()
        if r is not None:
            try:
                name = f"rl:{group}:{ip}:{window}"
                n = r.incr(name)
                r.expire(name, 120)
            except Exception:  # noqa: BLE001
                r = None
        if r is None:
            with _lock:
                n = _counts.get(key, 0) + 1
                _counts[key] = n
                for k in [k for k in _counts if k[2] < window - 1]:
                    del _counts[k]
        if n > cap:
            raise RateLimited(60 - int(time.time()) % 60)

    return dependency


def reset() -> None:
    with _lock:
        _counts.clear()
