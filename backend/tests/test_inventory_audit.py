"""SRS §16.10 (INV) and §16.21 (AUD)."""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.helpers import money


def refs(u):
    units = {x["code"]: x["id"] for x in u.get("/inventory/units").json()}
    locs = {x["name"]: x["id"] for x in u.get("/inventory/locations").json()}
    items = {x["code"]: x["id"] for x in u.get("/inventory/items").json()}
    return units, locs, items


def post_doc(u, doc_type, loc, lines, reason=None):
    d = u.post("/inventory/documents", {"doc_type": doc_type, "location_id": loc, "reason": reason, "lines": lines})
    assert d.status_code == 201, d.text
    return u.post(f"/inventory/documents/{d.json()['id']}/post")


def on_hand(u, ingredient_id):
    return next((money(b["quantity"]) for b in u.get("/inventory/balances").json() if b["ingredient_id"] == ingredient_id), Decimal(0))


def test_at_inv_01_receipt_posts_once(api):
    u = api("invoff")
    units, locs, items = refs(u)
    rice = items["ING-001"]
    post_doc(u, "Opening", locs["Dry store"], [{"ingredient_id": rice, "quantity": "10", "uom_id": units["kg"], "unit_cost": "1.00"}])
    d = u.post("/inventory/documents", {"doc_type": "Receipt", "location_id": locs["Dry store"], "lines": [{"ingredient_id": rice, "quantity": "25000", "uom_id": units["g"], "unit_cost": "0.0012"}]}).json()
    a = u.post(f"/inventory/documents/{d['id']}/post").json()
    b = u.post(f"/inventory/documents/{d['id']}/post").json()
    assert a["status"] == b["status"] == "Posted"
    assert on_hand(u, rice) == Decimal("35")
    receipts = u.get(f"/inventory/transactions?ingredient_id={rice}&txn_type=RECEIPT").json()
    assert receipts["total"] == 1


def test_at_inv_02_no_direct_edit(api):
    u = api("invoff")
    _, _, items = refs(u)
    r = u.patch(f"/inventory/items/{items['ING-001']}", {"quantity": "999"})
    assert r.status_code == 422  # unknown field rejected; there is no endpoint that sets on-hand


def test_at_inv_04_correction_by_reversal_and_threshold(api):
    u, gm = api("invoff"), api("gm")
    units, locs, items = refs(u)
    pork = items["ING-011"]
    post_doc(u, "Opening", locs["Chiller"], [{"ingredient_id": pork, "quantity": "10", "uom_id": units["kg"], "unit_cost": "5.00"}])
    wrong = post_doc(u, "Wastage", locs["Chiller"], [{"ingredient_id": pork, "quantity": "2", "uom_id": units["kg"]}], "Spoiled").json()
    assert wrong["status"] == "Posted"  # value 10.00 is within the officer's 25.00 threshold
    waste = u.get(f"/inventory/transactions?ingredient_id={pork}&txn_type=WASTE").json()["data"][0]
    assert u.post(f"/inventory/transactions/{waste['id']}/reverse", {"reason": "Entered 2 instead of 0.2"}).status_code == 201
    assert u.post(f"/inventory/transactions/{waste['id']}/reverse", {"reason": "again"}).json()["error"]["code"] == "ALREADY_REVERSED"
    post_doc(u, "Wastage", locs["Chiller"], [{"ingredient_id": pork, "quantity": "0.2", "uom_id": units["kg"]}], "Spoiled")
    hist = [(t["txn_type"], money(t["quantity"])) for t in reversed(u.get(f"/inventory/transactions?ingredient_id={pork}").json()["data"])]
    assert hist == [("OPENING", Decimal("10")), ("WASTE", Decimal("-2")), ("REVERSAL", Decimal("2")), ("WASTE", Decimal("-0.2"))]
    assert on_hand(u, pork) == Decimal("9.8")
    # above threshold → pending approval by someone else
    big = post_doc(u, "Adjustment", locs["Chiller"], [{"ingredient_id": pork, "quantity": "-8", "uom_id": units["kg"]}], "Count correction").json()
    assert big["status"] == "PendingApproval" and on_hand(u, pork) == Decimal("9.8")
    assert gm.post(f"/inventory/documents/{big['id']}/decision", {"approve": True}).json()["status"] == "Posted"
    docs = u.get("/inventory/documents?doc_type=Adjustment").json()
    assert docs[0]["id"] == big["id"] and docs[0]["created_at"] and all(d["doc_type"] == "Adjustment" for d in docs)
    assert on_hand(u, pork) == Decimal("1.8")


def test_negative_stock_and_unit_rules(api):
    u = api("invoff")
    units, locs, items = refs(u)
    r = post_doc(u, "Issue", locs["Dry store"], [{"ingredient_id": items["ING-002"], "quantity": "1", "uom_id": units["kg"]}], "Staff meal")
    assert r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    r = u.post("/inventory/documents", {"doc_type": "Receipt", "location_id": locs["Dry store"], "lines": [{"ingredient_id": items["ING-001"], "quantity": "1", "uom_id": units["L"], "unit_cost": "1"}]})
    assert r.json()["error"]["code"] == "UNIT_INCOMPATIBLE"


def test_audit_chain_and_append_only(api, engine):
    gm = api("gm")
    gm.get("/menu/pos")
    api("cashier").post("/cashier-sessions", {"floats": {"USD": "10"}})
    integrity = api("auditor").get("/audit-logs/integrity").json()
    assert integrity["valid"] and integrity["checked"] >= 3
    assert api("auditor").get("/audit-logs?action=auth.login").json()["total"] >= 2
    with engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text("update audit_logs set action='tampered' where id=1"))
        conn.rollback()
        with pytest.raises(DBAPIError):
            conn.execute(text("delete from audit_logs"))
        conn.rollback()
    assert api("waiter").get("/audit-logs").status_code == 403
