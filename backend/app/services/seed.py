"""Idempotent reference and demo data (SRS §10.11: seed scripts versioned with code).

Every value marked illustrative in the SRS is seeded as unverified and must be confirmed (V-01, V-04, D-03…).
"""
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.core.security import hash_secret
from app.models import (Branch, BranchMenuItem, DiningArea, ExchangeRate, Ingredient, InventoryLocation, ItemModifierGroup, KitchenStation, MenuCategory, MenuItem,
                        MenuItemVariant, MenuPrice, Modifier, ModifierGroup, PaymentMethod, Permission, PriceList, ReasonCode, Restaurant, RestaurantTable, Role, RoleLimit,
                        RolePermission, TaxProfile, TaxProfileRate, UnitOfMeasure, User, UserBranch, UserRole)
from app.permissions.catalog import PERMISSIONS, ROLE_GRANTS, ROLE_LIMITS, ROLE_NAMES

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _get_or_create(db: Session, model, lookup: dict, **values):
    obj = db.scalar(select(model).filter_by(**lookup))
    if obj is None:
        obj = model(**lookup, **values)
        db.add(obj)
        db.flush()
    return obj


def seed_reference(db: Session) -> dict:
    """Permissions, roles, limits, units, reasons, payment methods, tax profile, price list, rate, restaurant and branch."""
    for code, (module, desc) in PERMISSIONS.items():
        perm = db.get(Permission, code)
        if perm is None:
            db.add(Permission(code=code, module=module, description=desc))
    db.flush()
    roles = {}
    for code, grants in ROLE_GRANTS.items():
        role = _get_or_create(db, Role, {"code": code}, name=ROLE_NAMES[code], is_system=True)
        roles[code] = role
        have = set(db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)))
        for p in set(grants) - have:
            db.add(RolePermission(role_id=role.id, permission_code=p))
        for key, value in ROLE_LIMITS.get(code, {}).items():
            if db.get(RoleLimit, (role.id, key)) is None:
                db.add(RoleLimit(role_id=role.id, limit_key=key, value=value))
    db.flush()

    for code, name, dim, factor in [("g", "Gram", "Mass", "1"), ("kg", "Kilogram", "Mass", "1000"), ("ml", "Millilitre", "Volume", "1"), ("L", "Litre", "Volume", "1000"), ("piece", "Piece", "Count", "1")]:
        _get_or_create(db, UnitOfMeasure, {"code": code}, name=name, dimension=dim, factor_to_base=Decimal(factor))

    reasons = {
        "Void": ["Customer changed mind", "Wrong item entered", "Kitchen error", "Item unavailable", "Quality issue"],
        "Cancel": ["Customer left", "Duplicate order", "Entered in error"],
        "Discount": ["Regular customer", "Service recovery", "Staff meal", "Complimentary", "Manager decision"],
        "Refund": ["Quality issue", "Wrong order", "Overcharged", "Customer complaint"],
        "Adjustment": ["Count correction", "Breakage", "Entered in error"],
        "Wastage": ["Spoiled", "Burnt", "Dropped", "Expired", "Prepared but cancelled"],
        "CashMovement": ["Supplier paid in cash", "Float top-up", "Cash drop to safe"],
        "Variance": ["Counting error", "Unexplained", "Rounding"],
    }
    for kind, names in reasons.items():
        for n in names:
            _get_or_create(db, ReasonCode, {"kind": kind, "code": n.upper().replace(" ", "_")}, name_en=n)

    for code, name, kind, cur, ref, change in [("CASH_USD", "Cash USD", "Cash", ["USD"], False, True), ("CASH_KHR", "Cash KHR", "Cash", ["KHR"], False, True),
                                               ("KHQR", "KHQR", "QR", ["USD", "KHR"], True, False), ("BANK_TRANSFER", "Bank Transfer", "Bank", ["USD"], True, False),
                                               ("CARD", "Card (terminal)", "Card", ["USD"], True, False)]:
        _get_or_create(db, PaymentMethod, {"code": code}, name=name, kind=kind, currencies=cur, reference_required=ref, change_allowed=change)

    profile = _get_or_create(db, TaxProfile, {"code": "STANDARD"}, name="Standard food and beverage")
    if not db.scalar(select(TaxProfileRate).where(TaxProfileRate.profile_id == profile.id)):
        db.add_all([
            TaxProfileRate(profile_id=profile.id, charge_kind="ServiceCharge", name="Service charge (illustrative)", rate=Decimal("0.05"), base_rule="DiscountedSubtotal",
                           inclusive=False, applies_to_order_types=["DineIn"], valid_during=Range(EPOCH, None), verified=False),
            TaxProfileRate(profile_id=profile.id, charge_kind="Tax", name="Tax (illustrative)", rate=Decimal("0.10"), base_rule="SubtotalPlusServiceCharge",
                           inclusive=False, applies_to_order_types=["DineIn", "Takeaway", "Delivery"], valid_during=Range(EPOCH, None), verified=False),
        ])
    _get_or_create(db, PriceList, {"code": "STANDARD"}, name="Standard")
    _get_or_create(db, ExchangeRate, {"base_currency": "USD", "quote_currency": "KHR", "effective_from": EPOCH}, rate=Decimal("4100"), source="Illustrative seed (verify V-04)")

    from app.models import Department, ExpenseCategory, Position

    for name in ("Management", "Front of house", "Kitchen", "Bar", "Stores", "Finance", "Delivery"):
        _get_or_create(db, Department, {"name": name})
    for name in ("General Manager", "Branch Manager", "Supervisor", "Cashier", "Waiter", "Kitchen Manager", "Cook", "Bartender", "Inventory Officer", "Purchasing Officer", "Accountant", "Rider"):
        _get_or_create(db, Position, {"name": name})
    for name, required in [("Rent", True), ("Electricity", True), ("Water", False), ("Internet", False), ("Salaries", False), ("Cleaning supplies", False),
                           ("Equipment repairs", True), ("Delivery costs", False), ("Platform commissions", False)]:
        _get_or_create(db, ExpenseCategory, {"name_en": name}, attachment_required=required)
    restaurant = db.scalar(select(Restaurant)) or Restaurant(legal_name="RMS Demo Restaurant Co., Ltd.", name_en="RMS Demo Restaurant", name_km="ភោជនីយដ្ឋានសាកល្បង")
    db.add(restaurant)
    db.flush()
    branch = _get_or_create(db, Branch, {"restaurant_id": restaurant.id, "code": "RVS"}, name_en="Riverside", name_km="មាត់ទន្លេ", timezone="Asia/Phnom_Penh", day_end_time=time(4, 0))
    for i, (code, name) in enumerate([("HOT", "Hot"), ("COLD", "Cold"), ("BEV", "Beverage"), ("DESSERT", "Dessert"), ("BAR", "Bar")]):
        _get_or_create(db, KitchenStation, {"branch_id": branch.id, "code": code}, name=name, is_default=i == 0, warn_minutes=10, critical_minutes=20)
    for name in ("Dry store", "Chiller", "Freezer", "Bar"):
        _get_or_create(db, InventoryLocation, {"branch_id": branch.id, "name": name})
    db.flush()
    return {"restaurant": restaurant, "branch": branch, "roles": roles, "tax_profile": profile}


def create_user(db: Session, username: str, full_name: str, password: str, role_codes: list[str], branch: Branch, pin: str | None = None, email: str | None = None) -> User:
    user = db.scalar(select(User).where(User.username.ilike(username)))
    if user is None:
        user = User(username=username, full_name=full_name, email=email, password_hash=hash_secret(password), pin_hash=hash_secret(pin) if pin else None)
        db.add(user)
        db.flush()
        for code in role_codes:
            db.add(UserRole(user_id=user.id, role_id=db.scalar(select(Role.id).where(Role.code == code))))
        db.add(UserBranch(user_id=user.id, branch_id=branch.id, is_default=True))
        db.flush()
        db.refresh(user)
    return user


DEMO_MENU = [
    # category, code, name_en, name_km, station, type, [(variant, price)], modifier groups
    ("Rice & Noodles", "បាយ និងមី", [
        ("RN-01", "Fried Rice", "បាយឆា", "HOT", "Food", [("Regular", "5.00")], ["Spice level", "Extra toppings"]),
        ("RN-02", "Beef Stir-fried Noodles", "មីឆាសាច់គោ", "HOT", "Food", [("Regular", "5.50")], ["Spice level"]),
        ("RN-03", "Kuy Teav Pork Noodle", "គុយទាវសាច់ជ្រូក", "HOT", "Food", [("Regular", "4.50")], []),
    ]),
    ("Khmer Mains", "ម្ហូបខ្មែរ", [
        ("MN-01", "Fish Amok", "អាម៉ុកត្រី", "HOT", "Food", [("Regular", "8.50")], ["Spice level"]),
        ("MN-02", "Beef Lok Lak", "ឡុកឡាក់សាច់គោ", "HOT", "Food", [("Regular", "9.50"), ("Large", "12.50")], []),
    ]),
    ("Salads & Starters", "សាឡាត់", [("ST-01", "Green Mango Salad", "ញាំស្វាយ", "COLD", "Food", [("Regular", "5.00")], ["Spice level"])]),
    ("Desserts", "បង្អែម", [("DS-01", "Mango Sticky Rice", "បាយដំណើបស្វាយ", "DESSERT", "Food", [("Regular", "4.00")], [])]),
    ("Coffee & Tea", "កាហ្វេ និងតែ", [("CF-01", "Iced Coffee", "កាហ្វេទឹកកក", "BEV", "Beverage", [("Regular", "2.00"), ("Large", "2.75")], ["Sugar level", "Coffee add-ons"])]),
    ("Soft Drinks", "ភេសជ្ជៈ", [("DR-03", "Bottled Water", "ទឹកសុទ្ធ", None, "Beverage", [("Regular", "1.00")], [])]),
    ("Beer & Cocktails", "ស្រា", [("BR-01", "Draft Beer", "ស្រាបៀរស្រស់", "BAR", "Beverage", [("Regular", "2.50")], [])]),
]
DEMO_GROUPS = {
    "Spice level": ("កម្រិតហឹរ", 1, 1, [("No chilli", "0"), ("Mild", "0"), ("Medium", "0"), ("Hot", "0")]),
    "Sugar level": ("កម្រិតស្ករ", 1, 1, [("0%", "0"), ("50%", "0"), ("100%", "0")]),
    "Extra toppings": ("បន្ថែម", 0, 3, [("Fried egg", "0.75"), ("Extra chicken", "1.50")]),
    "Coffee add-ons": ("បន្ថែមកាហ្វេ", 0, 2, [("Extra shot", "0.50"), ("Caramel syrup", "0.50")]),
}


def seed_demo(db: Session, ref: dict) -> None:
    """Demo menu, tables and ingredients that mirror the frontend's demo screens. Prices are illustrative."""
    restaurant, branch, profile = ref["restaurant"], ref["branch"], ref["tax_profile"]
    price_list = db.scalar(select(PriceList).where(PriceList.code == "STANDARD"))
    groups = {}
    for name, (km, mn, mx, mods) in DEMO_GROUPS.items():
        g = _get_or_create(db, ModifierGroup, {"name_en": name}, name_km=km, min_select=mn, max_select=mx)
        if not g.modifiers:
            for i, (mname, delta) in enumerate(mods):
                db.add(Modifier(group_id=g.id, name_en=mname, price_delta=Decimal(delta), sort_order=i))
        groups[name] = g
    db.flush()
    for order, (cat_en, cat_km, items) in enumerate(DEMO_MENU):
        cat = _get_or_create(db, MenuCategory, {"restaurant_id": restaurant.id, "name_en": cat_en}, name_km=cat_km, sort_order=order)
        for code, en, km, station, itype, variants, gnames in items:
            if db.scalar(select(MenuItem).where(MenuItem.code == code)):
                continue
            item = MenuItem(restaurant_id=restaurant.id, category_id=cat.id, code=code, name_en=en, name_km=km, item_type=itype, station_code=station,
                            tax_profile_id=profile.id, channels=["POS", "Online"])
            db.add(item)
            db.flush()
            for i, (vname, price) in enumerate(variants):
                v = MenuItemVariant(menu_item_id=item.id, name_en=vname, sort_order=i)
                db.add(v)
                db.flush()
                db.add(MenuPrice(variant_id=v.id, price_list_id=price_list.id, price=Decimal(price), valid_during=Range(EPOCH, None)))
            for i, gname in enumerate(gnames):
                db.add(ItemModifierGroup(menu_item_id=item.id, group_id=groups[gname].id, sort_order=i))
            db.add(BranchMenuItem(branch_id=branch.id, menu_item_id=item.id))
    for area_name, tables in [("Indoor", [("A1", 4), ("A2", 2), ("A3", 2), ("A4", 4), ("B1", 4), ("B2", 8)]), ("Terrace", [("T1", 4), ("T2", 4)])]:
        area = _get_or_create(db, DiningArea, {"branch_id": branch.id, "name": area_name})
        for i, (code, cap) in enumerate(tables):
            if not db.scalar(select(RestaurantTable).where(RestaurantTable.branch_id == branch.id, RestaurantTable.table_code == code)):
                db.add(RestaurantTable(branch_id=branch.id, dining_area_id=area.id, table_code=code, capacity=cap, layout_x=Decimal(8 + (i % 4) * 22), layout_y=Decimal(10 + (i // 4) * 32)))
    kg = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "kg"))
    litre = db.scalar(select(UnitOfMeasure).where(UnitOfMeasure.code == "L"))
    for code, en, km, cat, uom, level, qty in [("ING-001", "Jasmine rice", "អង្ករម្លិះ", "Dry goods", kg, "15", "50"), ("ING-002", "Beef sirloin", "សាច់គោ", "Meat", kg, "8", "20"),
                                               ("ING-004", "Coconut cream", "ខ្ទិះដូង", "Dairy & cream", litre, "6", "24"), ("ING-011", "Pork shoulder", "សាច់ជ្រូក", "Meat", kg, "8", "20")]:
        _get_or_create(db, Ingredient, {"code": code}, name_en=en, name_km=km, category=cat, stock_uom_id=uom.id, reorder_level=Decimal(level), reorder_qty=Decimal(qty))
    db.flush()
