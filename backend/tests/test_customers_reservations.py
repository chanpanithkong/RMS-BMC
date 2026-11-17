"""SRS §16.7 (CUST) and §16.8 (RSV)."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tests.helpers import line, menu, tables

PP = ZoneInfo("Asia/Phnom_Penh")


def tomorrow_at(h, m=0):
    d = datetime.now(PP).date() + timedelta(days=1)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=PP)


def test_at_cust_01_duplicate_detection(api):
    c = api("cashier")
    a = c.post("/customers", {"name": "Sokha", "phone": "012 345 678"})
    assert a.status_code == 201 and a.json()["phone"] == "012 345 678"
    r = c.post("/customers", {"name": "Sokha H", "phone": "+855 12 345 678"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "POSSIBLE_DUPLICATE" and r.json()["error"]["existing"][0]["id"] == a.json()["id"]
    assert c.post("/customers", {"name": "X", "phone": "12345"}).json()["error"]["code"] == "PHONE_INVALID"
    found = c.get("/customers?q=012345678").json()["data"]
    assert [x["id"] for x in found] == [a.json()["id"]]


def test_at_cust_02_masking(api):
    cid = api("cashier").post("/customers", {"name": "Dara", "phone": "012 345 678", "email": "dara@example.com"}).json()["id"]
    w = api("waiter").get(f"/customers/{cid}").json()
    assert w["phone"] == "012 *** 678" and w["email"] == "d***@example.com" and w["contact_masked"]
    assert api("gm").get(f"/customers/{cid}").json()["phone"] == "012 345 678"


def test_at_cust_03_anonymise_keeps_orders_and_merge(api):
    c, gm = api("cashier"), api("gm")
    m = menu(c)
    cid = c.post("/customers", {"name": "Bopha", "phone": "097 222 118", "allergy_notes": "Peanuts"}).json()["id"]
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "Bopha", "items": [line(m, "DR-03")]}, idem=True).json()
    att = c.post(f"/customers/attach/{o['id']}", {"customer_id": cid}).json()
    assert att["customer"]["allergy_notes"] == "Peanuts"  # FR-CUST-006 on POS
    other = c.post("/customers", {"name": "Bopha (dup)", "email": "bopha@example.com"}).json()["id"]
    merged = gm.post("/customers/merge", {"keep_id": cid, "merge_id": other}).json()
    assert merged["id"] == cid
    assert gm.get(f"/customers/{other}").json()["merged_into_id"] == cid
    r = gm.post(f"/customers/{cid}/anonymise", {"reason": "Customer request"}).json()
    assert r["anonymised"] and r["phone"] is None and r["name"].startswith("Anonymised")
    order = c.get(f"/orders/{o['id']}").json()
    assert order["customer_name"] is None and order["items"]  # the order stays
    assert gm.get(f"/customers/{cid}/orders").json()["total"] == 1


def test_at_rsv_01_overlap_and_next_slot(api):
    s = api("supv")
    t = tables(s)
    a = s.post("/reservations", {"guest_name": "Mony", "reserved_at": tomorrow_at(19).isoformat(), "party_size": 4, "table_ids": [t["B2"]["id"]]})
    assert a.status_code == 201
    r = s.post("/reservations", {"guest_name": "Rithy", "reserved_at": tomorrow_at(20).isoformat(), "party_size": 2, "table_ids": [t["B2"]["id"]]})
    err = r.json()["error"]
    assert r.status_code == 409 and err["code"] == "TABLE_TIME_CONFLICT"
    assert datetime.fromisoformat(err["next_available"]) == tomorrow_at(20, 45)  # 19:00 + 90 min + 15 min buffer
    assert err["alternative_table_ids"]
    assert s.post("/reservations", {"guest_name": "Rithy", "reserved_at": tomorrow_at(20, 45).isoformat(), "party_size": 2, "table_ids": [t["B2"]["id"]]}).status_code == 201
    free = s.get(f"/reservations/availability?at={tomorrow_at(19, 30).isoformat().replace('+', '%2B')}&party_size=6").json()
    assert all(t["B2"]["id"] not in [str(x) for x in f["table_ids"]] for f in free)


def test_at_rsv_02_no_show_and_seat(api, engine):
    from sqlalchemy import text

    s = api("supv")
    t = tables(s)
    cid = api("cashier").post("/customers", {"name": "Late Guest", "phone": "011 730 225"}).json()["id"]
    r = s.post("/reservations", {"guest_name": "Late Guest", "customer_id": cid, "reserved_at": tomorrow_at(18, 30).isoformat(), "party_size": 2,
                                 "table_ids": [t["A2"]["id"]]}).json()
    assert s.post(f"/reservations/{r['id']}/no-show").json()["error"]["code"] == "GRACE_NOT_OVER"
    with engine.begin() as conn:  # time travel: move the booking into the past
        conn.execute(text("update table_reservations set reserved_at = now() - interval '20 minutes' where id = :i"), {"i": r["id"]})
    out = s.post("/reservations/process-holds").json()
    assert out["no_shows"] == 1
    assert s.get(f"/customers/{cid}").json()["no_show_count"] == 1
    # seating a confirmed reservation opens an order on its table
    r2 = s.post("/reservations", {"guest_name": "Sophea", "reserved_at": tomorrow_at(12).isoformat(), "party_size": 3, "table_ids": [t["A1"]["id"]]}).json()
    seated = s.post(f"/reservations/{r2['id']}/seat").json()
    assert seated["status"] == "Seated" and seated["order_id"]
    assert tables(s)["A1"]["service_state"] == "Seated"


def test_walkin_warning_on_reserved_table(api, engine):
    from sqlalchemy import text

    s = api("supv")
    t = tables(s)
    r = s.post("/reservations", {"guest_name": "Soon", "reserved_at": tomorrow_at(12).isoformat(), "party_size": 2, "table_ids": [t["A3"]["id"]]}).json()
    with engine.begin() as conn:
        conn.execute(text("update table_reservations set reserved_at = now() + interval '30 minutes' where id = :i"), {"i": r["id"]})
    assert s.post(f"/tables/{t['A3']['id']}/seat", {"guest_count": 2}).json()["error"]["code"] == "TABLE_RESERVED_SOON"
    assert s.post(f"/tables/{t['A3']['id']}/seat", {"guest_count": 2, "override_reservation": True}).status_code == 200


def test_at_rsv_03_waiting_list(api):
    w = api("waiter")
    ids = [w.post("/waitlist", {"party_name": n, "party_size": 2}).json()["id"] for n in ("Kimly", "Sarath", "Thida")]
    listed = w.get("/waitlist").json()
    assert [x["position"] for x in listed] == [1, 2, 3] and all(x["quoted_minutes"] >= 0 for x in listed)
    r = w.post(f"/waitlist/{ids[0]}/notify").json()
    assert r["status"] == "Notified" and r["notified_at"]
    assert w.post(f"/waitlist/{ids[0]}/notify").status_code == 409
    assert api("cook").get("/waitlist").status_code == 403
