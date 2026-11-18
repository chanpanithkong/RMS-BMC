"""SRS §16.1 (DASH), §16.17 (RPT), §16.20 (CFG) and real-time delivery."""
from datetime import datetime, timedelta, timezone

from tests.helpers import line, menu, money


def paid_order(c, m):
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "MN-02", 1)]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": f"KQ-{o['order_no']}"}, idem=True)
    return o, bill


def test_at_dash_01_02_role_widgets(api):
    c, owner = api("cashier"), api("owner")
    m = menu(c)
    paid_order(c, m)
    d = owner.get("/dashboard").json()["widgets"]
    s = d["sales"]
    assert money(s["gross_sales"]) == money("9.50") and money(s["net_sales"]) == money("9.50") and money(s["taxes"]) == money("0.95")
    assert money(s["net_sales"]) == money(s["gross_sales"]) - money(s["discounts"]) - money(s["refunds"])  # tax and service not in net
    assert d["orders"]["completed"] == 0 and d["payments_by_method"][0]["method"] == "KHQR"
    cashier_view = c.get("/dashboard").json()["widgets"]
    assert "sales" not in cashier_view and "payments_by_method" not in cashier_view
    assert api("waiter").get("/dashboard").status_code == 403


def test_reports_and_export(api):
    c, acct = api("cashier"), api("acct")
    m = menu(c)
    paid_order(c, m)
    r = acct.get("/reports/RPT-04").json()
    assert r["rows"][0]["name"] == "Beef Lok Lak" and money(r["rows"][0]["net_sales"]) == money("9.50")
    r14 = acct.get("/reports/RPT-14").json()
    assert {x["charge_type"] for x in r14["rows"]} == {"Tax"} and "illustrative" in r14["summary"]["basis"]
    exp = acct.get("/reports/RPT-07/export")
    assert exp.status_code == 200 and "KHQR" in exp.text
    assert acct.get("/reports/RPT-07/export?format=xlsx").status_code == 501
    assert c.get("/reports/RPT-01").status_code == 403
    assert acct.get("/reports/RPT-99").status_code == 404
    assert api("auditor").get("/audit-logs?action=report.export").json()["total"] == 1


def test_at_cfg_tax_change_needs_approval_and_future_date(api):
    gm, owner = api("gm"), api("owner")
    profile = owner.get("/tax-profiles").json()[0]
    body = {"charge_kind": "Tax", "name": "Tax", "rate": "0.10", "base_rule": "SubtotalPlusServiceCharge", "applies_to_order_types": ["DineIn"],
            "valid_from": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}
    assert gm.post(f"/tax-profiles/{profile['id']}/rates", body).status_code == 403
    past = {**body, "valid_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    assert owner.post(f"/tax-profiles/{profile['id']}/rates", past).json()["error"]["code"] == "EFFECTIVE_IN_PAST"
    assert owner.post(f"/tax-profiles/{profile['id']}/rates", body).status_code == 201
    rates = [r for r in owner.get("/tax-profiles").json()[0]["rates"] if r["charge_kind"] == "Tax"]
    assert len(rates) == 2 and any(r["valid_to"] for r in rates)
    assert all(r["verified"] is False for r in rates)


def test_exchange_rate_and_khr_blocked_without_rate(api, engine):
    from sqlalchemy import text

    c, acct = api("cashier"), api("acct")
    m = menu(c)
    with engine.begin() as conn:
        conn.execute(text("update exchange_rates set effective_from = now() + interval '10 days'"))
    c.post("/cashier-sessions", {"floats": {"USD": "10", "KHR": "0"}})
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "DR-03")]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    r = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_KHR", "currency": "KHR", "amount_tendered": "10000"}, idem=True)
    assert r.json()["error"]["code"] == "EXCHANGE_RATE_MISSING"
    assert acct.post("/exchange-rates", {"rate": "4050", "effective_from": datetime.now(timezone.utc).isoformat(), "source": "Bank board"}).status_code == 201
    r = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_KHR", "currency": "KHR", "amount_tendered": "10000"}, idem=True)
    assert r.status_code == 201 and money(r.json()["rate"]) == money("4050")


def test_day_end_blocks_with_open_items(api):
    gm, c = api("gm"), api("cashier")
    c.post("/cashier-sessions", {"floats": {"USD": "10"}})
    r = gm.post("/day-end/close", {})
    assert r.status_code == 409 and r.json()["error"]["open_sessions"] == 1
    r = gm.post("/day-end/close", {"acknowledge_open_items": True, "reason": "Late cashier"})
    assert r.json()["closed"] is True
    m = menu(c)
    r = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "DR-03")]}, idem=True)
    assert r.json()["error"]["code"] == "BUSINESS_DAY_CLOSED"


def test_websocket_pushes_kitchen_ticket(api, client):
    c = api("cashier")
    cook = api("cook")
    m = menu(c)
    branch = c.get("/auth/me").json()["current_branch"]["id"]
    with client.websocket_connect(f"/api/v1/ws?token={cook.token}") as ws:
        ws.send_json({"action": "subscribe", "topic": f"station:{branch}:HOT"})
        assert ws.receive_json()["type"] == "subscribed"
        ws.send_json({"action": "subscribe", "topic": "user:someone-else"})
        assert ws.receive_json()["code"] == "TOPIC_FORBIDDEN"
        o = c.post("/orders", {"order_type": "DineIn", "table_tag": "3", "items": [line(m, "RN-01", 1, ("Mild",))]}, idem=True).json()
        c.post(f"/orders/{o['id']}/send", idem=True)
        event = ws.receive_json()
        assert event["type"] == "kitchen.ticket.created" and event["data"]["order_id"] == o["id"]


def test_websocket_rejects_bad_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws?token=nope") as ws:
            ws.receive_json()


def test_outbox_worker_delivers_password_reset(client, engine):
    from sqlalchemy import text

    from app.workers.celery_app import process_outbox

    client.post("/api/v1/auth/password/forgot", json={"email_or_username": "cashier"})
    assert process_outbox() == 1
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from outbox_events where processed_at is null")).scalar() == 0


def test_rpt02_compares_with_previous_month(api, engine):
    from datetime import date as _date

    from sqlalchemy import text

    from app.services.reports import shift_month

    c, acct = api("cashier"), api("acct")
    m = menu(c)
    biz = _date.fromisoformat(acct.get("/auth/me").json()["business_date"])
    paid_order(c, m)  # 9.50 today
    o2 = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "B", "items": [line(m, "MN-02", 2)]}, idem=True).json()
    b2 = c.post(f"/orders/{o2['id']}/bills", {"mode": "single"}).json()[0]
    c.post("/payments", {"bill_id": b2["id"], "method": "KHQR", "currency": "USD", "reference": "KQ-PREV"}, idem=True)
    prev_day = shift_month(biz)
    with engine.begin() as conn:  # that sale belongs to the same day last month
        conn.execute(text("update bills set business_date = :d where id = :b"), {"d": prev_day, "b": b2["id"]})
    r = acct.get(f"/reports/RPT-02?date_from={biz}&date_to={biz}").json()
    s = r["summary"]
    assert money(s["net_sales"]) == money("9.50") and money(s["previous_period"]["net_sales"]) == money("19.00")
    assert s["previous_period"]["from"] == prev_day.isoformat() == s["previous_period"]["to"]
    assert money(s["change"]["net_sales"]["amount"]) == money("-9.50") and money(s["change"]["net_sales"]["percent"]) == money("-50.00")
    row = r["rows"][0]
    assert row["business_date"] == biz.isoformat() and money(row["previous_month_net_sales"]) == money("19.00")
    assert "completed_orders" in row and "average_order_value" in row
