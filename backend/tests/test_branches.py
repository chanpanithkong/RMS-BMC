"""Phase 3 multi-branch (SRS §6.22 BRN): branch setup, menu assignment, supplier restriction, inter-branch transfers, consolidated reports."""
from decimal import Decimal

from tests.helpers import line, menu, money
from tests.test_config_reports import paid_order
from tests.test_recipes_stock import opening, refs


def second_branch(api, seeded, *usernames):
    """The administrator registers BKK and assigns the given users to both branches (as they would through /users)."""
    admin = api("admin")
    b = admin.post("/branches", {"code": "BKK", "name_en": "BKK1", "name_km": "បឹងកេងកង", "timezone": "Asia/Phnom_Penh"})
    assert b.status_code == 201, b.json()
    b = b.json()
    rvs = seeded["branch_id"]
    for u in usernames:
        r = admin.patch(f"/users/{seeded['users'][u]}", {"branch_ids": [str(rvs), b["id"]]})
        assert r.status_code == 200, r.json()
    return b, {"X-Branch-Id": "BKK"}


def bal(u, code, loc, headers=None):
    return sum((money(b["quantity"]) for b in u.get("/inventory/balances", headers=headers).json() if b["ingredient_code"] == code and b["location_name"] == loc), Decimal(0))


def test_branch_setup_menu_assignment_and_suppliers(api, seeded):
    b, bkk = second_branch(api, seeded, "gm", "puroff")
    assert api("admin").post("/branches", {"code": "bkk", "name_en": "Again"}).json()["error"]["code"] == "BRANCH_CODE_EXISTS"
    assert api("admin").post("/branches", {"code": "X1", "name_en": "X", "timezone": "Mars/Base"}).status_code == 422
    assert api("gm").post("/branches", {"code": "X2", "name_en": "X"}).status_code == 403
    gm = api("gm")
    assert {x["name"] for x in gm.get("/inventory/locations", headers=bkk).json()} == {"Dry store", "Chiller", "Freezer", "Bar"}
    # FR-BRN-003: stop selling an item at BKK only
    m = menu(gm)
    assert gm.put(f"/menu-items/{m['MN-01']['id']}/branch-assignment", {"assigned": False}, headers=bkk).json()["assigned"] is False
    pos_bkk = {i["code"]: i for i in gm.get("/menu/pos", headers=bkk).json()["items"]}
    pos_rvs = {i["code"]: i for i in gm.get("/menu/pos").json()["items"]}
    assert "MN-01" not in pos_bkk or pos_bkk["MN-01"]["available"] is False
    assert pos_rvs["MN-01"]["available"] is True
    # FR-BRN-005: a supplier restricted to BKK isn't visible at Riverside
    p = api("puroff")
    s = p.post("/suppliers", {"name": "BKK Market", "contact_person": "Sok", "phone": "012 555 111", "branch_ids": [b["id"]]}).json()
    assert [x["name"] for x in p.get("/suppliers", headers=bkk).json()] == ["BKK Market"]
    assert "BKK Market" not in [x["name"] for x in p.get("/suppliers").json()]
    assert p.get(f"/suppliers/{s['id']}/history").status_code == 404
    assert api("invoff").get("/inventory/locations", headers=bkk).json()["error"]["code"] == "BRANCH_FORBIDDEN"  # not assigned to BKK


def test_inter_branch_transfer_dispatch_receive_cancel(api, seeded):
    b, bkk = second_branch(api, seeded, "invoff")
    inv = api("invoff")
    units, locs, items = refs(inv)
    bkk_locs = {x["name"]: x["id"] for x in inv.get("/inventory/locations", headers=bkk).json()}
    opening(inv, locs["Dry store"], items["ING-001"], "10", units["kg"], "2.00")
    body = {"to_branch_id": b["id"], "from_location_id": locs["Dry store"], "lines": [{"ingredient_id": items["ING-001"], "quantity": "4000", "uom_id": units["g"]}]}
    t = inv.post("/branch-transfers", body).json()
    assert t["status"] == "InTransit" and money(t["lines"][0]["qty_dispatched"]) == 4 and money(t["lines"][0]["unit_cost"]) == 2
    assert bal(inv, "ING-001", "Dry store") == 6  # left the source at dispatch
    assert inv.post("/branch-transfers", {**body, "lines": [{**body["lines"][0], "quantity": "50000"}]}).json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert [x["transfer_no"] for x in inv.get("/branch-transfers?direction=in", headers=bkk).json()] == [t["transfer_no"]]
    assert inv.post(f"/branch-transfers/{t['id']}/receive", {"to_location_id": locs["Dry store"]}).json()["error"]["code"] == "WRONG_BRANCH"
    line = t["lines"][0]["id"]
    short = {"to_location_id": bkk_locs["Dry store"], "lines": [{"line_id": line, "qty_received": "3.5"}]}
    assert inv.post(f"/branch-transfers/{t['id']}/receive", short, headers=bkk).json()["error"]["code"] == "VARIANCE_REASON_REQUIRED"
    short["lines"][0]["variance_reason"] = "Bag torn in transit"
    r = inv.post(f"/branch-transfers/{t['id']}/receive", short, headers=bkk).json()
    assert r["status"] == "Received" and money(r["lines"][0]["variance_qty"]) == Decimal("0.5")
    assert bal(inv, "ING-001", "Dry store", bkk) == Decimal("3.5")
    bkk_row = next(x for x in inv.get("/inventory/balances", headers=bkk).json() if x["ingredient_code"] == "ING-001")
    assert money(bkk_row["avg_cost"]) == 2  # carried at the source's cost
    assert inv.post(f"/branch-transfers/{t['id']}/receive", short, headers=bkk).json()["error"]["code"] == "TRANSFER_NOT_IN_TRANSIT"
    # cancel while in transit: only the sender, and the stock comes back
    t2 = inv.post("/branch-transfers", {**body, "lines": [{"ingredient_id": items["ING-001"], "quantity": "1", "uom_id": units["kg"]}]}).json()
    assert bal(inv, "ING-001", "Dry store") == 5
    assert inv.post(f"/branch-transfers/{t2['id']}/cancel", {"reason": "Driver unavailable"}, headers=bkk).json()["error"]["code"] == "WRONG_BRANCH"
    assert inv.post(f"/branch-transfers/{t2['id']}/cancel", {"reason": "Driver unavailable"}).json()["status"] == "Cancelled"
    assert bal(inv, "ING-001", "Dry store") == 6
    assert api("cook").get(f"/branch-transfers/{t['id']}").status_code == 403  # no inventory.view


def test_consolidated_comparison_and_rpt06(api, seeded):
    b, bkk = second_branch(api, seeded, "owner", "cashier")
    c = api("cashier")
    m = menu(c)
    paid_order(c, m)  # Riverside 9.50

    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "B", "items": [line(m, "MN-02", 1)]}, idem=True, headers=bkk).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}, headers=bkk).json()[0]
    # order numbers restart per branch, so the bank reference must differ from Riverside's
    assert c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": "KQ-BKK-1"}, idem=True, headers=bkk).status_code == 201
    owner = api("owner")
    cmp = owner.get("/branch-comparison").json()
    assert [r["branch"] for r in cmp["rows"]] == ["BKK", "RVS"]
    assert all(money(r["net_sales"]) == Decimal("9.50") for r in cmp["rows"]) and money(cmp["total"]["net_sales"]) == Decimal("19.00")
    r06 = owner.get("/reports/RPT-06").json()
    assert money(r06["summary"]["consolidated"]["net_sales"]) == Decimal("19.00") and len(r06["rows"]) == 2
    assert api("gm").get("/reports/RPT-06").status_code == 403  # no report.cross_branch
    assert api("gm").get("/branch-comparison").json()["error"]["code"] == "REPORT_FORBIDDEN"
    only_rvs = owner.get(f"/branch-comparison?branch_ids={seeded['branch_id']}").json()
    assert [r["branch"] for r in only_rvs["rows"]] == ["RVS"]
