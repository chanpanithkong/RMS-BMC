"""Loyalty (FR-PROMO-011, FR-CUST-008) with the owner's rules: 1 point per 1.00 USD of net sales, 100 points = 1.00 USD off,
points expire 12 months after earning (oldest used first)."""
import math
from decimal import Decimal

from sqlalchemy import text

from tests.helpers import line, menu, money
from tests.test_delivery import bump_all


def enable(gm):
    assert gm.put("/settings/loyalty", {"value": {"enabled": True}}).status_code == 200


def takeaway_for(c, m, customer_id, qty=1, pay=True):
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "Loyal", "items": [line(m, "MN-02", qty)]}, idem=True).json()
    assert c.post(f"/customers/attach/{o['id']}", {"customer_id": customer_id}).status_code == 200
    return o


def complete(c, cook, o, ref):
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    p = c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": ref}, idem=True).json()
    c.post(f"/orders/{o['id']}/send", idem=True)
    bump_all(cook, o["id"])
    c.post(f"/orders/{o['id']}/serve", {})
    out = c.get(f"/orders/{o['id']}").json()
    assert out["order_status"] == "Completed"
    return out, p


def balance(u, cid):
    return u.get(f"/customers/{cid}/loyalty").json()["balance"]


def test_earn_redeem_reverse_and_fifo(api, engine):
    gm, c, cook, s = api("gm"), api("cashier"), api("cook"), api("supv")
    m = menu(c)
    cid = c.post("/customers", {"name": "Bopha", "phone": "017 222 333"}).json()["id"]
    o = takeaway_for(c, m, cid, qty=3)
    assert c.post(f"/orders/{o['id']}/loyalty-redemption", {"points": 100}).json()["error"]["code"] == "LOYALTY_DISABLED"
    complete(c, cook, o, "KQ-L1")
    assert balance(c, cid) == 0  # nothing earned while loyalty is off
    enable(gm)
    o = takeaway_for(c, m, cid, qty=3)
    done, _ = complete(c, cook, o, "KQ-L2")
    assert money(done["totals"]["subtotal"]) == Decimal("28.50") and balance(c, cid) == 28  # tax isn't counted
    assert c.post(f"/customers/{cid}/loyalty/adjust", {"points": 200, "reason": "Welcome bonus"}).status_code == 403
    assert gm.post(f"/customers/{cid}/loyalty/adjust", {"points": 200, "reason": "Welcome bonus"}).json()["balance"] == 228
    o2 = takeaway_for(c, m, cid)
    assert c.post(f"/orders/{o2['id']}/loyalty-redemption", {"points": 150}).json()["error"]["code"] == "LOYALTY_STEP"
    assert c.post(f"/orders/{o2['id']}/loyalty-redemption", {"points": 1000}).json()["error"]["code"] == "LOYALTY_EXCEEDS_ORDER"
    r = c.post(f"/orders/{o2['id']}/loyalty-redemption", {"points": 200}).json()
    assert money(r["totals"]["subtotal"]) == Decimal("7.50") and balance(c, cid) == 28
    assert c.post(f"/orders/{o2['id']}/loyalty-redemption", {"points": 100}).json()["error"]["code"] == "LOYALTY_ALREADY_REDEEMED"
    assert s.post(f"/orders/{o2['id']}/discounts", {"kind": "Percent", "value": "10", "reason": "Regular"}).json()["error"]["code"] == "LOYALTY_REDEMPTION_APPLIED"
    # oldest points are used first: the 28 earned before the 200 bonus
    with engine.connect() as conn:
        lots = dict(conn.execute(text("select kind, remaining from loyalty_transactions where customer_id = :c and remaining is not null"), {"c": cid}).all())
    assert lots == {"Earn": 0, "Adjust": 28}
    # removing the redemption gives the points back
    assert money(c.delete(f"/orders/{o2['id']}/loyalty-redemption").json()["totals"]["subtotal"]) == Decimal("9.50") and balance(c, cid) == 228
    c.post(f"/orders/{o2['id']}/loyalty-redemption", {"points": 200})
    complete(c, cook, o2, "KQ-L3")
    assert balance(c, cid) == 28 + 7  # earned on the 7.50 actually charged
    summary = c.get(f"/customers/{cid}/loyalty").json()
    assert summary["redeemable_points"] == 0 and {h["kind"] for h in summary["history"]} >= {"Earn", "Adjust", "Redeem", "RedeemReversal"}


def test_cancel_returns_points_and_refund_claws_back(api):
    gm, c, cook = api("gm"), api("cashier"), api("cook")
    m = menu(c)
    enable(gm)
    cid = c.post("/customers", {"name": "Dara", "phone": "017 444 555"}).json()["id"]
    gm.post(f"/customers/{cid}/loyalty/adjust", {"points": 300, "reason": "Opening balance"})
    o = takeaway_for(c, m, cid)
    c.post(f"/orders/{o['id']}/loyalty-redemption", {"points": 300})
    assert balance(c, cid) == 0
    api("supv").post(f"/orders/{o['id']}/cancel", {"reason": "Customer left"})
    assert balance(c, cid) == 300
    o = takeaway_for(c, m, cid, qty=3)
    done, pay = complete(c, cook, o, "KQ-R1")
    assert balance(c, cid) == 328
    total = money(done["totals"]["grand_total"])
    rf = c.post("/refunds", {"payment_id": pay["payment_id"], "amount": "10.00", "reason": "Cold food"}, idem=True).json()
    gm.post(f"/refunds/{rf['id']}/approve", {})
    keep = math.floor(28 * (1 - Decimal("10.00") / total))
    assert balance(c, cid) == 300 + keep


def test_expiry_after_twelve_months(api, engine):
    from app.workers.celery_app import expire_loyalty_points

    gm, c = api("gm"), api("cashier")
    enable(gm)
    cid = c.post("/customers", {"name": "Vanna", "phone": "017 666 777"}).json()["id"]
    gm.post(f"/customers/{cid}/loyalty/adjust", {"points": 150, "reason": "Old points"})
    gm.post(f"/customers/{cid}/loyalty/adjust", {"points": 50, "reason": "New points"})
    with engine.begin() as conn:  # the first lot was earned 13 months ago
        conn.execute(text("update loyalty_transactions set expires_at = now() - interval '1 month' where customer_id = :c and reason = 'Old points'"), {"c": cid})
    assert expire_loyalty_points() == 150
    s = c.get(f"/customers/{cid}/loyalty").json()
    assert s["balance"] == 50 and s["history"][0]["kind"] == "Expire"
    assert expire_loyalty_points() == 0  # nothing expires twice
