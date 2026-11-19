"""Phase 2 reports (SRS §11.3: RPT-05, 08, 09, 10, 15, 16, 19, 20, 21, 22, 23, 25, 26) and dashboard trends and cost widgets (FR-DASH-010, 011, 013)."""
from datetime import date
from decimal import Decimal

from tests.helpers import line, menu, money, tables
from tests.test_purchasing import setup_po
from tests.test_recipes_stock import opening, refs


def full_cycle(w, c, cook, m, table_code, items, customer_id=None):
    """Seat, order, send, bump, serve and pay so the order completes (BR-031)."""
    oid = w.post(f"/tables/{tables(w)[table_code]['id']}/seat", {"guest_count": 2}).json()["order_id"]
    w.post(f"/orders/{oid}/items", items)
    if customer_id:
        assert w.post(f"/customers/attach/{oid}", {"customer_id": customer_id}).status_code == 200
    w.post(f"/orders/{oid}/send", idem=True)
    for station in {"HOT"}:
        for t in cook.get(f"/kitchen/stations/{station}/open-tickets").json():
            if t["order_id"] == oid:
                cook.post(f"/kitchen/tickets/{t['ticket_id']}/bump")
    w.post(f"/orders/{oid}/serve", {})
    bill = c.post(f"/orders/{oid}/bills", {"mode": "single"}).json()[0]
    c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": f"KQ-{oid[:8]}"}, idem=True)
    o = c.get(f"/orders/{oid}").json()
    assert o["order_status"] == "Completed", o["order_status"]
    return o


def test_sales_kitchen_and_food_cost_reports(api):
    w, c, cook, gm, inv, kmgr = api("waiter"), api("cashier"), api("cook"), api("gm"), api("invoff"), api("kmgr")
    m = menu(w)
    units, locs, items = refs(inv)
    opening(inv, locs["Dry store"], items["ING-001"], "10", units["kg"], "2.00")  # demo rice is used from the dry store (its default location)
    r = gm.post("/recipes", {"variant_id": m["RN-01"]["variants"]["Regular"]}).json()
    v = gm.post(f"/recipes/{r['id']}/versions", {"lines": [{"ingredient_id": items["ING-001"], "quantity": "200", "uom_id": units["g"]}]}).json()
    gm.post(f"/recipes/versions/{v['id']}/publish", {})
    o = full_cycle(w, c, cook, m, "B1", [line(m, "RN-01", 2, ("Mild",)), line(m, "MN-01", 1, ("Mild",))])
    net = money(o["totals"]["subtotal"])

    r05 = gm.get("/reports/RPT-05").json()
    server = next(x for x in r05["rows"] if x["role"] == "Server")
    assert server["employee"] == "Waiter" and server["orders"] == 1 and server["covers"] == 2 and money(server["net_sales"]) == net
    assert any(x["role"] == "Cashier" and x["employee"] == "Cashier" for x in r05["rows"])

    r08 = gm.get("/reports/RPT-08").json()
    assert r08["rows"][0]["order_type"] == "DineIn" and money(r08["rows"][0]["spend_per_cover"]) == net / 2

    r09 = gm.get("/reports/RPT-09").json()
    assert sum(x["orders"] for x in r09["rows"]) == 1 and r09["summary"]["peak_hour"] is not None

    r10 = api("supv").get("/reports/RPT-10").json()
    assert r10["rows"][0]["table"] == "B1" and r10["rows"][0]["seatings"] == 1 and r10["rows"][0]["covers"] == 2

    r15 = kmgr.get("/reports/RPT-15").json()
    hot = next(x for x in r15["rows"] if x["station_code"] == "HOT")
    assert hot["items"] == 2 and hot["late_items"] == 0 and r15["summary"]["late_threshold_minutes"] == 15

    # 2 portions × 200 g × 2.00/kg = 0.80 theoretical cost
    r16 = inv.get("/reports/RPT-16").json()
    rice = next(x for x in r16["rows"] if x["code"] == "ING-001")
    assert money(rice["theoretical_qty"]) == Decimal("0.4") and money(rice["theoretical_value"]) == Decimal("0.80")

    r23 = gm.get("/reports/RPT-23").json()
    fried = next(x for x in r23["rows"] if money(x["recipe_cost"]) > 0)
    assert money(fried["recipe_cost"]) == Decimal("0.80") and money(fried["unit_cost"]) == Decimal("0.40")
    assert money(fried["gross_margin"]) == money(fried["net_sales"]) - Decimal("0.80")
    assert any(money(x["quantity_without_recipe"]) == 1 for x in r23["rows"])  # MN-01 has no recipe

    d = gm.get("/dashboard?trend=week").json()["widgets"]
    assert money(d["costs"]["theoretical_food_cost"]) == Decimal("0.80")
    assert d["trends"]["grain"] == "week" and d["trends"]["series"][0]["orders"] == 1
    assert "not accounting profit" in d["indicative_operating_result"]["label"]
    assert money(d["indicative_operating_result"]["value"]) == money(d["sales"]["net_sales"]) - Decimal("0.80")


def test_purchase_supplier_expense_and_waste_reports(api):
    p, gm, inv, acct, s = api("puroff"), api("gm"), api("invoff"), api("acct"), api("supv")
    sup, po, units, locs, items = setup_po(p, gm, qty="10", price="1")
    gr = inv.post("/goods-receipts", {"po_id": po["id"], "lines": [{"po_item_id": po["lines"][0]["id"], "qty_received": "10", "unit_cost": "1.20"}]}).json()
    inv.post(f"/goods-receipts/{gr['id']}/post")
    r20 = p.get("/reports/RPT-20").json()
    row = r20["rows"][0]
    assert row["supplier"] == "Golden Grain Co." and money(row["received_value"]) == Decimal("12") and money(row["price_variance"]) == Decimal("2")
    r21 = acct.get(f"/reports/RPT-21?supplier_id={sup['id']}").json()
    assert r21["rows"][0]["receipts"] == 1 and money(r21["rows"][0]["quantity_accuracy_percent"]) == 100

    cat = next(x["id"] for x in s.get("/expense-categories").json() if x["name_en"] == "Water")
    e = s.post("/expenses", {"category_id": cat, "expense_date": date.today().isoformat(), "description": "Bottled water", "amount": "20", "payee": "Shop"}).json()
    s.post(f"/expenses/{e['id']}/submit")
    r22 = acct.get("/reports/RPT-22").json()
    assert money(r22["summary"]["approved_total"]) == Decimal("20") and r22["rows"][0]["category"] == "Water"
    assert money(gm.get("/dashboard").json()["widgets"]["costs"]["approved_expenses"]) == Decimal("20")

    w = inv.post("/inventory/documents", {"doc_type": "Wastage", "location_id": locs["Dry store"], "reason": "Spoiled",
                                          "lines": [{"ingredient_id": items["ING-001"], "quantity": "1", "uom_id": units["kg"]}]})
    assert w.status_code == 201, w.json()
    assert inv.post(f"/inventory/documents/{w.json()['id']}/post").json()["status"] == "Posted"
    r19 = gm.get("/reports/RPT-19").json()
    assert money(r19["rows"][0]["quantity"]) == 1 and money(r19["summary"]["total_value"]) == Decimal("1.2")  # at the 1.20 received cost
    assert r19["summary"]["by_reason"][0]["reason"] == "Spoiled"


def test_report_access_customer_history_and_exceptions(api):
    w, c, cook = api("waiter"), api("cashier"), api("cook")
    m = menu(w)
    cust = c.post("/customers", {"name": "Dara", "phone": "012 345 678"}).json()
    full_cycle(w, c, cook, m, "B2", [line(m, "MN-01", 1, ("Mild",))], customer_id=cust["id"])
    gm = api("gm")
    r25 = gm.get(f"/reports/RPT-25?customer_id={cust['id']}").json()
    assert r25["summary"]["visits"] == 1 and r25["summary"]["phone"].startswith("+855")
    listing = gm.get("/reports/RPT-25").json()
    assert listing["rows"][0]["customer"] == "Dara"

    r26 = api("auditor").get("/reports/RPT-26").json()
    assert r26["summary"]["counts"].get("Sold without recipe", 0) >= 1
    assert cook.get("/reports/RPT-23").status_code == 403
    assert c.get("/reports/RPT-26").status_code == 403
    assert api("kmgr").get("/reports/RPT-05").status_code == 403
    ids = {x["id"] for x in gm.get("/reports").json() if x["available"]}
    assert {"RPT-05", "RPT-08", "RPT-09", "RPT-10", "RPT-15", "RPT-22", "RPT-23", "RPT-25", "RPT-26"} <= ids
    exp = gm.get("/reports/RPT-08/export")
    assert exp.status_code == 200 and "DineIn" in exp.text


def test_purchase_report_uses_business_date_not_utc_date(api, engine):
    """A receipt posted at 05:00 in Phnom Penh is the previous day in UTC but belongs to today's business day (day-end 04:00)."""
    from sqlalchemy import text

    p, gm, inv = api("puroff"), api("gm"), api("invoff")
    sup, po, units, locs, items = setup_po(p, gm, qty="10", price="1")
    gr = inv.post("/goods-receipts", {"po_id": po["id"], "lines": [{"po_item_id": po["lines"][0]["id"], "qty_received": "10"}]}).json()
    inv.post(f"/goods-receipts/{gr['id']}/post")
    biz = gm.get("/auth/me").json().get("business_date") or date.today().isoformat()
    with engine.begin() as conn:
        conn.execute(text("update goods_receipts set posted_at = (CAST(:d AS date) + time '05:00') AT TIME ZONE 'Asia/Phnom_Penh'"), {"d": biz})
        conn.execute(text("update purchase_orders set created_at = (CAST(:d AS date) + time '05:00') AT TIME ZONE 'Asia/Phnom_Penh'"), {"d": biz})
    r = p.get(f"/reports/RPT-20?date_from={biz}&date_to={biz}").json()
    assert r["rows"] and r["rows"][0]["receipts"] == 1 and r["rows"][0]["purchase_orders"] == 1
