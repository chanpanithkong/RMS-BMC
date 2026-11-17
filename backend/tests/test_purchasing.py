"""SRS §16.12 (PUR)."""
from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import money


def refs(u):
    units = {x["code"]: x["id"] for x in u.get("/inventory/units").json()}
    locs = {x["name"]: x["id"] for x in u.get("/inventory/locations").json()}
    items = {x["code"]: x["id"] for x in u.get("/inventory/items").json()}
    return units, locs, items


def setup_po(p, gm, qty="50", price="16", approve=True, send=True):
    units, locs, items = refs(p)
    s = p.post("/suppliers", {"name": "Golden Grain Co.", "contact_person": "Sophal", "phone": "023 880 112", "email": "sales@example.com"}).json()
    po = p.post("/purchase-orders", {"supplier_id": s["id"], "location_id": locs["Dry store"], "lines": [{"ingredient_id": items["ING-001"], "qty_ordered": qty,
                                                                                                          "uom_id": units["kg"], "unit_price": price}]}).json()
    p.post(f"/purchase-orders/{po['id']}/submit")
    if approve:
        assert gm.post(f"/purchase-orders/{po['id']}/approve").json()["status"] == "Approved"
    if send:
        p.post(f"/purchase-orders/{po['id']}/send")
    return s, po, units, locs, items


def on_hand(u, code):
    return sum((money(b["quantity"]) for b in u.get("/inventory/balances").json() if b["ingredient_code"] == code), Decimal(0))


def test_at_pur_01_approval_segregation_and_bands(api):
    p, gm, mgr = api("puroff"), api("gm"), api("supv")
    s, po, *_ = setup_po(p, gm, qty="50", price="16", approve=False, send=False)  # 800.00
    assert money(po["total"]) == Decimal("800")
    assert p.post(f"/purchase-orders/{po['id']}/approve").status_code == 403  # purchasing officer can't approve
    assert mgr.post(f"/purchase-orders/{po['id']}/approve").status_code == 403  # supervisor has no purchase approval
    over = api("brmgr").post(f"/purchase-orders/{po['id']}/approve")  # 800 > branch manager band of 500
    assert over.json()["error"]["code"] == "APPROVER_LIMIT_EXCEEDED"
    assert gm.post(f"/purchase-orders/{po['id']}/approve").json()["status"] == "Approved"
    # changing an approved PO sends it back for approval (BR-017)
    units, _, items = refs(p)
    r = p.put(f"/purchase-orders/{po['id']}/lines", {"lines": [{"ingredient_id": items["ING-001"], "qty_ordered": "60", "uom_id": units["kg"], "unit_price": "16"}]}).json()
    assert r["status"] == "Submitted"


def test_at_pur_02_receipt_posts_once(api):
    p, gm, inv = api("puroff"), api("gm"), api("invoff")
    s, po, units, locs, items = setup_po(p, gm, qty="20", price="1.10")
    before = on_hand(inv, "ING-001")
    gr = inv.post("/goods-receipts", {"po_id": po["id"], "lines": [{"po_item_id": po["lines"][0]["id"], "qty_received": "20"}]}).json()
    a = inv.post(f"/goods-receipts/{gr['id']}/post").json()
    b = inv.post(f"/goods-receipts/{gr['id']}/post").json()
    assert a["status"] == b["status"] == "Posted"
    assert on_hand(inv, "ING-001") - before == Decimal("20")
    assert p.get(f"/purchase-orders/{po['id']}").json()["status"] == "Received"


def test_at_pur_03_over_receipt_needs_approval_then_invoice_and_payment(api):
    p, gm, inv, acct = api("puroff"), api("gm"), api("invoff"), api("acct")
    s, po, units, locs, items = setup_po(p, gm, qty="50", price="1")
    gr = inv.post("/goods-receipts", {"po_id": po["id"], "lines": [{"po_item_id": po["lines"][0]["id"], "qty_received": "55", "batch_no": "B1",
                                                                   "expiry_date": (date.today() + timedelta(days=200)).isoformat()}]}).json()
    pending = inv.post(f"/goods-receipts/{gr['id']}/post").json()
    assert pending["status"] == "PendingApproval" and "55" in pending["exception_note"]
    assert inv.post(f"/goods-receipts/{gr['id']}/approve").status_code == 403
    assert gm.post(f"/goods-receipts/{gr['id']}/approve").json()["status"] == "Posted"
    # return damaged goods
    gr_line = gm.get("/goods-receipts").json()[0]["lines"][0]["id"]
    ret = inv.post("/purchase-returns", {"gr_id": gr["id"], "reason": "Damaged bags", "lines": [{"gr_item_id": gr_line, "quantity": "5"}]}).json()
    assert money(ret["total_value"]) == Decimal("5")
    # invoice matching: 55 received - 5 returned = 50
    inv1 = acct.post("/supplier-invoices", {"supplier_id": s["id"], "invoice_no": "INV-1", "invoice_date": date.today().isoformat(),
                                            "due_date": (date.today() + timedelta(days=30)).isoformat(), "amount": "50.00", "gr_ids": [gr["id"]]}).json()
    assert inv1["match_status"] == "Matched"
    dup = acct.post("/supplier-invoices", {"supplier_id": s["id"], "invoice_no": "INV-1", "invoice_date": date.today().isoformat(), "due_date": date.today().isoformat(), "amount": "1"})
    assert dup.json()["error"]["code"] == "INVOICE_EXISTS"
    assert acct.post(f"/supplier-invoices/{inv1['id']}/payments", {"amount": "60", "method": "BANK_TRANSFER"}).json()["error"]["code"] == "PAYMENT_EXCEEDS_BALANCE"
    assert acct.post(f"/supplier-invoices/{inv1['id']}/payments", {"amount": "50", "method": "BANK_TRANSFER", "reference": "BT-1"}).json()["status"] == "Paid"
    hist = gm.get(f"/suppliers/{s['id']}/history").json()
    assert money(hist["balance"]) == 0 and hist["invoices"][0]["status"] == "Paid"


def test_requests_low_stock_and_conversion(api):
    p, k, gm = api("puroff"), api("kmgr"), api("gm")
    sugg = p.get("/reorder-suggestions").json()
    assert any(x["ingredient"] == "Jasmine rice" for x in sugg)  # 0 on hand ≤ reorder level 15
    r = k.post("/purchase-requests/from-low-stock").json()
    assert r["lines"] >= 1
    assert k.post(f"/purchase-requests/{r['id']}/approve").status_code == 403
    assert gm.post(f"/purchase-requests/{r['id']}/approve").json()["status"] == "Approved"
    units, locs, items = refs(p)
    s = p.post("/suppliers", {"name": "Green Valley", "contact_person": "Rin", "phone": "015 208 441"}).json()
    po = p.post("/purchase-orders", {"supplier_id": s["id"], "location_id": locs["Chiller"], "request_id": r["id"],
                                     "lines": [{"ingredient_id": items["ING-001"], "qty_ordered": "50", "uom_id": units["kg"], "unit_price": "1"}]})
    assert po.status_code == 201
    assert p.get("/purchase-requests").json()[0]["status"] == "Converted"


def test_sent_po_is_emailed_by_the_outbox_worker(api, engine, monkeypatch):
    from sqlalchemy import text

    from app.workers import celery_app

    sent = []
    monkeypatch.setattr(celery_app.EmailSender, "send", lambda self, to, subject, body: sent.append((to, subject, body)))
    setup_po(api("puroff"), api("gm"), qty="50", price="1.10")
    assert celery_app.process_outbox() == 1
    to, subject, body = sent[0]
    assert to == "sales@example.com" and subject.startswith("Purchase order PO-")
    assert "Jasmine rice: 50" in body and "kg at 1.1" in body and "Total: 55" in body
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from outbox_events where processed_at is null")).scalar() == 0
