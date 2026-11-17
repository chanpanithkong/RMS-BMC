"""SRS §16.16 (PROMO): AT-PROMO-01/02/03 plus validity rules and promotion types."""
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.helpers import line, menu, money

YESTERDAY = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def promo(gm, **kw):
    body = {"valid_from": YESTERDAY, **kw}
    r = gm.post("/promotions", body)
    assert r.status_code == 201, r.json()
    return r.json()


def order_of(c, m, *lines, order_type="Takeaway"):
    return c.post("/orders", {"order_type": order_type, "pickup_name": "P", "items": list(lines)}, idem=True).json()


def test_at_promo_01_combination_priority(api):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    item_promo = promo(gm, name="Rice 10%", promo_type="Percent", scope="Item", value="10", target_ids=[m["RN-01"]["id"]], combinable=True, priority=5)
    promo(gm, name="5 off", promo_type="Amount", scope="Order", value="5.00", combinable=False, priority=10)
    probe = order_of(c, m, line(m, "RN-01", 1, ("Mild",)))
    unit = money(probe["totals"]["gross"])
    qty = int(Decimal("40") / unit)
    o = order_of(c, m, line(m, "RN-01", qty, ("Mild",)))
    assert money(o["totals"]["gross"]) == unit * qty == Decimal("40")  # the SRS's 40.00 USD order
    assert money(o["totals"]["discount_total"]) == Decimal("5")  # the higher-priority promotion only
    ev = c.get(f"/orders/{o['id']}/promotions").json()
    assert [a["name"] for a in ev["applied"]] == ["5 off"]
    skipped = {x["name"]: x["reason"] for x in ev["not_applied"]}
    assert "can't be combined" in skipped["Rice 10%"]
    # raise the item promotion's priority: now it wins and the order discount is listed as not applied
    gm.patch(f"/promotions/{item_promo['id']}", {"priority": 20})
    ev = c.get(f"/orders/{o['id']}/promotions").json()
    assert [a["name"] for a in ev["applied"]] == ["Rice 10%"] and "Not combinable" in {x["name"]: x["reason"] for x in ev["not_applied"]}["5 off"]
    assert api("cashier").post("/promotions", {"name": "x", "promo_type": "Percent", "scope": "Order", "value": "5", "valid_from": YESTERDAY}).status_code == 403


def test_at_promo_02_duplicate_prevention(api):
    gm, c, s = api("gm"), api("cashier"), api("supv")
    m = menu(c)
    o = order_of(c, m, line(m, "MN-01", 2, ("Mild",)))
    body = {"kind": "Percent", "value": "10", "reason": "Regular guest"}
    assert s.post(f"/orders/{o['id']}/discounts", body).status_code == 200
    again = s.post(f"/orders/{o['id']}/discounts", body)
    assert again.status_code == 409 and again.json()["error"]["code"] == "DISCOUNT_ALREADY_APPLIED"
    p = promo(gm, name="Code 1 off", promo_type="Amount", scope="Item", value="1", target_ids=[m["MN-01"]["id"]], auto_apply=False)
    gm.post(f"/promotions/{p['id']}/codes", {"code": "ONEOFF"})
    assert c.post(f"/orders/{o['id']}/promo-codes", {"code": "oneoff"}).status_code == 200  # case-insensitive
    dup = c.post(f"/orders/{o['id']}/promo-codes", {"code": "ONEOFF"})
    assert dup.json()["error"]["code"] == "PROMO_ALREADY_APPLIED"
    discounts = c.get(f"/orders/{o['id']}").json()["discounts"]
    assert sorted((d["promotion_id"] is not None, d["kind"]) for d in discounts) == [(False, "Percent"), (True, "Amount")]


def test_at_promo_03_code_limit_concurrency(api, engine):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    p = promo(gm, name="Welcome", promo_type="Percent", scope="Order", value="10", auto_apply=False)
    code = gm.post(f"/promotions/{p['id']}/codes", {"code": "WELCOME", "max_uses": 1}).json()
    orders = [order_of(c, m, line(m, "MN-01", 1, ("Mild",))) for _ in range(2)]
    results = []

    def redeem(o):
        r = c.post(f"/orders/{o['id']}/promo-codes", {"code": "WELCOME"})
        results.append((r.status_code, r.json().get("error", {}).get("code")))

    threads = [threading.Thread(target=redeem, args=(o,)) for o in orders]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [(200, None), (409, "PROMO_LIMIT_REACHED")]
    assert gm.get(f"/promotions/{p['id']}").json()["codes"][0]["uses"] == 1
    # cancelling the order that used the code gives the use back
    winner = next(o for o in orders if c.get(f"/orders/{o['id']}/promotions").json()["codes"])
    api("supv").post(f"/orders/{winner['id']}/cancel", {"reason": "Guest left"})
    assert gm.get(f"/promotions/{p['id']}").json()["codes"][0]["uses"] == 0
    assert code["code"] == "WELCOME"


def test_validity_and_types(api):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    promo(gm, name="Dine-in only", promo_type="Percent", scope="Order", value="20", order_types=["DineIn"])
    promo(gm, name="3 for 2", promo_type="BuyXGetY", scope="Item", target_ids=[m["DR-03"]["id"]], buy_qty=2, get_qty=1, combinable=True)
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    gm.post("/promotions", {"name": "Next week", "promo_type": "Percent", "scope": "Order", "value": "50", "valid_from": future})
    o = order_of(c, m, line(m, "DR-03", 3))
    unit = money(o["items"][0]["unit_price_snapshot"])
    assert money(o["totals"]["discount_total"]) == unit  # one bottle free
    reasons = {x["name"]: x["reason"] for x in c.get(f"/orders/{o['id']}/promotions").json()["not_applied"]}
    assert reasons["Dine-in only"] == "Not valid for Takeaway orders"
    assert reasons["Next week"] == "Outside the promotion's validity dates"
    bad = gm.post("/promotions", {"name": "Bad", "promo_type": "FixedPrice", "scope": "Order", "value": "1", "valid_from": YESTERDAY})
    assert bad.status_code == 422
    assert c.post(f"/orders/{o['id']}/promo-codes", {"code": "NOPE"}).json()["error"]["code"] == "PROMO_CODE_INVALID"
