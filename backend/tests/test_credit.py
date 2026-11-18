"""Customer credit accounts (FR-CUST-011, FR-BILL-017, BR-036) with the owner's D-07 rules: Owner/GM/Accountant open accounts,
30-day terms by default, manager approval over the limit, overdue accounts blocked without a manager."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

from tests.helpers import line, menu, money
from tests.test_billing_cash import open_session


def setup(api, limit="50"):
    gm, c, acct = api("gm"), api("cashier"), api("acct")
    assert gm.put("/settings/credit", {"value": {"enabled": True}}).status_code == 200
    cust = c.post("/customers", {"name": "Mekong Trading Co.", "phone": "023 999 111"}).json()
    assert c.post("/credit-accounts", {"customer_id": cust["id"], "credit_limit": limit}).status_code == 403
    a = acct.post("/credit-accounts", {"customer_id": cust["id"], "credit_limit": limit, "company_name": "Mekong Trading Co."}).json()
    assert a["terms_days"] == 30 and money(a["available"]) == Decimal(limit)
    return cust, a


def bill_for(c, m, qty=1):
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "Office", "items": [line(m, "MN-02", qty)]}, idem=True).json()
    return o, c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]


def approval(u, bill, amount, who="gm", pin="5937"):
    r = u.post("/approvals", {"action": "credit_override", "approver_username": who, "approver_secret": pin, "amount": amount, "target_id": bill["id"]})
    return r


def test_charge_limit_overdue_and_statement(api, engine):
    c = api("cashier")
    m = menu(c)
    cust, a = setup(api)
    o, bill = bill_for(c, m)
    r = c.post(f"/bills/{bill['id']}/charge-to-account", {"account_id": a["id"]}).json()
    assert money(r["account"]["balance"]) == Decimal("10.45") and r["due_date"] == (date.today() + timedelta(days=30)).isoformat()
    order = c.get(f"/orders/{o['id']}").json()
    assert order["payment_status"] == "Paid"
    assert c.get(f"/orders/{o['id']}/bills").json()[0]["status"] == "Paid"
    # over the limit: 10.45 owed + 41.80 > 50 -> a manager must approve
    o2, bill2 = bill_for(c, m, qty=4)
    res = c.post(f"/bills/{bill2['id']}/charge-to-account", {"account_id": a["id"]}).json()
    assert res["error"]["code"] == "APPROVAL_REQUIRED" and res["error"]["action"] == "credit_override"
    assert approval(c, bill2, "41.80", "supv", "7314").json()["error"]["code"] == "APPROVER_NOT_PERMITTED"
    appr = approval(c, bill2, "41.80").json()
    r2 = c.post(f"/bills/{bill2['id']}/charge-to-account", {"account_id": a["id"], "approval_id": appr["approval_id"]}).json()
    assert "account" in r2, r2
    assert money(r2["account"]["balance"]) == Decimal("52.25") and money(r2["account"]["available"]) == 0
    # overdue: the first charge is now past due, so even a small charge needs a manager
    with engine.begin() as conn:
        conn.execute(text("update credit_transactions set due_date = current_date - 5 where amount = 10.45"))
    api("acct").patch(f"/credit-accounts/{a['id']}", {"credit_limit": "500"})
    o3, bill3 = bill_for(c, m)
    assert c.post(f"/bills/{bill3['id']}/charge-to-account", {"account_id": a["id"]}).json()["error"]["code"] == "APPROVAL_REQUIRED"
    acc = api("acct").get(f"/credit-accounts/{a['id']}").json()
    assert money(acc["overdue"]) == Decimal("10.45") and money(acc["ageing"]["1_30"]) == Decimal("10.45")
    # settle: oldest charge first; cash goes into the drawer
    assert c.post(f"/credit-accounts/{a['id']}/settlements", {"amount": "20", "method": "CASH_USD"}).json()["error"]["code"] == "CASHIER_SESSION_REQUIRED"
    open_session(c)
    assert c.post(f"/credit-accounts/{a['id']}/settlements", {"amount": "20", "method": "BANK_TRANSFER"}).json()["error"]["code"] == "REFERENCE_REQUIRED"
    assert c.post(f"/credit-accounts/{a['id']}/settlements", {"amount": "999", "method": "CASH_USD"}).json()["error"]["code"] == "SETTLEMENT_EXCEEDS_BALANCE"
    s = c.post(f"/credit-accounts/{a['id']}/settlements", {"amount": "20", "method": "CASH_USD"}).json()
    assert money(s["account"]["balance"]) == Decimal("32.25") and money(s["account"]["overdue"]) == 0  # the overdue 10.45 was paid first
    st = api("acct").get(f"/credit-accounts/{a['id']}/statement").json()
    assert money(st["opening_balance"]) == 0 and money(st["closing_balance"]) == Decimal("32.25")
    assert [x["kind"] for x in st["lines"]] == ["Charge", "Charge", "Settlement"]
    with engine.connect() as conn:
        assert conn.execute(text("select kind, amount from cash_movements")).one() == ("PaidIn", Decimal("20.0000"))


def test_refund_credits_account_and_rules(api):
    c, gm = api("cashier"), api("gm")
    m = menu(c)
    cust, a = setup(api)
    o, bill = bill_for(c, m)
    pay = c.post(f"/bills/{bill['id']}/charge-to-account", {"account_id": a["id"]}).json()["payment"]
    rf = c.post("/refunds", {"payment_id": pay["payment_id"], "amount": "5.00", "reason": "Cold food"}, idem=True).json()
    gm.post(f"/refunds/{rf['id']}/approve", {})
    acc = api("acct").get(f"/credit-accounts/{a['id']}").json()
    assert money(acc["balance"]) == Decimal("5.45")
    # an order for another customer can't go on this account
    other = c.post("/customers", {"name": "Someone Else", "phone": "012 444 555"}).json()
    o2, bill2 = bill_for(c, m)
    c.post(f"/customers/attach/{o2['id']}", {"customer_id": other["id"]})
    assert c.post(f"/bills/{bill2['id']}/charge-to-account", {"account_id": a["id"]}).json()["error"]["code"] == "CREDIT_ACCOUNT_MISMATCH"
    # closing needs a zero balance; suspended accounts can't be charged
    assert api("acct").patch(f"/credit-accounts/{a['id']}", {"status": "Closed"}).json()["error"]["code"] == "CREDIT_BALANCE_OUTSTANDING"
    api("acct").patch(f"/credit-accounts/{a['id']}", {"status": "Suspended"})
    o3, bill3 = bill_for(c, m)
    assert c.post(f"/bills/{bill3['id']}/charge-to-account", {"account_id": a["id"]}).json()["error"]["code"] == "CREDIT_ACCOUNT_INACTIVE"
    gm.put("/settings/credit", {"value": {"enabled": False}})
    assert c.post(f"/bills/{bill3['id']}/charge-to-account", {"account_id": a["id"]}).json()["error"]["code"] == "CREDIT_DISABLED"
