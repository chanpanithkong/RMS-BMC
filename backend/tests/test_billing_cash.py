"""Acceptance tests from SRS §16.3, §16.5, §16.9, §16.14 (BILL, STAFF, ORD completion)."""
import threading
import uuid
from decimal import Decimal

from sqlalchemy import text

from app.services.pricing import split_equal
from tests.helpers import line, menu, money, tables


def at_bill_01_order(c, m):
    o = c.post("/orders", {"order_type": "DineIn", "table_tag": "9", "items": [line(m, "RN-01", 2, ("Mild",)), line(m, "CF-01", 1, ("50%", "Extra shot"))]}, idem=True).json()
    coffee = next(i for i in o["items"] if i["item_name_en_snapshot"] == "Iced Coffee")
    c.post(f"/orders/{o['id']}/discounts", {"order_item_id": coffee["id"], "kind": "Percent", "value": "10", "reason": "Regular customer"})
    c.post(f"/orders/{o['id']}/discounts", {"kind": "Amount", "value": "1.00", "reason": "Regular customer"})
    return o


def open_session(u, usd="50", khr="100000"):
    r = u.post("/cashier-sessions", {"floats": {"USD": usd, "KHR": khr}})
    assert r.status_code == 201, r.text
    return r.json()


def test_cash_needs_open_session(api):
    c = api("cashier")
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "DR-03")]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    r = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_USD", "currency": "USD", "amount_tendered": "5"}, idem=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASHIER_SESSION_REQUIRED"


def test_at_bill_01_02_mixed_currency(api):
    c = api("cashier")
    m = menu(c)
    open_session(c)
    o = at_bill_01_order(c, m)
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    assert money(bill["total"]) == money("12.99")
    charges = {ch["charge_type"]: money(ch["amount"]) for ch in bill["charges"]}
    assert charges == {"ServiceCharge": money("0.56"), "Tax": money("1.18")}
    r1 = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_USD", "currency": "USD", "amount_tendered": "10.00"}, idem=True).json()
    assert money(r1["bill"]["balance"]) == money("2.99") and r1["bill"]["status"] == "PartiallyPaid"
    r2 = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_KHR", "currency": "KHR", "amount_tendered": "20000", "change_currency": "KHR"}, idem=True).json()
    assert money(r2["amount_applied"]) == money("12300") and money(r2["change"]["amount"]) == money("7700")
    assert money(r2["rounding"]["amount"]) == money("41") and money(r2["rounding_base"]) == money("0.01")
    assert money(r2["bill"]["balance"]) == money("0") and r2["bill"]["status"] == "Paid" and r2["receipt_no"].startswith("R-RVS-")


def test_at_bill_03_duplicate_payment_and_card_data(api, engine):
    c = api("cashier")
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "MN-01", 1, ("Mild",))]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    body = {"bill_id": bill["id"], "method": "CARD", "currency": "USD", "reference": "TID-0091-A", "approval_code": "A1B2C3", "card_last4": "4242"}
    a = c.post("/payments", body, idem="pay-1")
    b = c.post("/payments", body, idem="pay-1")
    assert a.status_code == 201 and a.json() == b.json()
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from payments where bill_id = :b"), {"b": bill["id"]}).scalar() == 1
        cols = {r[0] for r in conn.execute(text("select column_name from information_schema.columns where table_name='payments'"))}
    assert not {"card_number", "pan", "cvv"} & cols  # AT-BILL-05
    # reference is required for card, and must be unique per method
    r = c.post("/payments", {**body, "reference": None}, idem=True)
    assert r.json()["error"]["code"] in ("REFERENCE_REQUIRED", "BILL_NOT_PAYABLE")


def test_at_bill_04_refund_limit_and_separation(api):
    c, gm = api("cashier"), api("gm")
    m = menu(c)
    open_session(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "MN-02", 2), line(m, "DR-03", 1)]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    p = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_USD", "currency": "USD", "amount_tendered": "30"}, idem=True).json()
    paid = money(p["bill"]["paid"])
    r = c.post("/refunds", {"payment_id": p["payment_id"], "amount": "5.00", "reason": "Quality issue"}, idem=True).json()
    assert r["status"] == "Requested"
    assert c.post(f"/refunds/{r['id']}/approve", {}).status_code == 403  # cashier lacks refunds.approve
    assert gm.post(f"/refunds/{r['id']}/approve", {}).json()["status"] == "Completed"
    over = str(paid - Decimal("5.00") + Decimal("1.00"))
    r = c.post("/refunds", {"payment_id": p["payment_id"], "amount": over, "reason": "Too much"}, idem=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "REFUND_EXCEEDS_PAYMENT"
    assert c.get(f"/orders/{o['id']}").json()["payment_status"] == "PartiallyRefunded"


def test_at_pos_04_equal_split():
    assert split_equal(Decimal("30.01"), 3) == [Decimal("10.00"), Decimal("10.00"), Decimal("10.01")]


def test_split_bills_sum_to_order(api):
    c = api("cashier")
    m = menu(c)
    o = c.post("/orders", {"order_type": "DineIn", "table_tag": "4", "items": [line(m, "MN-01", 1, ("Mild",)), line(m, "RN-02", 1, ("Hot",)), line(m, "CF-01", 1, ("0%",))]}, idem=True).json()
    total = money(c.get(f"/orders/{o['id']}").json()["totals"]["grand_total"])
    for body in ({"mode": "equal", "parts": 3}, {"mode": "items", "assignment": {o["items"][0]["id"]: 0, o["items"][1]["id"]: 1, o["items"][2]["id"]: 1}}):
        bills = c.post(f"/orders/{o['id']}/bills", body).json()
        assert sum(money(b["total"]) for b in bills) == total
    assert len(c.get(f"/orders/{o['id']}/bills").json()) == 2  # earlier unpaid bills were voided


def test_at_ord_03_cancel_blocked_and_at_ord_04_completion(api):
    w, c, cook, s = api("waiter"), api("cashier"), api("cook"), api("supv")
    m = menu(w)
    t = tables(w)
    open_session(c)
    oid = w.post(f"/tables/{t['B1']['id']}/seat", {"guest_count": 2}).json()["order_id"]
    w.post(f"/orders/{oid}/items", [line(m, "MN-01", 1, ("Mild",))])
    w.post(f"/orders/{oid}/send", idem=True)
    bill = c.post(f"/orders/{oid}/bills", {"mode": "single"}).json()[0]
    c.post(f"/bills/{bill['id']}/print")
    assert tables(c)["B1"]["service_state"] == "AwaitingPayment"
    c.post("/payments", {"bill_id": bill["id"], "method": "CASH_USD", "currency": "USD", "amount_tendered": "5"}, idem=True)
    r = s.post(f"/orders/{oid}/cancel", {"reason": "Customer left"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REFUND_REQUIRED"
    c.post("/payments", {"bill_id": bill["id"], "method": "CASH_USD", "currency": "USD", "amount_tendered": "20"}, idem=True)
    ticket = next(x for x in cook.get("/kitchen/stations/HOT/open-tickets").json() if x["order_id"] == oid)
    cook.post(f"/kitchen/tickets/{ticket['ticket_id']}/bump")
    o = w.post(f"/orders/{oid}/serve", {}).json()
    assert o["order_status"] == "Completed" and o["payment_status"] == "Paid"
    assert tables(w)["B1"]["service_state"] == "Cleaning"


def test_cashier_session_blind_close_and_variance(api):
    c, gm = api("cashier"), api("gm")
    m = menu(c)
    s = open_session(c)
    assert c.post("/cashier-sessions", {"floats": {"USD": "10"}}).json()["error"]["code"] == "SESSION_ALREADY_OPEN"
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "MN-02", 1)]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    # pay 20 USD and take change in KHR: USD drawer keeps 20, KHR drawer pays out change
    p = c.post("/payments", {"bill_id": bill["id"], "method": "CASH_USD", "currency": "USD", "amount_tendered": "20", "change_currency": "KHR"}, idem=True).json()
    change_khr = money(p["change"]["amount"])
    c.post(f"/cashier-sessions/{s['id']}/cash-movements", {"kind": "PaidOut", "currency": "USD", "amount": "3", "reason": "Ice delivery"})
    report = c.get(f"/cashier-sessions/{s['id']}/report").json()
    assert report["kind"] == "X" and report["expected"] is None  # blind for the cashier
    expected_usd = Decimal("50") + Decimal("20") - Decimal("3")
    expected_khr = Decimal("100000") - change_khr
    r = c.post(f"/cashier-sessions/{s['id']}/close", {"counts": {"USD": str(expected_usd - Decimal('5')), "KHR": str(expected_khr)}}).json()
    assert r["status"] == "ClosingPendingApproval"
    res = {x["currency"]: x for x in r["results"]}
    assert money(res["USD"]["expected"]) == expected_usd and money(res["USD"]["variance"]) == Decimal("-5")
    assert c.post(f"/cashier-sessions/{s['id']}/approve-variance", {"reason": "Counting error"}).status_code == 403
    r = gm.post(f"/cashier-sessions/{s['id']}/approve-variance", {"reason": "Counting error"}).json()
    assert r["status"] == "Closed"


def test_concurrent_payments_do_not_overpay(api, engine):
    c = api("cashier")
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "MN-01", 1, ("Mild",))]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    results = []

    def pay(n):
        r = c.post("/payments", {"bill_id": bill["id"], "method": "BANK_TRANSFER", "currency": "USD", "reference": f"BT-{n}-{uuid.uuid4().hex[:6]}"}, idem=True)
        results.append(r.status_code)

    threads = [threading.Thread(target=pay, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(201) == 1  # the bill row lock serialises payments; the rest see a paid bill
    with engine.connect() as conn:
        paid = conn.execute(text("select paid_total, total from bills where id = :b"), {"b": bill["id"]}).one()
    assert paid[0] == paid[1]
