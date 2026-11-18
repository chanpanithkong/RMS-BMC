"""Customer SMS through PlasGate (mocked with the request shape from PlasGate's API overview), phone sign-in codes and
customer accounts (FR-ONL-004/010), reservation messages (FR-RSV-009). No real SMS is sent."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

from app.core import ratelimit
from app.core.config import get_settings
from app.integrations import sms as sms_int
from tests.helpers import line, menu, tables
from tests.test_customers_reservations import tomorrow_at
from tests.test_delivery import bump_all
from tests.test_online import cart, enable, pub


@pytest.fixture()
def plasgate(monkeypatch):
    s = get_settings()
    for k, v in {"SMS_PROVIDER": "plasgate", "PLASGATE_PRIVATE_KEY": "pk-test", "PLASGATE_SECRET": "sec-test", "PLASGATE_SENDER": "Riverside",
                 "PLASGATE_API_URL": "https://cloudapi.plasgate.example"}.items():
        monkeypatch.setattr(s, k, v)
    state = {"sent": [], "status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/send" and request.url.params["private_key"] == "pk-test" and request.headers["X-Secret"] == "sec-test"
        if state["status"] != 200:
            return httpx.Response(state["status"], text="error")
        state["sent"].append(json.loads(request.content))
        return httpx.Response(200, json={"message_id": f"m{len(state['sent'])}"})

    monkeypatch.setattr(sms_int, "TRANSPORT", httpx.MockTransport(handler))
    ratelimit.reset()
    return state


def deliver():
    from app.workers.celery_app import deliver_sms

    return deliver_sms()


def sms_on(gm, **extra):
    assert gm.put("/settings/sms", {"value": {"enabled": True, **extra}}).status_code == 200


def test_online_order_updates(api, client, plasgate, engine):
    gm, c, cook = api("gm"), api("cashier"), api("cook")
    m = menu(c)
    enable(gm)
    o = pub(client, "POST", "/branches/RVS/orders", cart(m), key=str(uuid.uuid4())).json()
    assert deliver() == {"sent": 0, "failed": 0, "retry": 0, "logged": 0}  # SMS setting is off: nothing queued
    sms_on(gm)
    o = pub(client, "POST", "/branches/RVS/orders", cart(m), key=str(uuid.uuid4())).json()
    oo = next(x for x in c.get("/online-orders").json() if x["order_no"] == o["order_no"])
    c.post(f"/online-orders/{oo['id']}/accept")
    bump_all(cook, str(o["order_id"]))
    assert deliver()["sent"] == 3
    msgs = plasgate["sent"]
    assert {x["to"] for x in msgs} == {"85512777888"} and {x["sender"] for x in msgs} == {"Riverside"}
    assert o["tracking_url"] in msgs[0]["content"] and "accepted" in msgs[1]["content"] and "ready for pickup" in msgs[2]["content"]
    # the ready message goes once even if the kitchen recalls and bumps again
    order = c.get(f"/orders/{o['order_id']}").json()
    assert api("kmgr").post(f"/kitchen/items/{order['items'][0]['id']}/status", {"status": "InPreparation"}).status_code == 200
    bump_all(cook, str(o["order_id"]))
    assert deliver()["sent"] == 0
    with engine.connect() as conn:
        assert conn.execute(text("select count(*), min(provider_ref) from sms_messages where status = 'Sent'")).one() == (3, "m1")


def test_retries_and_no_provider(api, client, plasgate, engine, monkeypatch):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    sms_on(gm)
    pub(client, "POST", "/branches/RVS/orders", cart(m), key=str(uuid.uuid4()))
    plasgate["status"] = 500
    assert deliver()["retry"] == 1
    assert deliver()["retry"] == 0  # backing off: not retried straight away
    for _ in range(3):
        with engine.begin() as conn:
            conn.execute(text("update sms_messages set next_attempt_at = now() - interval '1 second'"))
        assert deliver()["retry"] == 1
    with engine.begin() as conn:
        delay = conn.execute(text("select extract(epoch from next_attempt_at - now()) from sms_messages")).scalar()
        assert 200 < delay <= 240  # 4th failure: 4 minutes
        conn.execute(text("update sms_messages set next_attempt_at = now() - interval '1 second'"))
    assert deliver()["failed"] == 1
    with engine.connect() as conn:
        assert conn.execute(text("select status, attempts from sms_messages")).one() == ("Failed", 5)
    monkeypatch.setattr(get_settings(), "SMS_PROVIDER", "")
    pub(client, "POST", "/branches/RVS/orders", cart(m, phone="012 555 444"), key=str(uuid.uuid4()))
    assert deliver()["logged"] == 1  # no provider: recorded, not sent


def test_phone_sign_in_and_my_orders(api, client, plasgate, monkeypatch):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    r = pub(client, "POST", "/branches/RVS/account/code", {"phone": "015 888 999"})
    assert r.json() == {"sent": True, "expires_in_seconds": 600}
    deliver()
    code = re.search(r"code is (\d{6})", plasgate["sent"][-1]["content"]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    bad = pub(client, "POST", "/branches/RVS/account/verify", {"phone": "015 888 999", "code": wrong}).json()
    assert bad["error"]["code"] == "CODE_INVALID" and bad["error"]["tries_left"] == 4
    assert pub(client, "POST", "/branches/RVS/account/verify", {"phone": "015 888 999", "code": code}).json()["error"]["code"] == "NAME_REQUIRED"
    ok = pub(client, "POST", "/branches/RVS/account/verify", {"phone": "+855 15 888 999", "code": code, "name": "Srey Pov"}).json()
    token = {"X-Customer-Token": ok["customer_token"]}
    assert pub(client, "GET", "/account", headers=token).json()["name"] == "Srey Pov"
    assert pub(client, "POST", "/branches/RVS/account/verify", {"phone": "015 888 999", "code": code, "name": "X"}).json()["error"]["code"] == "CODE_INVALID"  # single use
    pub(client, "POST", "/branches/RVS/orders", cart(m, phone="099 111 222"), key=str(uuid.uuid4()), headers=token)  # signed in: linked even with another phone
    pub(client, "POST", "/branches/RVS/orders", cart(m, phone="099 333 444"), key=str(uuid.uuid4()))  # someone else's order
    mine = pub(client, "GET", "/account/orders", headers=token).json()
    assert len(mine) == 1 and mine[0]["items"][0]["name"]
    assert pub(client, "GET", "/account/orders").json()["error"]["code"] == "CUSTOMER_SIGN_IN_REQUIRED"
    for _ in range(2):
        pub(client, "POST", "/branches/RVS/account/code", {"phone": "015 888 999"})
    assert pub(client, "POST", "/branches/RVS/account/code", {"phone": "015 888 999"}).json()["error"]["code"] == "RATE_LIMITED"  # 3 codes per 15 minutes
    pub(client, "POST", "/account/sign-out", headers=token)
    assert pub(client, "GET", "/account", headers=token).json()["error"]["code"] == "CUSTOMER_SESSION_INVALID"
    monkeypatch.setattr(get_settings(), "SMS_PROVIDER", "")
    assert pub(client, "POST", "/branches/RVS/account/code", {"phone": "015 777 666"}).json()["error"]["code"] == "SMS_UNAVAILABLE"


def test_reservation_confirmation_reminder_and_waitlist(api, plasgate, engine):
    from app.workers.celery_app import reservation_reminders

    gm, s = api("gm"), api("supv")
    sms_on(gm)
    t = tables(s)
    r = s.post("/reservations", {"guest_name": "Kosal", "guest_phone": "011 222 333", "reserved_at": tomorrow_at(19).isoformat(), "party_size": 4,
                                 "table_ids": [t["A1"]["id"]]}).json()
    deliver()
    assert "table for 4 is booked" in plasgate["sent"][-1]["content"] and plasgate["sent"][-1]["to"] == "85511222333"
    assert reservation_reminders() == 0  # not yet inside the 2-hour window
    with engine.begin() as conn:
        conn.execute(text("update table_reservations set reserved_at = now() + interval '90 minutes' where id = :i"), {"i": r["id"]})
    assert reservation_reminders() == 1 and reservation_reminders() == 0  # one reminder only
    deliver()
    assert "reminder" in plasgate["sent"][-1]["content"]
    w = s.post("/waitlist", {"party_name": "Lina", "party_size": 2, "phone": "012 999 000"}).json()
    s.post(f"/waitlist/{w['id']}/notify")
    deliver()
    assert "table for 2 is ready" in plasgate["sent"][-1]["content"]
