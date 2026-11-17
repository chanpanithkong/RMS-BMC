"""Permission catalogue (resource.action) and default role grants from SRS §4.3.

Grants and limits are the SRS *proposed defaults*; final values await decision D-05 (and D-04 for discounts).
"""
from decimal import Decimal

PERMISSIONS: dict[str, tuple[str, str]] = {
    "dashboard.view": ("DASH", "View dashboard widgets permitted for the role"),
    "report.view": ("RPT", "View operational reports"),
    "report.financial.view": ("RPT", "View sales, payment, tax and expense figures"),
    "report.export": ("RPT", "Export reports (audited)"),
    "report.cross_branch": ("RPT", "View consolidated multi-branch data"),
    "users.view": ("USER", "View user accounts"),
    "users.manage": ("USER", "Create, edit, activate and deactivate users"),
    "roles.manage": ("USER", "Edit roles, permissions and approval limits"),
    "branches.manage": ("BRN", "Create and edit branches and devices"),
    "settings.view": ("CFG", "View configuration"),
    "settings.manage": ("CFG", "Change operational configuration"),
    "settings.approve": ("CFG", "Approve financial configuration (taxes, service charges)"),
    "exchange_rates.manage": ("CFG", "Enter exchange rates"),
    "menu.view": ("MENU", "View menu and prices"),
    "menu.manage": ("MENU", "Create and edit categories, items, variants and modifiers"),
    "menu.availability": ("MENU", "Mark items unavailable (86)"),
    "prices.manage": ("MENU", "Create effective-dated prices"),
    "tables.view": ("TBL", "View floor plan"),
    "tables.manage": ("TBL", "Edit areas and tables"),
    "tables.operate": ("TBL", "Seat, transfer and change table state"),
    "orders.view": ("ORD", "View orders"),
    "orders.view_all": ("ORD", "View all orders, not only own"),
    "orders.create": ("ORD", "Create orders and add items"),
    "orders.edit": ("ORD", "Edit pending items, hold, send"),
    "orders.cancel": ("ORD", "Cancel items and orders"),
    "orders.transfer": ("ORD", "Transfer orders between tables"),
    "kitchen.view": ("KDS", "View kitchen tickets"),
    "kitchen.operate": ("KDS", "Start, bump, recall tickets"),
    "kitchen.manage": ("KDS", "Prioritise tickets, manage stations"),
    "payments.view": ("BILL", "View bills and payments"),
    "payments.create": ("BILL", "Take payments and print bills"),
    "payments.void": ("BILL", "Void an unfinalised payment"),
    "refunds.request": ("BILL", "Request a refund"),
    "refunds.approve": ("BILL", "Approve refunds within limit"),
    "discounts.apply": ("PROMO", "Apply discounts within own limit"),
    "discounts.approve": ("PROMO", "Approve discounts above another user's limit"),
    "voids.approve": ("ORD", "Approve voids of prepared items"),
    "cash.operate": ("STAFF", "Open and close own cashier session"),
    "cash.view": ("STAFF", "View all cashier sessions"),
    "cash.approve": ("STAFF", "Approve variances, force-close sessions"),
    "inventory.view": ("INV", "View stock and movements"),
    "inventory.manage": ("INV", "Ingredients, receipts, issues, adjustments"),
    "inventory.wastage": ("INV", "Record wastage"),
    "inventory.approve": ("INV", "Approve adjustments above threshold"),
    "audit.view": ("AUD", "Search the audit trail"),
    "audit.export": ("AUD", "Export the audit trail"),
    "notifications.view": ("NOTIF", "Receive in-app notifications"),
    # Phase 2
    "customers.view": ("CUST", "Search and view customers"),
    "customers.manage": ("CUST", "Create, edit, merge and anonymise customers"),
    "customers.contact.view": ("CUST", "See unmasked phone and email"),
    "reservations.view": ("RSV", "View reservations and the waiting list"),
    "reservations.manage": ("RSV", "Create, change, seat and cancel reservations"),
    "recipes.view": ("RCP", "View recipes and food cost"),
    "recipes.manage": ("RCP", "Create recipe versions and publish them"),
    "suppliers.view": ("PUR", "View suppliers"),
    "suppliers.manage": ("PUR", "Create and edit suppliers"),
    "purchases.view": ("PUR", "View requests, POs, receipts, invoices"),
    "purchases.request": ("PUR", "Create purchase requests"),
    "purchases.create": ("PUR", "Create and submit purchase orders, invoices, returns"),
    "purchases.approve": ("PUR", "Approve purchase orders within limit"),
    "goods_receipts.post": ("PUR", "Record and post goods receipts"),
    "supplier_payments.create": ("PUR", "Record supplier invoices and payments"),
    "expenses.view": ("EXP", "View expenses"),
    "expenses.create": ("EXP", "Record and submit expenses"),
    "expenses.approve": ("EXP", "Approve or reject expenses within limit"),
    "expenses.pay": ("EXP", "Record expense payments"),
    "employees.view": ("STAFF", "View employees and schedules"),
    "employees.manage": ("STAFF", "Manage employees, departments, schedules"),
    "promotions.view": ("PROMO", "View promotions"),
    "promotions.manage": ("PROMO", "Create and edit promotions and codes"),
}

_VIEW_ALL = [p for p in PERMISSIONS if p.endswith(".view") or p in ("report.financial.view", "report.export", "audit.export", "orders.view_all")]

ROLE_GRANTS: dict[str, list[str]] = {
    "SYSADMIN": ["dashboard.view", "report.view", "users.view", "users.manage", "roles.manage", "branches.manage", "settings.view", "settings.manage", "menu.view", "tables.view", "kitchen.view", "audit.view", "audit.export"],
    "OWNER": _VIEW_ALL + ["users.view", "branches.manage", "settings.manage", "settings.approve", "prices.manage", "discounts.approve", "refunds.approve", "voids.approve", "cash.approve", "inventory.approve", "report.cross_branch"],
    "GM": ["dashboard.view", "report.view", "report.financial.view", "report.export", "users.view", "settings.view", "settings.manage", "exchange_rates.manage",
           "menu.view", "menu.manage", "menu.availability", "prices.manage", "tables.view", "tables.manage", "tables.operate",
           "orders.view", "orders.view_all", "orders.create", "orders.edit", "orders.cancel", "orders.transfer", "kitchen.view", "kitchen.manage",
           "payments.view", "payments.create", "payments.void", "refunds.request", "refunds.approve", "discounts.apply", "discounts.approve", "voids.approve",
           "cash.view", "cash.approve", "inventory.view", "inventory.approve", "audit.view"],
    "BRMGR": ["dashboard.view", "report.view", "report.financial.view", "report.export", "users.view", "settings.view", "settings.manage",
              "menu.view", "menu.availability", "tables.view", "tables.manage", "tables.operate",
              "orders.view", "orders.view_all", "orders.create", "orders.edit", "orders.cancel", "orders.transfer", "kitchen.view", "kitchen.manage",
              "payments.view", "payments.create", "payments.void", "refunds.request", "refunds.approve", "discounts.apply", "discounts.approve", "voids.approve",
              "cash.view", "cash.approve", "inventory.view", "inventory.approve", "audit.view"],
    "SUPV": ["dashboard.view", "report.view", "menu.view", "tables.view", "tables.operate", "orders.view", "orders.view_all", "orders.create", "orders.edit", "orders.cancel", "orders.transfer",
             "kitchen.view", "kitchen.manage", "payments.view", "payments.create", "refunds.request", "discounts.apply", "discounts.approve", "voids.approve", "cash.view", "inventory.view"],
    "CASHIER": ["dashboard.view", "menu.view", "tables.view", "tables.operate", "orders.view", "orders.view_all", "orders.create", "orders.edit", "kitchen.view",
                "payments.view", "payments.create", "refunds.request", "discounts.apply", "cash.operate"],
    "WAITER": ["menu.view", "tables.view", "tables.operate", "orders.view", "orders.create", "orders.edit", "kitchen.view", "discounts.apply"],
    "KMGR": ["dashboard.view", "report.view", "menu.view", "menu.availability", "orders.view", "orders.view_all", "kitchen.view", "kitchen.operate", "kitchen.manage", "voids.approve", "inventory.view", "inventory.wastage"],
    "COOK": ["menu.view", "kitchen.view", "kitchen.operate", "inventory.wastage"],
    "BAR": ["menu.view", "orders.view", "orders.create", "orders.edit", "kitchen.view", "kitchen.operate", "payments.view", "payments.create", "refunds.request", "discounts.apply", "cash.operate", "inventory.wastage"],
    "INVOFF": ["dashboard.view", "report.view", "inventory.view", "inventory.manage", "inventory.wastage"],
    "PUROFF": ["dashboard.view", "report.view", "inventory.view"],
    "ACCT": ["dashboard.view", "report.view", "report.financial.view", "report.export", "settings.view", "exchange_rates.manage", "orders.view", "orders.view_all", "payments.view", "refunds.approve",
             "cash.view", "cash.approve", "inventory.view", "audit.view", "menu.view"],
    "AUDITOR": _VIEW_ALL,
}
PHASE2_GRANTS: dict[str, list[str]] = {
    "SYSADMIN": ["employees.view"],
    "OWNER": ["customers.manage", "customers.contact.view", "recipes.view", "suppliers.view", "purchases.view", "purchases.approve", "expenses.view", "expenses.approve",
              "employees.view", "promotions.view", "reservations.view"],
    "GM": ["customers.view", "customers.manage", "customers.contact.view", "reservations.view", "reservations.manage", "recipes.view", "recipes.manage", "suppliers.view",
           "purchases.view", "purchases.approve", "expenses.view", "expenses.create", "expenses.approve", "employees.view", "employees.manage", "promotions.view", "promotions.manage"],
    "BRMGR": ["customers.view", "customers.manage", "customers.contact.view", "reservations.view", "reservations.manage", "recipes.view", "suppliers.view", "purchases.view",
              "purchases.approve", "expenses.view", "expenses.create", "expenses.approve", "employees.view", "employees.manage", "promotions.view"],
    "SUPV": ["customers.view", "customers.manage", "customers.contact.view", "reservations.view", "reservations.manage", "expenses.view", "expenses.create", "employees.view", "promotions.view"],
    "CASHIER": ["customers.view", "customers.manage", "customers.contact.view", "reservations.view", "reservations.manage", "expenses.pay", "promotions.view"],
    "WAITER": ["customers.view", "reservations.view", "reservations.manage"],
    "KMGR": ["recipes.view", "recipes.manage", "purchases.view", "purchases.request", "employees.view"],
    "COOK": ["recipes.view"],
    "BAR": ["recipes.view", "promotions.view"],
    "INVOFF": ["recipes.view", "suppliers.view", "purchases.view", "purchases.request", "goods_receipts.post"],
    "PUROFF": ["suppliers.view", "suppliers.manage", "purchases.view", "purchases.request", "purchases.create", "expenses.view", "expenses.create"],
    "ACCT": ["customers.view", "recipes.view", "suppliers.view", "purchases.view", "supplier_payments.create", "expenses.view", "expenses.create", "expenses.pay", "promotions.view"],
}
for role, extra in PHASE2_GRANTS.items():
    ROLE_GRANTS[role].extend(extra)
ROLE_GRANTS["AUDITOR"].extend(p for p in ("customers.view", "reservations.view", "recipes.view", "suppliers.view", "purchases.view", "expenses.view", "employees.view", "promotions.view")
                              if p not in ROLE_GRANTS["AUDITOR"])
for grants in ROLE_GRANTS.values():
    grants.append("notifications.view")

ROLE_NAMES = {
    "SYSADMIN": "System Administrator", "OWNER": "Restaurant Owner", "GM": "General Manager", "BRMGR": "Branch Manager", "SUPV": "Restaurant Supervisor",
    "CASHIER": "Cashier", "WAITER": "Waiter", "KMGR": "Kitchen Manager", "COOK": "Chef or Cook", "BAR": "Bartender", "INVOFF": "Inventory Officer",
    "PUROFF": "Purchasing Officer", "ACCT": "Accountant", "AUDITOR": "Auditor",
}

_INF = Decimal("999999")
# Illustrative approval limits (D-04, D-05). discount_pct is a percentage; the rest are USD amounts.
ROLE_LIMITS: dict[str, dict[str, Decimal]] = {
    "CASHIER": {"discount_pct": Decimal("10"), "discount_amount": Decimal("5")},
    "BAR": {"discount_pct": Decimal("10"), "discount_amount": Decimal("5")},
    "WAITER": {"discount_pct": Decimal("0"), "discount_amount": Decimal("0")},
    "SUPV": {"discount_pct": Decimal("20"), "discount_amount": Decimal("20"), "void_amount": Decimal("20")},
    "KMGR": {"void_amount": Decimal("50"), "adjustment_value": Decimal("25")},
    "INVOFF": {"adjustment_value": Decimal("25")},
    "BRMGR": {"discount_pct": Decimal("30"), "discount_amount": Decimal("50"), "void_amount": Decimal("100"), "refund_amount": Decimal("100"), "adjustment_value": Decimal("300"), "cash_variance": Decimal("50")},
    "GM": {"discount_pct": Decimal("50"), "discount_amount": Decimal("200"), "void_amount": Decimal("500"), "refund_amount": Decimal("500"), "adjustment_value": Decimal("2000"), "cash_variance": Decimal("500")},
    "ACCT": {"refund_amount": Decimal("200"), "cash_variance": Decimal("500")},
    "OWNER": {"discount_pct": Decimal("100"), "discount_amount": _INF, "void_amount": _INF, "refund_amount": _INF, "adjustment_value": _INF, "cash_variance": _INF},
}
# Phase 2 illustrative limits (AT-PUR-01: GM needed above 500; AT-EXP-01: supervisor expense limit 50).
for _role, _vals in {"BRMGR": {"po_amount": "500", "expense_amount": "300"}, "GM": {"po_amount": "5000", "expense_amount": "2000"}, "OWNER": {"po_amount": "999999", "expense_amount": "999999"},
                     "SUPV": {"expense_amount": "50"}, "PUROFF": {"expense_amount": "50"}, "ACCT": {"expense_amount": "100"}}.items():
    ROLE_LIMITS.setdefault(_role, {}).update({k: Decimal(v) for k, v in _vals.items()})

# Which permission an approver needs for each approval action.
APPROVAL_ACTIONS: dict[str, tuple[str, str]] = {
    "discount": ("discounts.approve", "discount_pct"),
    "void": ("voids.approve", "void_amount"),
    "refund": ("refunds.approve", "refund_amount"),
    "stock_adjustment": ("inventory.approve", "adjustment_value"),
    "cash_variance": ("cash.approve", "cash_variance"),
    "payment_void": ("payments.void", "void_amount"),
}
