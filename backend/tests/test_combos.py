"""FR-MENU-005 combo meals. The combo price is shared across the chosen items in proportion to their normal prices (owner's decision)."""
from decimal import Decimal

from tests.helpers import menu, money


def make_combo(gm, price="10.00", noodle_delta="0") -> dict:
    """Lunch set: one main (Kuy Teav $4.50 or Lok Lak Large $12.50 +$2) and one drink (water $1 or beer $2.50)."""
    cats = gm.get("/menu-categories").json()
    tax = gm.get("/tax-profiles").json()[0]
    m = menu(gm)
    r = gm.post("/menu-items", {"code": "CB-01", "name_en": "Lunch set", "category_id": cats[0]["id"], "item_type": "Combo", "tax_profile_id": tax["id"],
                                "variants": [{"name_en": "Regular", "price": price}]})
    assert r.status_code == 201, r.json()
    combo = r.json()
    slots = gm.put(f"/menu-items/{combo['id']}/combo-slots", {"slots": [
        {"name_en": "Main", "min_select": 1, "max_select": 1, "options": [
            {"variant_id": m["RN-03"]["variants"]["Regular"], "price_delta": noodle_delta},
            {"variant_id": m["MN-02"]["variants"]["Large"], "price_delta": "2.00"}]},
        {"name_en": "Drink", "min_select": 1, "max_select": 1, "options": [
            {"variant_id": m["DR-03"]["variants"]["Regular"]}, {"variant_id": m["BR-01"]["variants"]["Regular"]}]},
    ]})
    assert slots.status_code == 200, slots.json()
    s = {x["name_en"]: {o["item_name_en"]: o["variant_id"] for o in x["options"]} | {"_id": x["id"]} for x in slots.json()}
    return {"item": combo, "variant": combo["variants"][0]["id"], "slots": s}


def pick(c: dict, main: str, drink: str) -> list[dict]:
    return [{"slot_id": c["slots"]["Main"]["_id"], "variant_id": c["slots"]["Main"][main]},
            {"slot_id": c["slots"]["Drink"]["_id"], "variant_id": c["slots"]["Drink"][drink]}]


def test_combo_price_is_split_across_items_and_routed_to_the_kitchen(api):
    gm, c, cook = api("gm"), api("cashier"), api("cook")
    combo = make_combo(gm)
    pos = next(i for i in c.get("/menu/pos").json()["items"] if i["code"] == "CB-01")
    assert [s["name_en"] for s in pos["combo_slots"]] == ["Main", "Drink"]
    o = c.post("/orders", {"order_type": "DineIn", "table_tag": "9", "items": [
        {"variant_id": combo["variant"], "quantity": "2", "combo": pick(combo, "Beef Lok Lak", "Draft Beer")}]}, idem=True)
    assert o.status_code == 201, o.json()
    o = o.json()
    header = next(i for i in o["items"] if i["parent_item_id"] is None)
    kids = [i for i in o["items"] if i["parent_item_id"] == header["id"]]
    assert money(header["unit_price_snapshot"]) == 0 and header["station_code"] is None
    assert {k["item_name_en_snapshot"]: k["combo_slot_name"] for k in kids} == {"Beef Lok Lak": "Main", "Draft Beer": "Drink"}
    assert all(money(k["quantity"]) == 2 for k in kids)
    # $10 combo + $2 for the Lok Lak = $12 per set, shared 12.50 : 2.50
    units = {k["item_name_en_snapshot"]: money(k["unit_price_snapshot"]) for k in kids}
    assert sum(units.values()) == Decimal("12.00")
    assert units["Beef Lok Lak"] == Decimal("10.00") and units["Draft Beer"] == Decimal("2.00")
    assert money(o["totals"]["gross"]) == Decimal("24.00")
    # Each item goes to its own station; the combo line itself doesn't
    assert c.post(f"/orders/{o['id']}/send", idem=True).status_code == 200
    hot = [t for t in cook.get("/kitchen/stations/HOT/open-tickets").json() if t["order_id"] == o["id"]]
    assert [i["name_en"] for t in hot for i in t["items"]] == ["Beef Lok Lak"]
    now = c.get(f"/orders/{o['id']}").json()
    assert next(i for i in now["items"] if i["id"] == header["id"])["item_status"] == "Sent"  # follows its least advanced item
    # Combos are a set price: no automatic promotions or item discounts on their lines
    r = c.post(f"/orders/{o['id']}/discounts", {"order_item_id": kids[0]["id"], "kind": "Percent", "value": "5", "reason": "Regular guest"})
    assert r.json()["error"]["code"] == "COMBO_DISCOUNT"


def test_combo_choices_are_validated(api):
    gm, c = api("gm"), api("cashier")
    combo = make_combo(gm)
    m = menu(c)
    base = {"order_type": "Takeaway", "pickup_name": "V"}
    one = pick(combo, "Kuy Teav Pork Noodle", "Bottled Water")
    r = c.post("/orders", {**base, "items": [{"variant_id": combo["variant"], "quantity": "1", "combo": one[:1]}]}, idem=True)
    assert r.json()["error"]["code"] == "COMBO_CHOICE_REQUIRED"
    r = c.post("/orders", {**base, "items": [{"variant_id": combo["variant"], "quantity": "1", "combo": one + [one[1]]}]}, idem=True)
    assert r.json()["error"]["code"] == "COMBO_CHOICE_LIMIT"
    wrong = [one[0], {"slot_id": combo["slots"]["Drink"]["_id"], "variant_id": m["RN-01"]["variants"]["Regular"]}]
    r = c.post("/orders", {**base, "items": [{"variant_id": combo["variant"], "quantity": "1", "combo": wrong}]}, idem=True)
    assert r.json()["error"]["code"] == "COMBO_CHOICE_INVALID"
    r = c.post("/orders", {**base, "items": [{"variant_id": m["DR-03"]["variants"]["Regular"], "quantity": "1", "combo": one}]}, idem=True)
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    # Slot setup rules
    item_id = combo["item"]["id"]
    bad = {"slots": [{"name_en": "Main", "min_select": 2, "max_select": 2, "options": [{"variant_id": m["RN-03"]["variants"]["Regular"]}]}]}
    assert gm.put(f"/menu-items/{item_id}/combo-slots", bad).json()["error"]["code"] == "VALIDATION_ERROR"
    nested = {"slots": [{"name_en": "Main", "options": [{"variant_id": combo["variant"]}]}]}
    assert gm.put(f"/menu-items/{item_id}/combo-slots", nested).json()["error"]["code"] == "VALIDATION_ERROR"
    assert gm.put(f"/menu-items/{m['RN-03']['id']}/combo-slots", {"slots": bad["slots"]}).json()["error"]["code"] == "NOT_A_COMBO"
    assert c.put(f"/menu-items/{item_id}/combo-slots", {"slots": bad["slots"]}).status_code == 403
    # Unavailable items can't be chosen
    assert gm.post(f"/menu-items/{m['RN-03']['id']}/availability", {"available": False}).status_code in (200, 201)
    r = c.post("/orders", {**base, "items": [{"variant_id": combo["variant"], "quantity": "1", "combo": one}]}, idem=True)
    assert r.json()["error"]["code"] == "ITEM_UNAVAILABLE"


def test_combo_quantity_and_cancellation_act_on_the_whole_set(api):
    gm, c, s, cook = api("gm"), api("cashier"), api("supv"), api("cook")
    combo = make_combo(gm)
    o = c.post("/orders", {"order_type": "DineIn", "table_tag": "8", "items": [
        {"variant_id": combo["variant"], "quantity": "1", "combo": pick(combo, "Kuy Teav Pork Noodle", "Bottled Water")}]}, idem=True).json()
    header = next(i for i in o["items"] if i["parent_item_id"] is None)
    kids = [i for i in o["items"] if i["parent_item_id"]]
    assert sum(money(k["unit_price_snapshot"]) for k in kids) == Decimal("10.00")
    assert c.patch(f"/orders/{o['id']}/items/{kids[0]['id']}", {"quantity": "3"}).json()["error"]["code"] == "COMBO_PART"
    r = c.patch(f"/orders/{o['id']}/items/{header['id']}", {"quantity": "3"})
    assert r.status_code == 200, r.json()
    now = c.get(f"/orders/{o['id']}").json()
    assert all(money(i["quantity"]) == 3 for i in now["items"]) and money(now["totals"]["gross"]) == Decimal("30.00")
    # Cancel: a part alone is refused; the whole set needs one approval once something is prepared
    c.post(f"/orders/{o['id']}/send", idem=True)
    noodle = next(k for k in kids if k["item_name_en_snapshot"] == "Kuy Teav Pork Noodle")
    assert cook.post(f"/kitchen/items/{noodle['id']}/status", {"status": "InPreparation"}).status_code == 200
    assert s.post(f"/orders/{o['id']}/items/{noodle['id']}/cancel", {"reason": "Wrong one"}).json()["error"]["code"] == "COMBO_PART"
    r = s.post(f"/orders/{o['id']}/items/{header['id']}/cancel", {"reason": "Wrong order"})
    assert r.status_code in (403, 409, 422), r.json()
    line_net = c.get(f"/orders/{o['id']}").json()
    # The noodle is being cooked and the water (no station) was ready at send: both count as prepared
    amount = str(sum(money(i["line_net"]) for i in line_net["items"] if i["parent_item_id"]))
    ap = s.post("/approvals", {"action": "void", "approver_username": "gm", "approver_secret": "5937", "amount": amount, "target_id": header["id"]}).json()
    r = s.post(f"/orders/{o['id']}/items/{header['id']}/cancel", {"reason": "Wrong order", "approval_id": ap["approval_id"]})
    assert r.status_code == 200, r.json()
    done = c.get(f"/orders/{o['id']}").json()
    assert all(i["item_status"] == "Cancelled" for i in done["items"]) and money(done["totals"]["grand_total"]) == 0
