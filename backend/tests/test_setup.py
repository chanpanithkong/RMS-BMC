"""First setup: restaurant profile (shown on bills and receipts) and the seed command's restaurant and branch options."""
import pytest

from tests.helpers import line, menu


def test_restaurant_profile_edit_and_permissions(api):
    owner, gm, admin = api("owner"), api("gm"), api("admin")
    r = gm.get("/restaurant").json()
    assert r["name_en"] == "RMS Demo Restaurant" and r["base_currency"] == "USD"
    assert gm.patch("/restaurant", {"name_en": "Sok Kitchen"}).status_code == 403  # GM can't change legal details
    out = owner.patch("/restaurant", {"name_en": "Sok Kitchen", "name_km": "ផ្ទះបាយសុខ", "legal_name": "Sok Kitchen Co., Ltd.", "tax_id": "K001-123456789"})
    assert out.status_code == 200, out.json()
    assert out.json()["tax_id"] == "K001-123456789"
    assert admin.patch("/restaurant", {"legal_name": "  "}).json()["error"]["code"] == "VALIDATION_ERROR"
    assert admin.patch("/restaurant", {"tax_id": ""}).json()["tax_id"] is None  # cleared: not printed
    # The new details print on bills
    c = api("cashier")
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "S", "items": [line(m, "DR-03")]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    doc = c.get(f"/bills/{bill['id']}/document").json()
    assert doc["restaurant"]["name_en"] == "Sok Kitchen" and doc["restaurant"]["tax_id"] is None
    logs = owner.get("/audit-logs", params={"action": "restaurant.update"}).json()
    assert (logs["data"] if isinstance(logs, dict) else logs)


def test_seed_identity_options(api, seeded):
    from app.core.database import session_factory
    from app.models import Branch, Restaurant
    from app.services.seed import apply_identity, seed_reference

    with session_factory()() as db:
        ref = seed_reference(db)
        assert ref["branch"].id == seeded["branch_id"]
        # The test branch already has no orders: code and time zone may still change
        msgs = apply_identity(db, ref, {"name_en": "Sok Kitchen", "legal_name": "Sok Kitchen Co., Ltd.", "tax_id": "K001", "name_km": None},
                              {"code": "pp1", "name_en": "BKK1", "timezone": "Asia/Phnom_Penh", "phone": "012 345 678"})
        assert "Branch code set to PP1." in msgs and any("name en" in m for m in msgs)
        db.commit()
        # Running the seed again reuses the renamed branch instead of creating a new "RVS" one
        again = seed_reference(db)
        assert again["branch"].id == seeded["branch_id"] and again["branch"].code == "PP1"
        assert db.query(Branch).count() == 1 and db.query(Restaurant).one().name_en == "Sok Kitchen"
        with pytest.raises(ValueError, match="2-10 letters"):
            apply_identity(db, again, {}, {"code": "X"})
        with pytest.raises(ValueError, match="Unknown time zone"):
            apply_identity(db, again, {}, {"timezone": "Mars/Base"})
        assert apply_identity(db, again, {"name_en": "Sok Kitchen"}, {}) == []  # nothing changed, nothing recorded
        db.rollback()


def test_branch_code_locked_after_first_order(api):
    from app.core.database import session_factory
    from app.services.seed import apply_identity, seed_reference

    c = api("cashier")
    m = menu(c)
    c.post("/orders", {"order_type": "Takeaway", "pickup_name": "First", "items": [line(m, "DR-03")]}, idem=True)
    with session_factory()() as db:
        ref = seed_reference(db)
        with pytest.raises(ValueError, match="already has orders"):
            apply_identity(db, ref, {}, {"code": "PP2"})
        with pytest.raises(ValueError, match="already has orders"):
            apply_identity(db, ref, {}, {"timezone": "Asia/Bangkok"})
        assert apply_identity(db, ref, {}, {"name_en": "Riverside 2"}) == ["Branch name en set."]  # names can still change
        db.rollback()
