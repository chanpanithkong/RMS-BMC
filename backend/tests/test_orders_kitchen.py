"""Acceptance tests from SRS §16.2–16.6 (MENU, POS, TBL, ORD, KDS)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from tests.helpers import line, menu, money, tables


def new_order(u, m, items, order_type="Takeaway", **extra):
    body = {"order_type": order_type, "items": items, **extra}
    if order_type == "Takeaway":
        body.setdefault("pickup_name", "Vanna")
    r = u.post("/orders", body, idem=True)
    assert r.status_code == 201, r.text
    return r.json()


def test_at_pos_01_item_subtotal(api):
    u = api("cashier")
    m = menu(u)
    o = new_order(u, m, [line(m, "RN-01", 2, ("Medium",))])
    assert money(o["items"][0]["line_gross"]) == money("10.00")
    assert money(o["totals"]["gross"]) == money("10.00")


def test_at_menu_02_required_modifier(api):
    u = api("cashier")
    m = menu(u)
    r = u.post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "CF-01")]}, idem=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "MODIFIER_REQUIRED" and "Sugar level" in r.json()["error"]["message"]


def test_at_menu_03_item_86_rejected(api):
    m = menu(api("cashier"))
    r = api("kmgr").post(f"/menu-items/{m['RN-03']['id']}/availability", {"available": False, "reason": "Out of broth"})
    assert r.status_code == 200 and r.json()["available"] is False
    pos = {i["code"]: i for i in api("cashier").get("/menu/pos").json()["items"]}
    assert pos["RN-03"]["available"] is False
    r = api("cashier").post("/orders", {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "RN-03")]}, idem=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "ITEM_UNAVAILABLE"


def test_at_menu_04_price_overlap_and_at_menu_01_history(api):
    gm, cashier = api("gm"), api("cashier")
    m = menu(cashier)
    o = new_order(cashier, m, [line(m, "RN-01", 1, ("Mild",))])
    vid = m["RN-01"]["variants"]["Regular"]
    now = datetime.now(timezone.utc)
    r = gm.post(f"/menu-items/{m['RN-01']['id']}/prices", {"variant_id": vid, "price": "5.50", "valid_from": (now - timedelta(seconds=1)).isoformat()})
    assert r.status_code == 201, r.text
    # open order keeps 5.00; new orders use 5.50 (BR-026)
    assert money(cashier.get(f"/orders/{o['id']}").json()["items"][0]["unit_price_snapshot"]) == money("5.00")
    o2 = new_order(cashier, m, [line(m, "RN-01", 1, ("Mild",))])
    assert money(o2["items"][0]["unit_price_snapshot"]) == money("5.50")
    hist = gm.get(f"/menu-items/{m['RN-01']['id']}/price-history").json()
    assert {money(h["price"]) for h in hist} == {money("5.00"), money("5.50")}
    # a bounded record, then an overlapping one inside it
    dec1, dec31 = datetime(2027, 12, 1, tzinfo=timezone.utc), datetime(2027, 12, 31, tzinfo=timezone.utc)
    branch_only = {"variant_id": vid, "price": "6.00", "valid_from": dec1.isoformat(), "valid_to": dec31.isoformat(), "branch_id": gm.get("/auth/me").json()["current_branch"]["id"]}
    assert gm.post(f"/menu-items/{m['RN-01']['id']}/prices", branch_only).status_code == 201
    overlap = {**branch_only, "price": "6.50", "valid_from": datetime(2027, 12, 15, tzinfo=timezone.utc).isoformat(), "valid_to": datetime(2027, 12, 20, tzinfo=timezone.utc).isoformat()}
    r = gm.post(f"/menu-items/{m['RN-01']['id']}/prices", overlap)
    assert r.status_code == 409 and r.json()["error"]["code"] == "PRICE_OVERLAP"


def test_at_kds_01_routing_and_at_pos_02_duplicate_send(api):
    u = api("cashier")
    m = menu(u)
    t = tables(u)
    o = new_order(u, m, [line(m, "RN-01", 1, ("Hot",)), line(m, "CF-01", 1, ("50%",)), line(m, "DR-03")], order_type="DineIn", table_id=t["A1"]["id"], guest_count=2)
    key = "send-key-1"
    r1 = u.post(f"/orders/{o['id']}/send", idem=key)
    r2 = u.post(f"/orders/{o['id']}/send", idem=key)
    assert r1.status_code == 200 and r1.json() == r2.json()
    assert sorted(x["station_code"] for x in r1.json()["tickets"]) == ["BEV", "HOT"]
    hot = api("cook").get("/kitchen/stations/HOT/open-tickets").json()
    assert len(hot) == 1 and [i["name_en"] for i in hot[0]["items"]] == ["Fried Rice"]
    first = hot[0]["items"][0]  # the kitchen screen is built from tickets alone (cooks can't read orders)
    assert first["status"] == "Sent" and first["void_type"] is None and first["started_at"] is None and first["ready_at"] is None
    bev = api("cook").get("/kitchen/stations/BEV/open-tickets").json()
    assert [i["name_en"] for i in bev[0]["items"]] == ["Iced Coffee"]
    order = u.get(f"/orders/{o['id']}").json()
    water = next(i for i in order["items"] if i["item_name_en_snapshot"] == "Bottled Water")
    assert water["item_status"] == "Ready"  # no kitchen routing
    assert tables(u)["A1"]["service_state"] == "Ordering"
    # a different key for the same order now has nothing new to send
    assert u.post(f"/orders/{o['id']}/send", idem=True).json()["error"]["code"] == "NOTHING_TO_SEND"


def test_at_ord_01_02_status_and_no_edit_after_send(api):
    u, cook = api("cashier"), api("cook")
    m = menu(u)
    o = new_order(u, m, [line(m, "RN-01", 1, ("Mild",)), line(m, "CF-01", 1, ("0%",))])
    o = u.get(f"/orders/{o['id']}").json()
    # takeaway is pay-first by default: kitchen send is blocked until paid
    assert u.post(f"/orders/{o['id']}/send", idem=True).json()["error"]["code"] == "PAYMENT_REQUIRED_FIRST"
    o = new_order(u, m, [line(m, "RN-01", 1, ("Mild",)), line(m, "CF-01", 1, ("0%",))], order_type="DineIn", table_tag="12")
    assert u.post(f"/orders/{o['id']}/send", idem=True).status_code == 200
    items = {i["item_name_en_snapshot"]: i for i in u.get(f"/orders/{o['id']}").json()["items"]}
    assert cook.post(f"/kitchen/items/{items['Fried Rice']['id']}/status", {"status": "InPreparation"}).status_code == 200
    assert cook.post(f"/kitchen/items/{items['Iced Coffee']['id']}/status", {"status": "Ready"}).status_code == 200
    order = u.get(f"/orders/{o['id']}").json()
    statuses = {i["item_name_en_snapshot"]: i["item_status"] for i in order["items"]}
    assert statuses == {"Fried Rice": "InPreparation", "Iced Coffee": "Ready"} and order["kitchen_status"] == "InProgress"
    r = u.patch(f"/orders/{o['id']}/items/{items['Fried Rice']['id']}", {"quantity": "2"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ITEM_NOT_PENDING"
    # forward-only state machine
    r = cook.post(f"/kitchen/items/{items['Fried Rice']['id']}/status", {"status": "Served"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_stale_version_rejected(api):
    u = api("cashier")
    m = menu(u)
    o = new_order(u, m, [line(m, "DR-03")])
    r = u.post(f"/orders/{o['id']}/items", [line(m, "DR-03")], headers={"If-Match": str(o["version"] + 5)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "VERSION_CONFLICT"


def test_at_tbl_01_02_03(api):
    w, s = api("waiter"), api("supv")
    m = menu(w)
    t = tables(w)
    r = w.post(f"/tables/{t['A2']['id']}/state", {"state": "Served"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    seat = w.post(f"/tables/{t['A1']['id']}/seat", {"guest_count": 3})
    assert seat.status_code == 200
    oid = seat.json()["order_id"]
    w.post(f"/orders/{oid}/items", [line(m, "RN-01", 1, ("Mild",)), line(m, "DR-03")])
    a1 = tables(w)["A1"]
    assert a1["service_state"] == "Ordering" and a1["guest_count"] == 3 and a1["open_order_id"] == oid
    total = w.get(f"/orders/{oid}").json()["totals"]["grand_total"]
    assert w.post(f"/orders/{oid}/transfer", {"table_id": t["B2"]["id"]}).status_code == 403  # waiter lacks orders.transfer
    r = s.post(f"/orders/{oid}/transfer", {"table_id": t["B2"]["id"]})
    assert r.status_code == 200 and r.json()["table_code"] == "B2" and r.json()["totals"]["grand_total"] == total
    now = tables(s)
    assert now["A1"]["service_state"] == "Cleaning" and now["B2"]["service_state"] == "Ordering"
    # over capacity needs a manager override
    assert w.post(f"/tables/{t['A2']['id']}/seat", {"guest_count": 5}).json()["error"]["code"] == "OVER_CAPACITY"


def test_at_pos_03_discount_limit_and_approval(api, engine):
    c = api("cashier")
    m = menu(c)
    o = new_order(c, m, [line(m, "MN-01", 2, ("Mild",))], order_type="DineIn", table_tag="5")
    r = c.post(f"/orders/{o['id']}/discounts", {"kind": "Percent", "value": "20", "reason": "Service recovery"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "APPROVAL_REQUIRED"
    ap = c.post("/approvals", {"action": "discount", "approver_username": "supv", "approver_secret": "7314", "amount": "20", "target_id": o["id"], "reason": "Service recovery"}).json()
    r = c.post(f"/orders/{o['id']}/discounts", {"kind": "Percent", "value": "20", "reason": "Service recovery", "approval_id": ap["approval_id"]})
    assert r.status_code == 200 and money(r.json()["totals"]["discount_total"]) == money("3.40")
    # the token is single use
    r = c.post(f"/orders/{o['id']}/discounts", {"kind": "Percent", "value": "15", "reason": "again", "approval_id": ap["approval_id"]})
    assert r.status_code == 403
    with engine.connect() as conn:
        row = conn.execute(text("select after_data from audit_logs where action='discount.apply' order by id desc limit 1")).scalar()
    assert row["approved_by"] and row["requested_by"] and row["approved_by"] != row["requested_by"]


def test_at_bill_01_calculation_order(api):
    c = api("cashier")
    m = menu(c)
    o = new_order(c, m, [line(m, "RN-01", 2, ("Mild",)), line(m, "CF-01", 1, ("50%", "Extra shot"))], order_type="DineIn", table_tag="7")
    coffee = next(i for i in o["items"] if i["item_name_en_snapshot"] == "Iced Coffee")
    c.post(f"/orders/{o['id']}/discounts", {"order_item_id": coffee["id"], "kind": "Percent", "value": "10", "reason": "Regular customer"})
    r = c.post(f"/orders/{o['id']}/discounts", {"kind": "Amount", "value": "1.00", "reason": "Regular customer"})
    t = r.json()["totals"]
    assert (money(t["gross"]), money(t["subtotal"]), money(t["service_charge"]), money(t["tax"]), money(t["grand_total"])) == \
        (money("12.50"), money("11.25"), money("0.56"), money("1.18"), money("12.99"))


def test_void_rules_and_at_kds_02_03(api):
    w, cook, s = api("waiter"), api("cook"), api("supv")
    m = menu(w)
    t = tables(w)
    oid = w.post(f"/tables/{t['A3']['id']}/seat", {"guest_count": 2}).json()["order_id"]
    w.post(f"/orders/{oid}/items", [line(m, "RN-01", 1, ("Mild",)), line(m, "ST-01", 1, ("Mild",))])
    w.post(f"/orders/{oid}/send", idem=True)
    items = {i["item_name_en_snapshot"]: i for i in w.get(f"/orders/{oid}").json()["items"]}
    cook.post(f"/kitchen/items/{items['Fried Rice']['id']}/status", {"status": "InPreparation"})
    # a waiter can't cancel sent items; a supervisor can cancel unprepared ones with a reason
    assert w.post(f"/orders/{oid}/items/{items['Green Mango Salad']['id']}/cancel", {"reason": "Customer changed mind"}).status_code == 403
    assert s.post(f"/orders/{oid}/items/{items['Green Mango Salad']['id']}/cancel", {"reason": "Customer changed mind"}).status_code == 200
    # prepared item: approval from another user required
    r = s.post(f"/orders/{oid}/items/{items['Fried Rice']['id']}/cancel", {"reason": "Kitchen error"})
    assert r.json()["error"]["code"] == "APPROVAL_REQUIRED"
    ap = s.post("/approvals", {"action": "void", "approver_username": "gm", "approver_secret": "5937", "amount": items["Fried Rice"]["line_net"], "target_id": items["Fried Rice"]["id"]}).json()
    r = s.post(f"/orders/{oid}/items/{items['Fried Rice']['id']}/cancel", {"reason": "Kitchen error", "approval_id": ap["approval_id"]})
    fr = next(i for i in r.json()["items"] if i["item_name_en_snapshot"] == "Fried Rice")
    assert fr["item_status"] == "Cancelled" and fr["void_type"] == "AfterPreparation"
    assert cook.post(f"/kitchen/items/{fr['id']}/waste-outcome", {"outcome": "Wastage"}).status_code == 200
    # AT-KDS-03 ready notification to the owning waiter
    oid2 = w.post(f"/tables/{t['A4']['id']}/seat", {"guest_count": 2}).json()["order_id"]
    w.post(f"/orders/{oid2}/items", [line(m, "MN-01", 1, ("Hot",))])
    w.post(f"/orders/{oid2}/send", idem=True)
    ticket = cook.get("/kitchen/stations/HOT/open-tickets").json()
    tid = next(x["ticket_id"] for x in ticket if x["order_id"] == oid2)
    assert cook.post(f"/kitchen/tickets/{tid}/bump").status_code == 200
    item = w.get(f"/orders/{oid2}").json()["items"][0]
    assert item["item_status"] == "Ready" and item["ready_at"]
    notes = w.get("/notifications").json()["data"]
    assert any("ready" in n["title"].lower() for n in notes)


def test_role_restrictions(api):
    cook = api("cook")
    m = menu(cook)
    r = cook.post("/orders", {"order_type": "Takeaway", "pickup_name": "x", "items": [line(m, "DR-03")]}, idem=True)
    assert r.status_code == 403
    assert api("waiter").post(f"/menu-items/{m['DR-03']['id']}/availability", {"available": False}).status_code == 403


def test_create_order_requires_idempotency_and_replays(api):
    c = api("cashier")
    m = menu(c)
    body = {"order_type": "Takeaway", "pickup_name": "A", "items": [line(m, "DR-03")]}
    assert c.post("/orders", body).json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    a = c.post("/orders", body, idem="create-1").json()
    b = c.post("/orders", body, idem="create-1").json()
    assert a["id"] == b["id"]
    r = c.post("/orders", {**body, "pickup_name": "B"}, idem="create-1")
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"
