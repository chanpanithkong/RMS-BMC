"""FR-MENU-008 time-based price lists and menu schedules; BR-003 (sellable only within a schedule); BR-048 (price snapshot)."""
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from tests.helpers import line, menu, money

TZ = ZoneInfo("Asia/Phnom_Penh")


def window(now_inside: bool) -> dict:
    """A two-hour window around (or well away from) the branch's local time now."""
    now = datetime.now(TZ)
    centre = now if now_inside else now + timedelta(hours=12)
    return {"time_from": (centre - timedelta(hours=1)).strftime("%H:%M"), "time_to": (centre + timedelta(hours=1)).strftime("%H:%M")}


def pos_price(api_user, code: str) -> dict:
    item = next(i for i in api_user.get("/menu/pos").json()["items"] if i["code"] == code)
    return item["variants"][0] | {"available": item["available"]}


def test_happy_hour_price_list_applies_by_time_and_channel(api):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    beer = m["BR-01"]
    standard = money(pos_price(c, "BR-01")["price"])
    r = gm.post("/price-lists", {"code": "HAPPY", "name": "Happy hour", "priority": 50, "channels": ["POS"], **window(True)})
    assert r.status_code == 201, r.json()
    hh = r.json()
    happy = standard - Decimal("1.00")
    assert gm.post(f"/menu-items/{beer['id']}/prices", {"variant_id": beer["variants"]["Regular"], "price": str(happy),
                                                      "valid_from": (datetime.now(TZ) - timedelta(minutes=5)).isoformat(), "price_list": "HAPPY"}).status_code == 201
    # The POS feed shows the happy-hour price with the normal price beside it
    v = pos_price(c, "BR-01")
    assert money(v["price"]) == happy and money(v["regular_price"]) == standard and v["price_list"] == "Happy hour"
    # An order added now is charged the happy-hour price; the snapshot keeps it (BR-048)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "HH", "items": [line(m, "BR-01", 2)]}, idem=True).json()
    assert money(o["items"][0]["unit_price_snapshot"]) == happy
    # Outside the list's channels or hours the standard price applies
    assert gm.patch(f"/price-lists/{hh['id']}", {**window(False)}).status_code == 200
    assert money(pos_price(c, "BR-01")["price"]) == standard and pos_price(c, "BR-01")["regular_price"] is None
    o2 = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "Late", "items": [line(m, "BR-01", 1)]}, idem=True).json()
    assert money(o2["items"][0]["unit_price_snapshot"]) == standard
    still = c.get(f"/orders/{o['id']}").json()
    assert money(still["items"][0]["unit_price_snapshot"]) == happy  # earlier order unchanged
    # Back inside the hours: a POS-only list doesn't apply to other channels
    gm.patch(f"/price-lists/{hh['id']}", {**window(True)})
    assert money(pos_price(c, "BR-01")["price"]) == happy
    item = gm.get(f"/menu-items/{beer['id']}").json()
    assert gm.patch(f"/menu-items/{beer['id']}", {"channels": ["POS", "Online"], "version": item["version"]}).status_code == 200
    online = next(i for i in c.get("/menu/pos?channel=Online").json()["items"] if i["code"] == "BR-01")
    assert money(online["variants"][0]["price"]) == standard and online["variants"][0]["price_list"] is None


def test_price_list_rules_and_permissions(api):
    gm, c = api("gm"), api("cashier")
    lists = {x["code"]: x for x in gm.get("/price-lists").json()}
    assert gm.patch(f"/price-lists/{lists['STANDARD']['id']}", {"auto_apply": True}).json()["error"]["code"] == "STANDARD_LIST"
    assert gm.post("/price-lists", {"code": "STANDARD", "name": "Again"}).json()["error"]["code"] == "PRICE_LIST_EXISTS"
    assert gm.post("/price-lists", {"code": "HALF", "name": "Half window", "time_from": "10:00"}).status_code == 422
    assert gm.post("/price-lists", {"code": "BADDAY", "name": "Bad day", "days_of_week": [7]}).status_code == 422
    assert c.post("/price-lists", {"code": "MINE", "name": "Cashier list"}).status_code == 403
    staff = gm.post("/price-lists", {"code": "STAFF", "name": "Staff meal", "auto_apply": False}).json()
    assert staff["auto_apply"] is False and staff["priority"] == 10
    assert any(x["code"] == "STAFF" for x in c.get("/price-lists").json())


def test_menu_schedule_controls_availability(api):
    gm, c = api("gm"), api("cashier")
    m = menu(c)
    salad = m["ST-01"]
    s = gm.post("/menu-schedules", {"name": "Evening only", **window(False), "item_ids": [salad["id"]]})
    assert s.status_code == 201, s.json()
    sched = s.json()
    assert sched["item_ids"] == [salad["id"]]
    assert pos_price(c, "ST-01")["available"] is False
    r = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "S", "items": [line(m, "ST-01", 1)]}, idem=True)
    assert r.json()["error"]["code"] == "ITEM_UNAVAILABLE" and "menu schedule" in r.json()["error"]["message"]
    # Another item is unaffected
    assert pos_price(c, "BR-01")["available"] is True
    # Move the window to now: sellable again
    body = {"name": "Evening only", **window(True), "item_ids": [salad["id"]]}
    assert gm.put(f"/menu-schedules/{sched['id']}", body).status_code == 200
    assert pos_price(c, "ST-01")["available"] is True
    # A date range that has ended hides it again
    past = (datetime.now(TZ) - timedelta(days=3)).date().isoformat()
    gm.put(f"/menu-schedules/{sched['id']}", {**body, "date_from": past, "date_to": past})
    assert pos_price(c, "ST-01")["available"] is False
    # Inactive schedules don't restrict anything
    gm.put(f"/menu-schedules/{sched['id']}", {**body, "date_from": past, "date_to": past, "is_active": False})
    assert pos_price(c, "ST-01")["available"] is True
    assert gm.post("/menu-schedules", {"name": "Bad", "date_from": "2026-12-02", "date_to": "2026-12-01"}).status_code == 422
    assert c.post("/menu-schedules", {"name": "Mine"}).status_code == 403
