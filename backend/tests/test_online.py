"""Phase 3 online ordering and QR table ordering (SRS §6.21 ONL; BR-046)."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core import ratelimit
from app.core.config import get_settings
from tests.helpers import line, menu, money, tables
from tests.test_delivery import bump_all, zone


@pytest.fixture(autouse=True)
def _fresh_limits():
    ratelimit.reset()
    yield
    ratelimit.reset()


def pub(client, method, path, body=None, key=None, headers=None):
    h = dict(headers or {})
    if key:
        h["Idempotency-Key"] = key
    return client.request(method, "/api/v1/public" + path, json=body, headers=h)


def enable(gm, **extra):
    r = gm.put("/settings/online", {"value": {"enabled": True, **extra}})
    assert r.status_code == 200, r.json()


def cart(m, **kw):
    return {"fulfilment": "Pickup", "name": "Sokha", "phone": "012 777 888", "items": [line(m, "MN-02", 1)], **kw}


def test_menu_quote_checkout_accept_and_tracking(api, client, monkeypatch):
    gm, c, cook = api("gm"), api("cashier"), api("cook")
    m = menu(c)
    assert pub(client, "GET", "/branches/RVS/menu").json()["error"]["code"] == "ONLINE_ORDERING_DISABLED"
    enable(gm)
    pm = pub(client, "GET", "/branches/RVS/menu").json()
    assert pm["branch"]["code"] == "RVS" and any(i["code"] == "MN-02" for i in pm["items"])
    q = pub(client, "POST", "/branches/RVS/quote", cart(m)).json()
    assert money(q["totals"]["total"]) == Decimal("10.45")
    assert c.get("/orders").json()["total"] == 0  # a quote saves nothing
    assert pub(client, "POST", "/branches/RVS/orders", cart(m)).json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    stale = pub(client, "POST", "/branches/RVS/orders", cart(m, expected_total="9.99"), key=str(uuid.uuid4())).json()
    assert stale["error"]["code"] == "PRICE_CHANGED" and stale["error"]["current_total"] == "10.45"
    assert c.get("/orders").json()["total"] == 0
    assert pub(client, "POST", "/branches/RVS/orders", cart(m, items=[line(m, "MN-02", 25)]), key="q1").json()["error"]["code"] == "QUANTITY_LIMIT"
    sent = []
    from app.workers import celery_app

    monkeypatch.setattr(celery_app.EmailSender, "send", lambda self, to, subject, body: sent.append((to, subject, body)))
    key = str(uuid.uuid4())
    o = pub(client, "POST", "/branches/RVS/orders", cart(m, email="sokha@example.com", expected_total="10.45"), key=key)
    assert o.status_code == 201, o.json()
    o = o.json()
    assert o["status"] == "Received" and "payment" not in o
    assert pub(client, "POST", "/branches/RVS/orders", cart(m, email="sokha@example.com", expected_total="10.45"), key=key).json()["order_no"] == o["order_no"]
    assert c.get("/orders").json()["total"] == 1  # the replay didn't create a second order
    assert celery_app.process_outbox() == 1 and o["tracking_url"] in sent[0][2]
    assert pub(client, "GET", f"/track/{o['tracking_token']}").json()["status"] == "Received"
    assert pub(client, "GET", "/track/not-a-real-token").status_code == 404
    # staff accept: sent to the kitchen even though takeaway is normally pay-first (pay at pickup)
    oo = c.get("/online-orders").json()
    assert [x["order_no"] for x in oo] == [o["order_no"]] and oo[0]["customer_phone"] == "012 777 888"
    assert api("cook").post(f"/online-orders/{oo[0]['id']}/accept").status_code == 403
    assert c.post(f"/online-orders/{oo[0]['id']}/accept").json()["tracking_status"] == "Preparing"
    assert c.post(f"/online-orders/{oo[0]['id']}/accept").json()["error"]["code"] == "ONLINE_ORDER_DECIDED"
    bump_all(cook, str(o["order_id"]))
    t = pub(client, "GET", f"/track/{o['tracking_token']}").json()
    assert t["status"] == "Ready" and t["items"][0]["status"] == "Ready" and "customer_phone" not in json.dumps(t)


def test_pause_hours_and_lead_time(api, client):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm, lead_minutes=30)
    assert gm.put("/online-ordering/pause", {"paused": True}).json()["paused"] is True
    assert c.put("/online-ordering/pause", {"paused": False}).status_code == 403
    assert pub(client, "POST", "/branches/RVS/orders", cart(m), key="p1").json()["error"]["code"] == "ONLINE_ORDERING_PAUSED"
    gm.put("/online-ordering/pause", {"paused": False})
    soon = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    assert pub(client, "POST", "/branches/RVS/quote", cart(m, scheduled_at=soon)).json()["error"]["code"] == "TOO_SOON"
    now = datetime.now(timezone(timedelta(hours=7)))
    start = (now + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    closed = f"{start:%H:%M}-{start + timedelta(hours=4):%H:%M}"  # open later today (the range may cross midnight)
    branch_id = gm.get("/branches").json()[0]["id"]
    api("owner").patch(f"/branches/{branch_id}", {"opening_hours": closed})
    assert pub(client, "POST", "/branches/RVS/quote", cart(m)).json()["error"]["code"] == "BRANCH_CLOSED"
    later = (start + timedelta(minutes=30)).isoformat()
    r = pub(client, "POST", "/branches/RVS/quote", cart(m, scheduled_at=later)).json()
    assert money(r.get("totals", {}).get("total", 0)) == Decimal("10.45"), r


def test_sandbox_payment_callback(api, client, monkeypatch):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    assert pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key="n1").json()["error"]["code"] == "ONLINE_PAYMENT_UNAVAILABLE"
    s = get_settings()
    monkeypatch.setattr(s, "PAYMENT_GATEWAY", "sandbox")
    monkeypatch.setattr(s, "PAYMENT_SANDBOX_SECRET", "test-only-sandbox-secret")
    o = pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key=str(uuid.uuid4())).json()
    assert o["payment"]["gateway"] == "sandbox" and "/pay/sandbox?session=" in o["payment"]["redirect_url"]
    oo = c.get("/online-orders").json()[0]
    assert oo["payment_status"] == "Pending" and c.post(f"/online-orders/{oo['id']}/accept").json()["error"]["code"] == "PAYMENT_PENDING"
    from app.integrations.payments import get_gateway

    gw = get_gateway()

    def notify(payload, sig=None):
        body = json.dumps(payload).encode()
        return client.post("/api/v1/public/payments/sandbox/callback", content=body, headers={"X-Signature": sig or gw.sign(body), "Content-Type": "application/json"})

    ok = {"session_ref": o["payment"]["session_ref"], "status": "paid", "amount": "10.45", "currency": "USD", "gateway_txn": "SBX-TXN-1"}
    assert notify(ok, sig="0" * 64).json()["error"]["code"] == "SIGNATURE_INVALID"
    assert notify({**ok, "amount": "1.00"}).json()["error"]["code"] == "PAYMENT_AMOUNT_MISMATCH"
    assert notify(ok).json()["status"] == "recorded"
    assert notify(ok).json()["status"] == "already_recorded"  # gateways retry; one payment only
    order = c.get(f"/orders/{o['order_id']}").json()
    assert order["payment_status"] == "Paid" and money(order["totals"]["paid"]) == Decimal("10.45")
    assert c.post(f"/online-orders/{oo['id']}/accept").json()["status"] == "Accepted"
    monkeypatch.setattr(s, "APP_ENV", "production")
    assert get_gateway() is None  # the sandbox is never used in production


def test_online_delivery_and_reject(api, client):
    gm, c, s = api("gm"), api("cashier"), api("supv")
    m = menu(c)
    enable(gm)
    z = zone(gm)
    body = cart(m, fulfilment="Delivery", delivery={"zone_id": z["id"], "address": "St 63, house 5", "fee_override": "0"})
    assert pub(client, "POST", "/branches/RVS/orders", body, key="d0").status_code == 422  # customers can't set the fee
    body["delivery"].pop("fee_override")
    assert [x["name"] for x in pub(client, "GET", "/branches/RVS/delivery-zones").json()] == ["Riverside 3 km"]
    o = pub(client, "POST", "/branches/RVS/orders", body, key=str(uuid.uuid4())).json()
    assert money(o["totals"]["delivery_fee"]) == Decimal("1.50")
    oo = c.get("/online-orders").json()[0]
    assert s.post(f"/online-orders/{oo['id']}/reject", {"reason": "Kitchen closing"}).json()["status"] == "Rejected"
    t = pub(client, "GET", f"/track/{o['tracking_token']}").json()
    assert t["status"] == "Rejected" and t["reject_reason"] == "Kitchen closing"
    assert c.get(f"/orders/{o['order_id']}").json()["order_status"] == "Cancelled"


def test_qr_table_ordering(api, client):
    gm, c, w = api("gm"), api("cashier"), api("waiter")
    m = menu(c)
    t = tables(gm)
    qr = gm.post(f"/tables/{t['B1']['id']}/qr-code").json()
    assert w.post(f"/tables/{t['B1']['id']}/qr-code").status_code == 403
    assert pub(client, "GET", f"/qr/{qr['token']}").json()["error"]["code"] == "QR_ORDERING_DISABLED"
    gm.put("/settings/qr", {"value": {"enabled": True}})
    page = pub(client, "GET", f"/qr/{qr['token']}").json()
    assert page["table"] == "B1" and page["staff_confirmation"] is True
    r1 = pub(client, "POST", f"/qr/{qr['token']}/orders", {"guest_count": 2, "items": [line(m, "MN-02", 1)]}, key=str(uuid.uuid4())).json()
    assert r1["state"] == "WaitingForStaff" and r1["table"] == "B1"
    assert tables(c)["B1"]["service_state"] != "Available"
    r2 = pub(client, "POST", f"/qr/{qr['token']}/orders", {"items": [line(m, "MN-02", 1)]}, key=str(uuid.uuid4())).json()
    assert r2["order_no"] == r1["order_no"]  # added to the table's open order
    order = c.get(f"/orders/{r1['order_id']}").json()
    assert order["channel"] == "QR" and len(order["items"]) == 2 and all(i["item_status"] == "Pending" for i in order["items"])
    oo = next(x for x in c.get("/online-orders").json() if x["order_no"] == r1["order_no"])
    c.post(f"/online-orders/{oo['id']}/accept")
    assert all(i["item_status"] == "Sent" for i in c.get(f"/orders/{r1['order_id']}").json()["items"])
    # rotating the code invalidates the printed one
    new = gm.post(f"/tables/{t['B1']['id']}/qr-code").json()
    assert pub(client, "GET", f"/qr/{qr['token']}").status_code == 404 and pub(client, "GET", f"/qr/{new['token']}").status_code == 200
    # without staff confirmation the kitchen gets it straight away
    gm.put("/settings/qr", {"value": {"require_staff_confirmation": False}})
    qr2 = gm.post(f"/tables/{t['B2']['id']}/qr-code").json()
    r3 = pub(client, "POST", f"/qr/{qr2['token']}/orders", {"items": [line(m, "MN-02", 1)]}, key=str(uuid.uuid4())).json()
    assert r3["state"] == "SentToKitchen"


def test_public_rate_limit(api, client, monkeypatch):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    monkeypatch.setattr(get_settings(), "PUBLIC_RATE_LIMIT_PER_MINUTE", 3)
    codes = [pub(client, "POST", "/branches/RVS/quote", cart(m)).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
