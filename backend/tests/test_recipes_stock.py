"""SRS §16.11 (RCP) and §16.10 AT-INV-03, plus transfers, batches and menu-item wastage."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from tests.helpers import line, menu, money


def refs(u):
    units = {x["code"]: x["id"] for x in u.get("/inventory/units").json()}
    locs = {x["name"]: x["id"] for x in u.get("/inventory/locations").json()}
    items = {x["code"]: x["id"] for x in u.get("/inventory/items").json()}
    return units, locs, items


def add_ingredient(inv, code, name, unit_id, cost_loc=None, units=None, cost="0"):
    i = inv.post("/inventory/items", {"code": code, "name_en": name, "category": "Test", "stock_uom_id": unit_id}).json()
    return i["id"]


def opening(inv, loc, ing, qty, uom, cost):
    d = inv.post("/inventory/documents", {"doc_type": "Opening", "location_id": loc, "lines": [{"ingredient_id": ing, "quantity": qty, "uom_id": uom, "unit_cost": cost}]}).json()
    assert inv.post(f"/inventory/documents/{d['id']}/post").json()["status"] == "Posted"


def fried_rice_recipe(km, inv, m, effective=None):
    units, locs, items = refs(inv)
    veg = add_ingredient(inv, "ING-VEG", "Vegetables", units["kg"])
    r = km.post("/recipes", {"variant_id": m["RN-01"]["variants"]["Regular"]}).json()
    v = km.post(f"/recipes/{r['id']}/versions", {"lines": [{"ingredient_id": items["ING-001"], "quantity": "150", "uom_id": units["g"]},
                                                         {"ingredient_id": veg, "quantity": "100", "uom_id": units["g"], "prep_loss_pct": "10"}]}).json()
    assert km.post(f"/recipes/versions/{v['id']}/publish", {"effective_from": effective}).status_code == 200
    return r, v, veg, units, locs, items


def test_at_rcp_01_consumption_once_and_reversal(api, engine):
    km, inv, c = api("gm"), api("invoff"), api("cashier")
    m = menu(c)
    r, v, veg, units, locs, items = fried_rice_recipe(km, inv, m)
    o = c.post("/orders", {"order_type": "DineIn", "table_tag": "1", "items": [line(m, "RN-01", 3, ("Mild",))]}, idem=True).json()
    key = "send-rcp-1"
    c.post(f"/orders/{o['id']}/send", idem=key)
    c.post(f"/orders/{o['id']}/send", idem=key)
    with engine.connect() as conn:
        rows = {r[0]: r[1] for r in conn.execute(text("select ingredient_id::text, quantity from inventory_transactions where txn_type='SALE_CONSUMPTION'"))}
    assert rows == {items["ING-001"]: Decimal("-0.4500"), veg: Decimal("-0.3333")}
    # cancelling before preparation puts the ingredients back (BR-014)
    item = c.get(f"/orders/{o['id']}").json()["items"][0]
    api("supv").post(f"/orders/{o['id']}/items/{item['id']}/cancel", {"reason": "Customer changed mind"})
    with engine.connect() as conn:
        rev = conn.execute(text("select sum(quantity) from inventory_transactions where txn_type='SALE_REVERSAL'")).scalar()
    assert rev == Decimal("0.7833")


def test_at_rcp_02_unit_incompatible(api):
    km, inv = api("gm"), api("invoff")
    m = menu(km)
    units, _, _ = refs(inv)
    oil = add_ingredient(inv, "ING-OIL", "Cooking oil", units["L"])
    r = km.post("/recipes", {"variant_id": m["RN-02"]["variants"]["Regular"]}).json()
    res = km.post(f"/recipes/{r['id']}/versions", {"lines": [{"ingredient_id": oil, "quantity": "20", "uom_id": units["g"]}]})
    assert res.status_code == 422 and res.json()["error"]["code"] == "UNIT_INCOMPATIBLE"


def test_at_rcp_03_food_cost(api):
    km, inv = api("gm"), api("invoff")
    m = menu(km)
    units, locs, _ = refs(inv)
    a = add_ingredient(inv, "ING-A", "Cost item", units["kg"])
    opening(inv, locs["Dry store"], a, "10", units["kg"], "1.40")
    r = km.post("/recipes", {"variant_id": m["RN-01"]["variants"]["Regular"]}).json()
    v = km.post(f"/recipes/{r['id']}/versions", {"lines": [{"ingredient_id": a, "quantity": "1", "uom_id": units["kg"]}]}).json()
    km.post(f"/recipes/versions/{v['id']}/publish", {})
    fc = km.get(f"/recipes/{r['id']}/cost").json()
    assert money(fc["cost_per_portion"]) == Decimal("1.40") and money(fc["food_cost_pct"]) == Decimal("28.0") and money(fc["gross_margin"]) == Decimal("3.60")
    assert fc["above_target"] is False


def test_at_rcp_04_versions_effective_dated(api):
    km, inv = api("gm"), api("invoff")
    m = menu(km)
    r, v1, veg, units, locs, items = fried_rice_recipe(km, inv, m)
    v2 = km.post(f"/recipes/{r['id']}/versions", {"lines": [{"ingredient_id": items["ING-001"], "quantity": "200", "uom_id": units["g"]}]}).json()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    km.post(f"/recipes/versions/{v2['id']}/publish", {"effective_from": tomorrow})
    got = km.get(f"/recipes/{r['id']}").json()
    assert got["active_version_id"] == v1["id"] and len(got["versions"]) == 2  # v1 in effect today, v2 scheduled
    assert km.patch(f"/recipes/versions/{v1['id']}", {"yield_qty": "2"}).json()["error"]["code"] == "VERSION_PUBLISHED"
    assert api("cook").post("/recipes", {"variant_id": m["MN-01"]["variants"]["Regular"]}).status_code == 403


def test_unmapped_items(api):
    c = api("cashier")
    m = menu(c)
    c.post("/orders", {"order_type": "DineIn", "table_tag": "2", "items": [line(m, "DR-03")]}, idem=True)
    names = [x["item"] for x in api("gm").get("/recipes/unmapped-items").json()]
    assert "Bottled Water" in names


def test_at_inv_03_blind_count_and_variance(api, engine):
    inv, gm = api("invoff"), api("gm")
    units, locs, items = refs(inv)
    milk = add_ingredient(inv, "ING-MILK", "Milk", units["L"])
    opening(inv, locs["Chiller"], milk, "12", units["L"], "1.00")
    c = inv.post("/inventory/counts", {"location_id": locs["Chiller"], "ingredient_ids": [milk]}).json()
    assert "system_qty" not in c["lines"][0]  # blind
    inv.put(f"/inventory/counts/{c['id']}/lines", {"lines": [{"ingredient_id": milk, "quantity": "11500", "uom_id": units["ml"]}]})
    sub = inv.post(f"/inventory/counts/{c['id']}/submit").json()
    assert money(sub["lines"][0]["variance"]) == Decimal("-0.5")
    assert inv.post(f"/inventory/counts/{c['id']}/decision", {"approve": True}).status_code == 403  # no inventory.approve, and own count
    assert gm.post(f"/inventory/counts/{c['id']}/decision", {"approve": True}).json()["status"] == "Posted"
    with engine.connect() as conn:
        q = conn.execute(text("select quantity, source_type from inventory_transactions where txn_type='COUNT_ADJUSTMENT'")).one()
    assert q == (Decimal("-0.5000"), "StockCount")


def test_transfer_batches_and_menu_wastage(api):
    inv, gm = api("invoff"), api("gm")
    m = menu(gm)
    units, locs, items = refs(inv)
    rice = items["ING-001"]
    d = inv.post("/inventory/documents", {"doc_type": "Receipt", "location_id": locs["Dry store"], "lines": [
        {"ingredient_id": rice, "quantity": "20", "uom_id": units["kg"], "unit_cost": "1.10", "batch_no": "R-77", "expiry_date": (datetime.now().date() + timedelta(days=2)).isoformat()}]}).json()
    inv.post(f"/inventory/documents/{d['id']}/post")
    t = inv.post("/inventory/transfers", {"from_location_id": locs["Dry store"], "to_location_id": locs["Chiller"], "lines": [{"ingredient_id": rice, "quantity": "5", "uom_id": units["kg"]}]})
    assert t.status_code == 201
    bal = {(b["location_name"], b["ingredient_code"]): b for b in inv.get("/inventory/balances").json()}
    assert money(bal[("Dry store", "ING-001")]["quantity"]) == 15 and money(bal[("Chiller", "ING-001")]["quantity"]) == 5
    assert money(bal[("Chiller", "ING-001")]["avg_cost"]) == Decimal("1.1")
    too_much = inv.post("/inventory/transfers", {"from_location_id": locs["Chiller"], "to_location_id": locs["Bar"], "lines": [{"ingredient_id": rice, "quantity": "50", "uom_id": units["kg"]}]})
    assert too_much.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    exp = inv.get("/inventory/expiring?days=3").json()
    assert exp[0]["batch_no"] == "R-77"
    # menu-item wastage converts through the recipe
    fried_rice_recipe(gm, inv, m)
    w = inv.post("/inventory/menu-wastage", {"variant_id": m["RN-01"]["variants"]["Regular"], "quantity": "2", "reason": "Dropped"}).json()
    assert {money(x["quantity"]) for x in w["transactions"]} == {Decimal("-0.3"), Decimal("-0.2222")}
