"""SRS §16.13 (EXP) and §16.14 (STAFF)."""
from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import money


def cat(u, name):
    return next(c["id"] for c in u.get("/expense-categories").json() if c["name_en"] == name)


def test_at_exp_01_approval_required_and_separation(api):
    s, gm, owner = api("supv"), api("gm"), api("owner")
    e = s.post("/expenses", {"category_id": cat(s, "Water"), "expense_date": date.today().isoformat(), "description": "Pump repair", "amount": "120.00", "payee": "Plumber"}).json()
    r = s.post(f"/expenses/{e['id']}/submit").json()
    assert r["status"] == "Submitted"
    assert s.post(f"/expenses/{e['id']}/decision", {"approve": True}).status_code == 403  # no expenses.approve
    assert gm.post(f"/expenses/{e['id']}/decision", {"approve": True}).json()["status"] == "Approved"
    small = s.post("/expenses", {"category_id": cat(s, "Water"), "expense_date": date.today().isoformat(), "description": "Bottled water", "amount": "20", "payee": "Shop"}).json()
    assert s.post(f"/expenses/{small['id']}/submit").json()["status"] == "Approved"  # within the 50.00 limit
    own = gm.post("/expenses", {"category_id": cat(gm, "Water"), "expense_date": date.today().isoformat(), "description": "Big", "amount": "2500", "payee": "X"}).json()
    gm.post(f"/expenses/{own['id']}/submit")
    assert gm.post(f"/expenses/{own['id']}/decision", {"approve": True}).json()["error"]["code"] == "SELF_APPROVAL"
    assert owner.post(f"/expenses/{own['id']}/decision", {"approve": False}).json()["error"]["code"] == "REASON_REQUIRED"
    assert owner.post(f"/expenses/{own['id']}/decision", {"approve": False, "reason": "Not budgeted"}).json()["status"] == "Rejected"
    future = s.post("/expenses", {"category_id": cat(s, "Water"), "expense_date": (date.today() + timedelta(days=5)).isoformat(), "description": "Prepaid gas", "amount": "1", "payee": "x"})
    assert future.json()["error"]["code"] == "EXPENSE_DATE_FUTURE"


def test_at_exp_02_paid_out_from_drawer(api):
    s, c = api("supv"), api("cashier")
    sess = c.post("/cashier-sessions", {"floats": {"USD": "50", "KHR": "0"}}).json()
    e = s.post("/expenses", {"category_id": cat(s, "Cleaning supplies"), "expense_date": date.today().isoformat(), "description": "Cleaner", "amount": "15.00", "payee": "Shop"}).json()
    s.post(f"/expenses/{e['id']}/submit")
    r = c.post(f"/expenses/{e['id']}/pay", {"method": "CASH_DRAWER"}).json()
    assert r["status"] == "Paid"
    closed = c.post(f"/cashier-sessions/{sess['id']}/close", {"counts": {"USD": "35", "KHR": "0"}}).json()
    usd = next(x for x in closed["results"] if x["currency"] == "USD")
    assert money(usd["expected"]) == Decimal("35") and money(usd["variance"]) == 0
    assert c.post(f"/expenses/{e['id']}/pay", {"method": "CASH_DRAWER"}).json()["error"]["code"] == "EXPENSE_NOT_APPROVED"


def test_at_exp_03_attachment_rule(api):
    s = api("supv")
    e = s.post("/expenses", {"category_id": cat(s, "Equipment repairs"), "expense_date": date.today().isoformat(), "description": "Freezer", "amount": "40", "payee": "CoolTech"}).json()
    r = s.post(f"/expenses/{e['id']}/submit")
    assert r.status_code == 422 and r.json()["error"]["code"] == "ATTACHMENT_REQUIRED"
    bad = s.post(f"/expenses/{e['id']}/attachments", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert bad.json()["error"]["code"] == "FILE_TYPE"
    ok = s.post(f"/expenses/{e['id']}/attachments", files={"file": ("quote.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert ok.status_code == 201
    assert s.post(f"/expenses/{e['id']}/submit").json()["status"] == "Approved"
    dl = api("acct").get(f"/expenses/{e['id']}/attachments/{ok.json()['id']}")
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF")
    assert api("waiter").get(f"/expenses/{e['id']}/attachments/{ok.json()['id']}").status_code == 403


def test_at_staff_01_expected_cash_from_srs_example(api, engine):
    """SRS §6.14: float 50 USD / 100,000 KHR; retained 420 USD and 312,300 KHR; 10 USD refund; 15 USD paid-out → 445 USD / 412,300 KHR."""
    import uuid

    from sqlalchemy import text

    c = api("cashier")
    s = c.post("/cashier-sessions", {"floats": {"USD": "50", "KHR": "100000"}}).json()
    with engine.begin() as conn:  # posted payments and a completed cash refund, inserted directly to reproduce the illustration
        ids = conn.execute(text("select (select id from payment_methods where code='CASH_USD'), (select id from payment_methods where code='CASH_KHR'), (select id from users where username='cashier'), (select id from branches limit 1)")).one()
        order = conn.execute(text("insert into orders (id, branch_id, business_date, order_no, order_type, channel, order_status, kitchen_status, payment_status, server_user_id, currency, version, gross_total, discount_total, subtotal, service_charge_total, tax_total, delivery_fee, rounding_total, grand_total) values (:i, :b, current_date, 'X1', 'Takeaway', 'POS', 'Open', 'NotSent', 'Paid', :u, 'USD', 1, 0,0,0,0,0,0,0,0) returning id"),
                             {"i": uuid.uuid4(), "b": ids[3], "u": ids[2]}).scalar()
        bill = conn.execute(text("insert into bills (id, branch_id, business_date, order_id, bill_no, split_index, split_count, status, gross_total, discount_total, subtotal, service_charge_total, tax_total, delivery_fee, rounding_total, total, paid_total, refunded_total, balance, currency, printed_count, version) values (:i, :b, current_date, :o, 'BX1', 1, 1, 'Paid', 0,0,0,0,0,0,0,0,0,0,0,'USD',0,1) returning id"),
                            {"i": uuid.uuid4(), "b": ids[3], "o": order}).scalar()
        pay = "insert into payments (id, branch_id, business_date, bill_id, method_id, method_code, currency, amount_tendered, amount_applied, change_amount, change_currency, amount_base, rounding_base, refunded_base, status, cashier_session_id, idempotency_key, received_by) values (:i, :b, current_date, :bill, :m, :mc, :cur, :t, :t, :ch, :chc, 1, 0, 0, 'Confirmed', :s, :k, :u)"
        conn.execute(text(pay), {"i": uuid.uuid4(), "b": ids[3], "bill": bill, "m": ids[0], "mc": "CASH_USD", "cur": "USD", "t": "420", "ch": "0", "chc": None, "s": s["id"], "k": "srs-a", "u": ids[2]})
        conn.execute(text(pay), {"i": uuid.uuid4(), "b": ids[3], "bill": bill, "m": ids[1], "mc": "CASH_KHR", "cur": "KHR", "t": "320000", "ch": "7700", "chc": "KHR", "s": s["id"], "k": "srs-b", "u": ids[2]})
        conn.execute(text("insert into refunds (id, branch_id, business_date, refund_no, payment_id, bill_id, amount_base, currency, amount, method_code, reason, requested_by, status, cashier_session_id) select :i, :b, current_date, 'RF-X', id, :bill, 10, 'USD', 10, 'CASH_USD', 'x', :u, 'Completed', :s from payments where idempotency_key='srs-a'"),
                     {"i": uuid.uuid4(), "b": ids[3], "bill": bill, "u": ids[2], "s": s["id"]})
    c.post(f"/cashier-sessions/{s['id']}/cash-movements", {"kind": "PaidOut", "currency": "USD", "amount": "15", "reason": "Supplier"})
    r = c.post(f"/cashier-sessions/{s['id']}/close", {"counts": {"USD": "440", "KHR": "412300"}}).json()
    res = {x["currency"]: x for x in r["results"]}
    assert money(res["USD"]["expected"]) == Decimal("445") and money(res["KHR"]["expected"]) == Decimal("412300")
    assert money(res["USD"]["variance"]) == Decimal("-5") and money(res["KHR"]["variance"]) == 0
    assert r["status"] == "ClosingPendingApproval"  # AT-STAFF-02: beyond the 1.00 USD tolerance


def test_employees_schedule_and_user_link(api, seeded):
    gm = api("gm")
    dept = gm.get("/departments").json()[0]["id"]
    e = gm.post("/employees", {"employee_code": "E-100", "name_en": "Lina Chhay", "name_km": "ឆាយ លីណា", "department_id": dept, "start_date": "2026-01-02",
                               "user_id": str(seeded["users"]["cashier2"])}).json()
    assert e["user_id"] == str(seeded["users"]["cashier2"])
    other = gm.post("/employees", {"employee_code": "E-101", "name_en": "X", "start_date": "2026-01-02"}).json()
    assert gm.patch(f"/employees/{other['id']}", {"user_id": str(seeded["users"]["cashier2"])}).json()["error"]["code"] == "USER_ALREADY_LINKED"
    monday = date.today() - timedelta(days=date.today().weekday())
    assert gm.post("/shift-schedules", {"employee_id": e["id"], "shift_date": monday.isoformat(), "start_time": "08:00", "end_time": "16:00"}).status_code == 201
    r = gm.post("/shift-schedules", {"employee_id": e["id"], "shift_date": monday.isoformat(), "start_time": "15:00", "end_time": "22:00"})
    assert r.json()["error"]["code"] == "SHIFT_OVERLAP"
    assert len(gm.get(f"/shift-schedules?week_start={monday.isoformat()}").json()) == 1
    assert gm.post(f"/employees/{e['id']}/clock-in").status_code == 200
    assert gm.post(f"/employees/{e['id']}/clock-in").json()["error"]["code"] == "ALREADY_CLOCKED_IN"
    assert gm.post(f"/employees/{e['id']}/clock-out").status_code == 200
    att = gm.get("/attendance").json()
    assert att[0]["employee_id"] == e["id"] and att[0]["clock_out"] and att[0]["hours"] is not None
    # BR-051: deactivating the employee deactivates the linked user
    gm.patch(f"/employees/{e['id']}", {"status": "Inactive"})
    assert gm.get(f"/users/{seeded['users']['cashier2']}").json()["status"] == "Inactive"
    assert api("waiter").post("/employees", {"employee_code": "E-9", "name_en": "x", "start_date": "2026-01-01"}).status_code == 403
