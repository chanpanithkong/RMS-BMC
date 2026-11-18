"""Advanced analytics: daily summary tables, menu engineering, background report jobs (NFR-PERF-009)."""
import csv
import io
from decimal import Decimal

from sqlalchemy import text

from tests.helpers import line, menu, money, tables
from tests.test_delivery import bump_all
from tests.test_recipes_stock import opening, refs


def completed_order(api, m, table, lines):
    w, c, cook = api("waiter"), api("cashier"), api("cook")
    oid = w.post(f"/tables/{tables(w)[table]['id']}/seat", {"guest_count": 2}).json()["order_id"]
    w.post(f"/orders/{oid}/items", lines)
    w.post(f"/orders/{oid}/send", idem=True)
    bump_all(cook, oid)
    w.post(f"/orders/{oid}/serve", {})
    bill = c.post(f"/orders/{oid}/bills", {"mode": "single"}).json()[0]
    c.post("/payments", {"bill_id": bill["id"], "method": "KHQR", "currency": "USD", "reference": f"KQ-{oid[:8]}"}, idem=True)
    assert c.get(f"/orders/{oid}").json()["order_status"] == "Completed"
    return oid


def recipe(gm, m, code, grams, units, items):
    r = gm.post("/recipes", {"variant_id": m[code]["variants"]["Regular"]}).json()
    v = gm.post(f"/recipes/{r['id']}/versions", {"lines": [{"ingredient_id": items["ING-001"], "quantity": str(grams), "uom_id": units["g"]}]}).json()
    gm.post(f"/recipes/versions/{v['id']}/publish", {})


def setup_sales(api):
    gm, inv = api("gm"), api("invoff")
    m = menu(gm)
    units, locs, items = refs(inv)
    opening(inv, locs[sorted(locs)[0]], items["ING-001"], "20", units["kg"], "2.00")
    recipe(gm, m, "RN-01", 200, units, items)  # 0.40 per portion
    recipe(gm, m, "MN-01", 100, units, items)  # 0.20 per portion
    completed_order(api, m, "B1", [line(m, "RN-01", 5, ("Mild",)), line(m, "MN-01", 1, ("Mild",)), line(m, "DR-03", 1)])
    return m


def test_daily_summaries(api):
    from app.workers.celery_app import refresh_analytics

    m = setup_sales(api)
    acct = api("acct")
    assert refresh_analytics()["RVS"] > 0
    first = acct.get("/analytics/summary?dimension=item").json()
    refresh_analytics()
    again = acct.get("/analytics/summary?dimension=item").json()
    assert first["rows"] == again["rows"]  # a refresh replaces the day's rows
    items = {r["key"]: r for r in again["rows"]}
    rice = items[m["RN-01"]["id"]]
    assert money(rice["quantity"]) == 5 and money(rice["cost"]) == Decimal("2.00") and money(items[m["DR-03"]["id"]]["cost"]) == 0
    assert again["days_with_data"] == 1 and again["days_in_range"] == 1
    hours = acct.get("/analytics/summary?dimension=hour").json()["rows"]
    assert sum(r["count"] for r in hours) == 1
    assert acct.get("/analytics/summary?dimension=method").json()["rows"][0]["key"] == "KHQR:USD"
    assert acct.get("/analytics/summary?dimension=employee").json()["rows"][0]["label"] == "Waiter"
    ing = acct.get("/analytics/summary?dimension=ingredient").json()["rows"][0]
    assert money(ing["quantity"]) == Decimal("1.1") and money(ing["cost"]) == Decimal("2.20")  # 5 x 200 g + 1 x 100 g of rice at 2.00/kg
    cats = acct.get("/analytics/summary?dimension=category").json()["rows"]
    assert sum(money(r["net"]) for r in cats) == sum(money(r["net"]) for r in again["rows"])
    assert api("cashier").get("/analytics/summary").status_code == 403
    assert acct.get("/analytics/summary?dimension=weather").json()["error"]["code"] == "VALIDATION_ERROR"


def test_menu_engineering(api):
    from app.workers.celery_app import refresh_analytics

    m = setup_sales(api)
    refresh_analytics()
    me = api("gm").get("/analytics/menu-engineering").json()
    rows = {r["menu_item_id"]: r for r in me["rows"]}
    assert me["items_classified"] == 2 and money(me["popularity_threshold_percent"]) == 35
    rice, beef, water = rows[m["RN-01"]["id"]], rows[m["MN-01"]["id"]], rows[m["DR-03"]["id"]]
    assert water["classification"] == "Unclassified"  # no recipe cost
    assert money(rice["menu_mix_percent"]) > 35 and money(beef["menu_mix_percent"]) < 35
    avg = money(me["average_contribution_margin"])
    for r in (rice, beef):
        high_pop, high_cm = money(r["menu_mix_percent"]) >= 35, money(r["contribution_margin_per_unit"]) >= avg
        assert r["classification"] == {(True, True): "Star", (True, False): "Plowhorse", (False, True): "Puzzle", (False, False): "Dog"}[(high_pop, high_cm)]
    assert sum(me["counts"].values()) == 3


def test_background_report_jobs(api, engine):
    from app.workers.celery_app import process_report_jobs

    c, acct = api("cashier"), api("acct")
    setup_sales(api)
    assert c.post("/reports/RPT-04/jobs", {}).status_code == 403
    job = acct.post("/reports/RPT-04/jobs", {"date_from": "2026-01-01"}).json()
    assert job["status"] == "Queued" and job["download"] is None and job["params"]["date_from"] == "2026-01-01"
    bad = acct.post("/reports/RPT-25/jobs", {"customer_id": "00000000-0000-0000-0000-000000000000"}).json()
    assert acct.post("/reports/RPT-99/jobs", {}).status_code == 404
    out = process_report_jobs()
    assert out["done"] == 1 and out["failed"] == 1
    failed = acct.get(f"/report-jobs/{bad['id']}").json()
    assert failed["status"] == "Failed" and failed["error"] and failed["download"] is None  # the reason is kept for the user
    j = acct.get(f"/report-jobs/{job['id']}").json()
    assert j["status"] == "Done" and j["rows"] >= 3 and j["download"].endswith("/download")
    res = acct.get(f"/report-jobs/{job['id']}/download")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.text.lstrip("\ufeff"))))
    assert rows[0][0] == "name" and any("Fried Rice" in r[0] for r in rows[1:] if r)
    assert api("owner").get(f"/report-jobs/{job['id']}/download").status_code == 404  # requester only
    assert api("auditor").get("/audit-logs?action=report.export").json()["total"] == 1
    with engine.begin() as conn:
        conn.execute(text("update report_jobs set expires_at = now() - interval '1 minute'"))
    assert process_report_jobs()["expired"] == 1
    assert acct.get(f"/report-jobs/{job['id']}/download").json()["error"]["code"] == "REPORT_NOT_AVAILABLE"
