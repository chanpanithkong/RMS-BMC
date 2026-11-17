"""SRS §16.15 (DLV): AT-DLV-01 fee separate and taxed by its own profile, AT-DLV-02 commission is a cost, AT-DLV-03 ready board; riders and failures."""
from decimal import ROUND_HALF_UP, Decimal

from tests.helpers import line, menu, money


def standard_profile(u):
    return next(p["id"] for p in u.get("/tax-profiles").json() if p["code"] == "STANDARD")


def zone(gm, **kw):
    r = gm.post("/delivery-zones", {"name": "Riverside 3 km", "fee": "1.50", "estimated_minutes": 45, **kw})
    assert r.status_code == 201, r.json()
    return r.json()


def delivery_order(c, m, z, *lines, **extra):
    body = {"order_type": "Delivery", "customer_name": "Dara", "customer_phone": "012 345 678",
            "delivery": {"zone_id": z["id"], "address": "St 110, house 21", "landmark": "Near the pagoda", **extra}, "items": list(lines)}
    return c.post("/orders", body, idem=True)


def bump_all(cook, oid):
    for st in ("HOT", "COLD", "BEV", "DESSERT", "BAR"):
        for t in cook.get(f"/kitchen/stations/{st}/open-tickets").json():
            if t["order_id"] == oid:
                cook.post(f"/kitchen/tickets/{t['ticket_id']}/bump")


def test_at_dlv_01_fee_is_a_separate_taxed_charge(api):
    gm, c, s = api("gm"), api("cashier"), api("supv")
    m = menu(c)
    z = zone(gm, tax_profile_id=standard_profile(gm), free_over="30")
    assert c.post("/orders", {"order_type": "Delivery", "customer_phone": "012 345 678", "items": [line(m, "MN-02", 1)]}, idem=True).json()["error"]["code"] == "DELIVERY_DETAILS_REQUIRED"
    assert delivery_order(c, m, z, line(m, "MN-02", 1), fee_override="0").status_code == 403  # cashier can't override the fee
    o = delivery_order(c, m, z, line(m, "MN-02", 1)).json()
    t = o["totals"]
    assert money(t["delivery_fee"]) == Decimal("1.50") and money(t["subtotal"]) == Decimal("9.50")
    assert money(t["tax"]) == Decimal("0.95") + Decimal("0.15")  # food tax plus 10 % (illustrative) on the fee, from the zone's profile
    assert money(t["grand_total"]) == Decimal("9.50") + Decimal("0.95") + Decimal("1.50") + Decimal("0.15")
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    assert money(bill["delivery_fee"]) == Decimal("1.50") and money(bill["subtotal"]) == Decimal("9.50")
    c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": "KQ-DLV-1"}, idem=True)
    sales = api("owner").get("/dashboard").json()["widgets"]["sales"]
    assert money(sales["net_sales"]) == Decimal("9.50") and money(sales["delivery_fees"]) == Decimal("1.50")  # fee excluded from food net sales
    # free over 30.00 of food; manual override needs delivery.fee_override and a reason
    big = delivery_order(c, m, z, line(m, "MN-02", 4)).json()
    assert money(big["totals"]["delivery_fee"]) == 0
    small = delivery_order(c, m, z, line(m, "MN-02", 1)).json()
    assert c.put(f"/orders/{small['id']}/delivery-fee", {"fee": "0.50", "reason": "Regular customer"}).status_code == 403
    r = s.put(f"/orders/{small['id']}/delivery-fee", {"fee": "0.50", "reason": "Regular customer"}).json()
    assert money(r["totals"]["delivery_fee"]) == Decimal("0.50")
    assert api("auditor").get("/audit-logs?action=delivery.fee_override").json()["total"] == 1


def test_rider_flow_failure_and_cancellation(api):
    gm, c, cook, rider, s = api("gm"), api("cashier"), api("cook"), api("rider"), api("supv")
    m = menu(c)
    z = zone(gm, min_order="5")
    o = delivery_order(c, m, z, line(m, "MN-02", 1)).json()
    d = next(x for x in c.get("/deliveries").json() if x["order_id"] == o["id"])
    assert d["status"] == "PendingAssignment" and d["landmark"] == "Near the pagoda"
    rider_id = next(u["id"] for u in api("admin").get("/users").json()["data"] if u["username"] == "rider")
    waiter_id = next(u["id"] for u in api("admin").get("/users").json()["data"] if u["username"] == "waiter")
    assert c.post(f"/deliveries/{d['id']}/assign", {"rider_id": waiter_id}).json()["error"]["code"] == "NOT_A_RIDER"
    assert c.post(f"/deliveries/{d['id']}/assign", {"rider_id": rider_id}).json()["status"] == "Assigned"
    assert [x["order_no"] for x in rider.get("/deliveries/mine").json()] == [o["order_no"]]
    assert rider.get("/deliveries").status_code == 403  # riders see only their own
    c.post(f"/orders/{o['id']}/send", idem=True)
    assert rider.post(f"/deliveries/{d['id']}/out").json()["error"]["code"] == "ORDER_NOT_READY"
    bump_all(cook, o["id"])
    assert rider.post(f"/deliveries/{d['id']}/out").json()["status"] == "OutForDelivery"
    assert api("waiter").post(f"/deliveries/{d['id']}/delivered", {}).status_code in (403, 404)
    done = rider.post(f"/deliveries/{d['id']}/delivered", {"recipient_name": "Dara"}).json()
    assert done["status"] == "Delivered" and money(done["amount_due"]) > 0  # cash on delivery still to settle
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": "KQ-COD-1"}, idem=True)
    assert c.get(f"/orders/{o['id']}").json()["order_status"] == "Completed"
    # failure and re-delivery
    o2 = delivery_order(c, m, z, line(m, "MN-02", 1)).json()
    d2 = next(x for x in c.get("/deliveries").json() if x["order_id"] == o2["id"])
    c.post(f"/deliveries/{d2['id']}/assign", {"rider_id": rider_id})
    assert rider.post(f"/deliveries/{d2['id']}/failed", {"reason": "Customer not answering"}).json()["status"] == "Failed"
    assert rider.post(f"/deliveries/{d2['id']}/redeliver").status_code == 403
    assert c.post(f"/deliveries/{d2['id']}/redeliver").json()["status"] == "PendingAssignment"
    # cancelling the order cancels the delivery
    s.post(f"/orders/{o2['id']}/cancel", {"reason": "Customer cancelled"})
    assert c.get(f"/deliveries/{d2['id']}").json()["status"] == "Cancelled"
    perf = gm.get("/deliveries/performance").json()
    rider_row = next(x for x in perf["by_rider"] if x["key"] == "Rider")
    assert rider_row["delivered"] == 1 and sum(x["failed"] for x in perf["by_rider"]) == 1  # the re-delivery is unassigned again


def test_minimum_order(api):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    z = zone(gm, min_order="20")
    o = delivery_order(c, m, z, line(m, "MN-02", 1)).json()
    assert c.post(f"/orders/{o['id']}/send", idem=True).json()["error"]["code"] == "MINIMUM_ORDER_NOT_MET"


def test_at_dlv_02_platform_commission_is_a_cost_and_settlement(api):
    c, acct, owner = api("cashier"), api("acct"), api("owner")
    m = menu(c)
    body = {"platform": "FoodApp", "platform_ref": "FA-1001", "commission_rate": "0.25", "items": [line(m, "MN-02", 2)]}
    r = c.post("/platform-orders", body).json()
    total = money(r["order"]["totals"]["grand_total"])
    assert r["order"]["channel"] == "Platform" and money(r["commission_amount"]) == (total * Decimal("0.25")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    assert c.post("/platform-orders", body).json()["error"]["code"] == "PLATFORM_REF_EXISTS"
    bill = c.post(f"/orders/{r['order']['id']}/bills", {"mode": "single"}).json()[0]
    assert c.post("/payments", {"bill_id": bill["id"], "method": "PLATFORM", "currency": "USD", "reference": "FA-1001"}, idem=True).status_code == 201
    d = owner.get("/dashboard").json()["widgets"]
    commission = money(r["commission_amount"])
    assert money(d["sales"]["net_sales"]) == Decimal("19.00") and money(d["sales"]["discounts"]) == 0  # commission isn't a discount
    assert money(d["costs"]["platform_commissions"]) == commission
    assert money(d["indicative_operating_result"]["value"]) == Decimal("19.00") - commission
    # settlement: one matching line, one unknown order, payout short by 1.00
    lines = [{"platform_ref": "FA-1001", "gross": str(total), "commission": str(commission), "net": str(total - commission)},
             {"platform_ref": "FA-9999", "gross": "10", "commission": "2.5", "net": "7.5"}]
    rec = acct.post("/platform-settlements", {"platform": "FoodApp", "statement_ref": "ST-1", "period_from": r["order"]["business_date"],
                                              "period_to": r["order"]["business_date"], "amount_paid": str(total - commission + Decimal("6.5")), "lines": lines}).json()
    issues = {(x["platform_ref"], x["issue"]) for x in rec["differences"]}
    assert issues == {("FA-9999", "Not recorded in RMS"), (None, "Payout differs from the sum of lines")}
    po = acct.get("/platform-orders").json()[0]
    assert po["settlement_status"] == "Settled" and money(po["net_expected"]) == total - commission
    assert c.post("/platform-settlements", {"platform": "FoodApp", "statement_ref": "ST-2", "period_from": "2026-01-01", "period_to": "2026-01-01",
                                            "amount_paid": "0", "lines": lines}).status_code == 403  # cashier can't reconcile


def test_at_dlv_03_takeaway_ready_board(api):
    c, cook = api("cashier"), api("cook")
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "0457", "items": [line(m, "MN-02", 1)]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": "KQ-0457"}, idem=True)  # takeaway is pay-first
    assert c.post(f"/orders/{o['id']}/send", idem=True).status_code == 200
    assert all(x["order_id"] != o["id"] for x in c.get("/ready-board").json())
    bump_all(cook, o["id"])
    board = c.get("/ready-board").json()
    assert any(x["order_no"] == o["order_no"] and x["pickup_name"] == "0457" for x in board)
    c.post(f"/orders/{o['id']}/serve", {})  # collected: off the board and completed
    assert all(x["order_id"] != o["id"] for x in c.get("/ready-board").json())
    assert c.get(f"/orders/{o['id']}").json()["order_status"] == "Completed"
