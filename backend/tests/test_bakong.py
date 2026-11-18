"""Bakong KHQR online payment. Bakong itself is mocked with the response shapes from NBC's Open API document v1.0.1;
the CRC is checked against the KHQR sample in that document. No real Bakong call is made."""
import json
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

from app.core import ratelimit
from app.core.config import get_settings
from app.integrations import bakong
from tests.helpers import line, menu, money
from tests.test_online import cart, enable, pub

NBC_SAMPLE = "00020101021229190015gg_hh_1980@amkb52045999530384054031685802KH5905Gg Hh6010Phnom Penh62100806#hello630498B8"


def test_crc_matches_nbc_sample_and_khqr_fields():
    assert bakong.crc16(NBC_SAMPLE[:-4]) == "98B8"
    assert bakong.parse(NBC_SAMPLE)["29"] == "0015gg_hh_1980@amkb"
    qr = bakong.build_khqr(account_id="rms_test@devb", merchant_name="Riverside", merchant_city="Phnom Penh", amount=Decimal("10.45"), currency="USD",
                           bill_number="RVS261117-0001", store_label="Riverside", created_ms=1763380000000)
    f = bakong.parse(qr)
    assert qr.startswith("000201010212") and f["29"] == "0013rms_test@devb" and f["52"] == "5999" and f["53"] == "840" and f["54"] == "10.45"
    assert f["58"] == "KH" and f["59"] == "Riverside" and f["60"] == "Phnom Penh" and f["62"] == "0114RVS261117-00010309Riverside"
    assert f["99"] == "00131763380000000" and len(bakong.md5(qr)) == 32
    khr = bakong.parse(bakong.build_khqr(account_id="a@b", merchant_name="X", merchant_city="PP", amount=Decimal("41000"), currency="KHR", bill_number="1"))
    assert khr["53"] == "116" and khr["54"] == "41000"
    corp = bakong.parse(bakong.build_khqr(account_id="khqr@devb", merchant_type="merchant", merchant_id="013345168", acquiring_bank="Dev Bank",
                                          merchant_name="Coffee", merchant_city="PP", amount=Decimal("1"), currency="USD", bill_number="1"))
    assert corp["30"] == "0009khqr@devb01090133451680208Dev Bank"
    with pytest.raises(bakong.KhqrError):
        bakong.build_khqr(account_id="a@b", merchant_name="A name that is far too long for KHQR", merchant_city="PP", amount=Decimal("1"), currency="USD", bill_number="1")
    with pytest.raises(bakong.KhqrError):
        bakong.parse(NBC_SAMPLE[:-4] + "0000")


@pytest.fixture()
def fake_bakong(monkeypatch):
    s = get_settings()
    for k, v in {"PAYMENT_GATEWAY": "bakong", "BAKONG_ACCOUNT_ID": "rms_test@devb", "BAKONG_MERCHANT_NAME": "Riverside", "BAKONG_API_TOKEN": "test-token",
                 "BAKONG_API_URL": "https://sit-api-bakong.example"}.items():
        monkeypatch.setattr(s, k, v)
    state = {"calls": 0, "reply": {}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/check_transaction_by_md5" and request.headers["Authorization"] == "Bearer test-token"
        state["calls"] += 1
        state["last_md5"] = json.loads(request.content)["md5"]
        if state.get("http"):
            return httpx.Response(state["http"])
        return httpx.Response(200, json=state["reply"].get(state["last_md5"], {"data": None, "errorCode": 1, "responseCode": 1,
                                                                              "responseMessage": "Transaction could not be found. Please check and try again."}))

    monkeypatch.setattr(bakong, "TRANSPORT", httpx.MockTransport(handler))
    ratelimit.reset()
    return state


def paid(md5, amount="10.45", to="rms_test@devb", currency="USD"):
    return {md5: {"responseCode": 0, "responseMessage": "Getting transaction successfully.",
                  "data": {"hash": "8465d722d7d5065f2886f0a474a4d34dc6a7855355b611836f7b6111228893e9", "fromAccountId": "payer@abaa", "toAccountId": to,
                           "currency": currency, "amount": float(amount), "description": "RMS"}}}


def test_khqr_checkout_poll_and_record(api, client, fake_bakong):
    from app.workers.celery_app import poll_khqr_payments

    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    o = pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key=str(uuid.uuid4())).json()
    p = o["payment"]
    assert p["kind"] == "khqr" and p["md5"] == bakong.md5(p["qr"]) and bakong.parse(p["qr"])["54"] == "10.45"
    st = pub(client, "GET", f"/track/{o['tracking_token']}/payment").json()
    assert st["payment_status"] == "Pending" and st["check"] == "pending" and st["qr"] == p["qr"] and fake_bakong["calls"] == 1
    pub(client, "GET", f"/track/{o['tracking_token']}/payment")
    assert fake_bakong["calls"] == 1  # throttled: at most one Bakong check every 3 seconds per order
    fake_bakong["reply"] = paid(p["md5"])
    assert poll_khqr_payments() == {"paid": 1}
    order = c.get(f"/orders/{o['order_id']}").json()
    assert order["payment_status"] == "Paid" and money(order["totals"]["paid"]) == Decimal("10.45")
    pays = c.get(f"/orders/{o['order_id']}/bills").json()[0]
    assert pays["status"] == "Paid"
    assert pub(client, "GET", f"/track/{o['tracking_token']}/payment").json()["payment_status"] == "Paid"
    oo = c.get("/online-orders").json()[0]
    assert c.post(f"/online-orders/{oo['id']}/accept").json()["status"] == "Accepted"


def test_khqr_wrong_receiver_amount_and_unavailable(api, client, fake_bakong, engine):
    from app.workers.celery_app import poll_khqr_payments

    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    a = pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key=str(uuid.uuid4())).json()
    b = pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key=str(uuid.uuid4())).json()
    fake_bakong["reply"] = {**paid(a["payment"]["md5"], to="someone_else@abaa"), **paid(b["payment"]["md5"], amount="1.00")}
    assert poll_khqr_payments() == {"failed": 2}
    for o in (a, b):
        assert c.get(f"/orders/{o['order_id']}").json()["payment_status"] == "Unpaid"
    assert api("auditor").get("/audit-logs?action=online.payment_wrong_receiver").json()["total"] == 1
    assert api("auditor").get("/audit-logs?action=online.payment_mismatch").json()["total"] == 1
    # Bakong down or blocking us: nothing changes, it's retried later
    d = pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key=str(uuid.uuid4())).json()
    fake_bakong["http"] = 403
    assert pub(client, "GET", f"/track/{d['tracking_token']}/payment").json()["check"] == "unavailable"
    fake_bakong.pop("http")


def test_khqr_expiry_and_new_code(api, client, fake_bakong, engine):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    enable(gm)
    o = pub(client, "POST", "/branches/RVS/orders", cart(m, payment="Online"), key=str(uuid.uuid4())).json()
    assert pub(client, "POST", f"/track/{o['tracking_token']}/payment").json()["error"]["code"] == "PAYMENT_STILL_OPEN"
    with engine.begin() as conn:
        conn.execute(text("update online_orders set gateway_expires_at = now() - interval '1 minute', gateway_checked_at = null"))
    assert pub(client, "GET", f"/track/{o['tracking_token']}/payment").json()["check"] == "expired"
    fresh = pub(client, "POST", f"/track/{o['tracking_token']}/payment").json()
    assert fresh["md5"] != o["payment"]["md5"] and bakong.parse(fresh["qr"])["54"] == "10.45"
    assert pub(client, "GET", f"/track/{o['tracking_token']}/payment").json()["payment_status"] == "Pending"
