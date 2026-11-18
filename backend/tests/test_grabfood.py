"""GrabFood order import. Payloads follow the GrabFood Partner API v1.1.3 docs and Grab's SDK models; Grab itself is mocked."""
import json
import uuid
from decimal import Decimal

import httpx
import pytest

from app.core.config import get_settings
from app.integrations import grabfood as grab_int
from tests.helpers import menu, money
from tests.test_delivery import bump_all

MERCHANT = "1-CYNGRUNGSBCCC"


@pytest.fixture()
def grab(monkeypatch, api):
    s = get_settings()
    for k, v in {"GRABFOOD_PARTNER_CLIENT_ID": "rms-for-grab", "GRABFOOD_PARTNER_CLIENT_SECRET": "partner-secret-123", "GRABFOOD_CLIENT_ID": "grab-client",
                 "GRABFOOD_CLIENT_SECRET": "grab-secret", "GRABFOOD_API_URL": "https://partner-api.grab.example/grabfood",
                 "GRABFOOD_AUTH_URL": "https://partner-api.grab.example/grabid/v1/oauth2/token"}.items():
        monkeypatch.setattr(s, k, v)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/grabid/v1/oauth2/token":
            body = json.loads(request.content)
            assert body == {"client_id": "grab-client", "client_secret": "grab-secret", "grant_type": "client_credentials", "scope": "food.partner_api"}
            return httpx.Response(200, json={"access_token": "grab-token", "token_type": "Bearer", "expires_in": 604799})
        assert request.headers["Authorization"] == "Bearer grab-token"
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(204)

    monkeypatch.setattr(grab_int, "TRANSPORT", httpx.MockTransport(handler))
    grab_int.reset_token()
    assert api("gm").put("/settings/grabfood", {"value": {"enabled": True, "merchant_id": MERCHANT, "commission_rate": "0.30"}}).status_code == 200
    return calls


def bearer(client):
    r = client.post("/api/v1/integrations/grabfood/oauth/token", json={"client_id": "rms-for-grab", "client_secret": "partner-secret-123", "grant_type": "client_credentials",
                                                                       "scope": "food.partner_api"})
    assert r.status_code == 200, r.json()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def grab_order(m, ref="123-CYNKLPCVRN5", mode="MANUAL", qty=2, item_id=None, total=None, edit=False):
    """Two Beef Lok Lak at 9.50 + 10 % tax (illustrative) = 20.90 USD = 85,690 KHR at 4,100 -> 8,569,000 in minor units (exponent 2)."""
    return {"orderID": ref, "shortOrderNumber": "GF-123", "merchantID": MERCHANT, "partnerMerchantID": "RVS", "paymentType": "CASHLESS", "cutlery": True,
            "orderTime": "2026-11-17T05:06:00Z", "scheduledTime": "", "currency": {"code": "KHR", "symbol": "៛", "exponent": 2},
            "featureFlags": {"orderAcceptedType": mode, "orderType": "DeliveredByGrab", "isMexEditOrder": edit},
            "items": [{"id": item_id or str(m["MN-02"]["variants"]["Regular"]), "grabItemID": "IDN-1#0", "quantity": qty, "price": 4284500, "tax": 0,
                       "specifications": "No chilli", "modifiers": []}],
            "price": {"subtotal": 8569000, "tax": 0, "deliveryFee": 0, "eaterPayment": 0, "total": total if total is not None else 8569000},
            "receiver": {"name": "Prashanth", "phones": "85512000000"}}


def submit(client, h, body):
    return client.post("/api/v1/integrations/grabfood/orders", json=body, headers=h)


def test_token_and_webhook_auth(client, grab):
    bad = client.post("/api/v1/integrations/grabfood/oauth/token", json={"client_id": "rms-for-grab", "client_secret": "wrong", "grant_type": "client_credentials"})
    assert bad.status_code == 401
    tok = client.post("/api/v1/integrations/grabfood/oauth/token", json={"client_id": "rms-for-grab", "client_secret": "partner-secret-123", "grant_type": "client_credentials"}).json()
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == 604800
    assert client.post("/api/v1/integrations/grabfood/orders", json={}).status_code == 401
    assert client.put("/api/v1/integrations/grabfood/order/state", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_manual_order_accept_ready_collected(api, client, grab):
    from app.workers.celery_app import process_outbox

    c, cook = api("cashier"), api("cook")
    m = menu(c)
    h = bearer(client)
    r = submit(client, h, grab_order(m)).json()
    assert r["status"] == "received"
    assert submit(client, h, grab_order(m)).json()["status"] == "duplicate"  # Grab retries: one order
    po = c.get("/platform-orders").json()[0]
    assert po["acceptance"] == "Received" and po["platform_short_no"] == "GF-123" and po["platform_ref"] == "123-CYNKLPCVRN5" and po["mismatch_note"] is None
    assert money(po["commission_amount"]) == Decimal("6.27")  # 30 % of 20.90 (rate set for the branch)
    order = c.get(f"/orders/{po['order_id']}").json()
    assert order["channel"] == "Platform" and order["items"][0]["note"] == "No chilli" and money(order["totals"]["grand_total"]) == Decimal("20.90")
    assert api("cook").post(f"/platform-orders/{po['order_id']}/accept").status_code == 403
    assert c.post(f"/platform-orders/{po['order_id']}/accept").json()["acceptance"] == "Accepted"
    order = c.get(f"/orders/{po['order_id']}").json()
    assert order["payment_status"] == "Paid" and all(i["item_status"] == "Sent" for i in order["items"])
    assert process_outbox() == 1 and grab[-1] == ("/grabfood/partner/v1/order/prepare", {"orderID": "123-CYNKLPCVRN5", "toState": "Accepted"})
    bump_all(cook, po["order_id"])
    assert process_outbox() == 1 and grab[-1] == ("/grabfood/partner/v1/orders/mark", {"orderID": "123-CYNKLPCVRN5", "markStatus": 1})
    st = client.put("/api/v1/integrations/grabfood/order/state", json={"merchantID": MERCHANT, "orderID": "123-CYNKLPCVRN5", "state": "COLLECTED"}, headers=h).json()
    assert st["status"] == "collected" and c.get(f"/orders/{po['order_id']}").json()["order_status"] == "Completed"


def test_reject_auto_unknown_and_mapping(api, client, grab):
    from app.workers.celery_app import process_outbox

    c, gm, s = api("cashier"), api("gm"), api("supv")
    m = menu(c)
    h = bearer(client)
    submit(client, h, grab_order(m, ref="R-1"))
    po = c.get("/platform-orders").json()[0]
    assert s.post(f"/platform-orders/{po['order_id']}/reject", {"reason": "Out of beef"}).json()["acceptance"] == "Rejected"
    assert c.get(f"/orders/{po['order_id']}").json()["order_status"] == "Cancelled"
    process_outbox()
    assert grab[-1] == ("/grabfood/partner/v1/order/prepare", {"orderID": "R-1", "toState": "Rejected"})
    # AUTO: Grab already accepted, so RMS accepts and sends straight away without calling Grab back
    submit(client, h, grab_order(m, ref="A-1", mode="AUTO", total=100))
    auto = next(x for x in c.get("/platform-orders").json() if x["platform_ref"] == "A-1")
    assert auto["acceptance"] == "Accepted" and "Grab total" in auto["mismatch_note"]  # 1 KHR from Grab vs 20.90 USD in RMS
    assert process_outbox() == 0
    # unknown merchant and unmapped menu IDs
    assert submit(client, h, {**grab_order(m, ref="X-1"), "merchantID": "1-OTHER"}).status_code == 404
    assert submit(client, h, grab_order(m, ref="U-1", item_id="LOKLAK-02")).json()["status"] == "needs_manual_entry"
    log = gm.get("/integrations/grabfood/inbound?outcome=unmapped").json()
    assert log[0]["order"] == "U-1" and "LOKLAK-02" in log[0]["detail"]
    assert gm.post("/platform-item-maps", {"external_id": "LOKLAK-02", "variant_id": m["MN-02"]["variants"]["Regular"]}).status_code == 201
    assert submit(client, h, grab_order(m, ref="U-2", item_id="LOKLAK-02")).json()["status"] == "received"


def test_grab_cancellation_notifies_manager(api, client, grab):
    c = api("cashier")
    m = menu(c)
    h = bearer(client)
    submit(client, h, grab_order(m, ref="C-1", mode="AUTO"))
    st = client.put("/api/v1/integrations/grabfood/order/state", json={"merchantID": MERCHANT, "orderID": "C-1", "state": "CANCELLED", "message": "Driver unavailable"},
                    headers=h).json()
    assert st["status"] == "manager_notified"
    notes = api("supv").get("/notifications").json()
    assert any("Grab cancelled order GF-123" in (n.get("title") or "") for n in (notes.get("data") if isinstance(notes, dict) else notes))
    assert client.put("/api/v1/integrations/grabfood/order/state", json={"orderID": "nope", "state": "DELIVERED"}, headers=h).json()["status"] == "unknown_order"
    assert str(uuid.uuid4())


def test_menu_sync(api, client, grab, engine):
    from sqlalchemy import text

    from app.workers.celery_app import process_outbox

    gm, km = api("gm"), api("kmgr")
    m = menu(gm)
    h = bearer(client)
    assert client.get("/api/v1/integrations/grabfood/merchant/menu?partnerMerchantID=RVS&merchantID=x").status_code == 401
    # first contact during activation: the Grab merchant ID arrives in GetMenu and is stored for the branch
    gm.put("/settings/grabfood", {"value": {"merchant_id": None}})
    r = client.get(f"/api/v1/integrations/grabfood/merchant/menu?merchantID={MERCHANT}&partnerMerchantID=RVS&BusinessType=0", headers=h)
    assert r.status_code == 200, r.json()
    body = r.json()
    assert gm.get("/settings/grabfood").json()["value"]["merchant_id"] == MERCHANT
    assert body["currency"] == {"code": "KHR", "symbol": "៛", "exponent": 2} and body["partnerMerchantID"] == "RVS" and len(body["sellingTimes"]) == 1
    items = {i["id"]: i for c in body["categories"] for i in c["items"]}
    loklak = items[str(m["MN-02"]["variants"]["Regular"])]
    assert loklak["price"] == 4280000  # 9.50 + 10 % tax = 10.45 USD x 4,100 = 42,845 -> 42,800 KHR (100-riel steps), x 100 minor units
    assert loklak["nameTranslation"]["en"] == "Beef Lok Lak" and loklak["availableStatus"] == "AVAILABLE"
    assert all(1 <= len(c["items"]) <= 300 for c in body["categories"]) and all(c["sellingTimeID"] == "rms-opening-hours" for c in body["categories"])
    assert client.get("/api/v1/integrations/grabfood/merchant/menu?partnerMerchantID=NOPE", headers=h).status_code == 404
    # ask Grab to pull the menu
    assert gm.post("/integrations/grabfood/menu/sync").status_code == 202
    assert process_outbox() == 1 and grab[-1] == ("/grabfood/partner/v1/merchant/menu/notification", {"merchantID": MERCHANT})
    # 86 goes to Grab immediately as a menu record update
    km.post(f"/menu-items/{m['MN-02']['id']}/availability", {"available": False, "reason": "Out of beef"})
    process_outbox()
    path, payload = grab[-1]
    assert path == "/grabfood/partner/v1/menu" and payload["availableStatus"] == "UNAVAILABLE" and payload["maxStock"] == 0 and payload["field"] == "ITEM"
    preview = {i["id"]: i for c in gm.get("/integrations/grabfood/menu/preview").json()["categories"] for i in c["items"]}
    assert preview[str(m["MN-02"]["variants"]["Regular"])]["availableStatus"] == "UNAVAILABLE"
    # sync state webhook: failures alert menu managers, repeats are ignored
    st = {"requestID": "6b5e362a-caa1-4858-908b-dae145d317bc", "merchantID": MERCHANT, "partnerMerchantID": "RVS", "jobID": "j1", "status": "FAILED",
          "errors": ["item name too long"]}
    assert client.post("/api/v1/integrations/grabfood/menu-sync-state", json=st, headers=h).json()["status"] == "recorded"
    assert client.post("/api/v1/integrations/grabfood/menu-sync-state", json=st, headers=h).json()["status"] == "duplicate"
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from notifications where title = 'Grab menu sync failed'")).scalar() >= 1
