"""Calls from RMS to GrabFood (GrabFood Partner API v1.1.3, developer.grab.com/docs/grabfood/api/v1-1-3):

* OAuth: POST {GRABFOOD_AUTH_URL}  {"client_id", "client_secret", "grant_type": "client_credentials", "scope": "food.partner_api"}
  -> {"access_token", "token_type": "Bearer", "expires_in"}  (default 7 days; reuse until expiry or a 401)
* Accept/reject (manual acceptance, within 5 minutes): POST {GRABFOOD_API_URL}/partner/v1/order/prepare  {"orderID", "toState": "Accepted"|"Rejected"} -> 204
* Mark ready: POST {GRABFOOD_API_URL}/partner/v1/orders/mark  {"orderID", "markStatus": 1} -> 204 (once per order)
"""
import threading
import time

import httpx

from app.core.config import get_settings

TRANSPORT: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport
_lock = threading.Lock()
_token: dict = {}


class GrabError(Exception):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=10.0, transport=TRANSPORT)


def _access_token(force: bool = False) -> str:
    s = get_settings()
    if not (s.GRABFOOD_CLIENT_ID and s.GRABFOOD_CLIENT_SECRET):
        raise GrabError("GrabFood client credentials aren't configured.")
    with _lock:
        if not force and _token.get("value") and _token["expires"] > time.time() + 60:
            return _token["value"]
        try:
            with _client() as c:
                r = c.post(s.GRABFOOD_AUTH_URL, json={"client_id": s.GRABFOOD_CLIENT_ID, "client_secret": s.GRABFOOD_CLIENT_SECRET,
                                                      "grant_type": "client_credentials", "scope": "food.partner_api"})
        except httpx.HTTPError as e:
            raise GrabError(f"Grab OAuth didn't answer: {type(e).__name__}") from e
        if r.status_code != 200:
            raise GrabError(f"Grab OAuth returned HTTP {r.status_code}")
        body = r.json()
        _token.update(value=body["access_token"], expires=time.time() + int(body.get("expires_in", 3600)))
        return _token["value"]


def _post(path: str, payload: dict, method: str = "POST") -> None:
    s = get_settings()
    for attempt in (1, 2):
        token = _access_token(force=attempt == 2)
        try:
            with _client() as c:
                r = c.request(method, f"{s.GRABFOOD_API_URL.rstrip('/')}{path}", json=payload,
                              headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise GrabError(f"Grab didn't answer: {type(e).__name__}") from e
        if r.status_code == 401 and attempt == 1:
            continue  # token expired early: get a new one once
        if not 200 <= r.status_code < 300:
            raise GrabError(f"Grab returned HTTP {r.status_code}: {r.text[:300]}")
        return


def set_order_state(order_id: str, to_state: str) -> None:
    _post("/partner/v1/order/prepare", {"orderID": order_id, "toState": to_state})


def mark_ready(order_id: str) -> None:
    _post("/partner/v1/orders/mark", {"orderID": order_id, "markStatus": 1})


def reset_token() -> None:
    with _lock:
        _token.clear()


def notify_menu(merchant_id: str) -> None:
    """Update menu notification: POST /partner/v1/merchant/menu/notification; Grab then calls our Get menu webhook."""
    _post("/partner/v1/merchant/menu/notification", {"merchantID": merchant_id})


def update_menu_record(payload: dict) -> None:
    """Update menu record: PUT /partner/v1/menu (price, availableStatus, maxStock of one item or modifier)."""
    _post("/partner/v1/menu", payload, method="PUT")
