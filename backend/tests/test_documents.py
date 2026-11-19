"""Printable bill and receipt document (SRS §6.7, BR-049 reprints marked COPY)."""
from decimal import Decimal

from tests.helpers import line, menu, money


def test_bill_then_receipt_document(api):
    c, cook = api("cashier"), api("cook")
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "Dara", "items": [line(m, "DR-03", 2), line(m, "MN-01", 1, ("Mild",))]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    d = c.get(f"/bills/{bill['id']}/document").json()
    assert d["kind"] == "Bill" and d["receipt"] is None and d["copy_label"] is None
    assert d["order"]["order_no"] == o["order_no"] and d["order"]["pickup_name"] == "Dara"
    names = {ln["name_en"]: ln for ln in d["lines"]}
    assert money(names["Bottled Water"]["quantity"]) == 2 and names["Fish Amok"]["modifiers"] == ["Mild"]
    assert money(d["totals"]["total"]) == money(bill["total"]) and d["restaurant"]["name_en"] and d["branch"]["name_en"]
    assert {ch["type"] for ch in d["charges"]} >= {"Tax"}
    assert d["khr_rate"] is not None
    # Paid: it becomes a receipt with the payment and change
    p = c.post("/payments", {"bill_id": bill["id"], "method": "CARD", "currency": "USD", "reference": "TID-77", "card_last4": "4242"}, idem=True)
    assert p.status_code == 201, p.json()
    r = c.get(f"/bills/{bill['id']}/document").json()
    assert r["kind"] == "Receipt" and r["receipt"]["receipt_no"] and r["copy_label"] is None
    assert r["payments"][0]["card_last4"] == "4242" and money(r["payments"][0]["applied"]) == money(bill["total"])
    assert money(r["totals"]["balance"]) == 0
    # A reprint is marked COPY 1 (BR-049)
    c.post(f"/bills/{bill['id']}/receipt/reprint")
    assert c.get(f"/bills/{bill['id']}/document").json()["copy_label"] == "COPY 1"
    assert cook.get(f"/bills/{bill['id']}/document").status_code == 403


def test_combo_prints_as_one_line(api):
    gm, c = api("gm"), api("cashier")
    from tests.test_combos import make_combo, pick

    combo = make_combo(gm)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "C", "items": [
        {"variant_id": combo["variant"], "quantity": "1", "combo": pick(combo, "Beef Lok Lak", "Draft Beer")}]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    d = c.get(f"/bills/{bill['id']}/document").json()
    assert len(d["lines"]) == 1
    ln = d["lines"][0]
    assert ln["name_en"] == "Lunch set" and ln["parts"] == ["Main: Beef Lok Lak", "Drink: Draft Beer"]
    assert money(ln["amount_gross"]) == Decimal("12.00")
