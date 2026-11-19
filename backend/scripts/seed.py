"""Seed reference data (idempotent). Usage:

    python -m scripts.seed                      # reference data only
    python -m scripts.seed --demo               # plus demo menu, tables, ingredients
    python -m scripts.seed --admin-username admin --admin-password '...'
    python -m scripts.seed --restaurant-name "Sok Kitchen" --legal-name "Sok Kitchen Co., Ltd." --tax-id "K001-123456789"         --branch-code PP1 --branch-name "Phnom Penh BKK1"      # first setup: your restaurant and first branch

Restaurant and branch options change only what you pass, and can be run again later. The branch code and time zone
can only change before the branch has any orders.

The first administrator is created only when you pass --admin-password (never a hard-coded default).
"""
import argparse
import sys

from app.core.database import session_factory
from app.core.security import password_policy_error
from app.services.seed import apply_identity, create_user, seed_demo, seed_reference


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password")
    parser.add_argument("--admin-roles", default="SYSADMIN,OWNER", help="Comma separated role codes for the first user")
    g = parser.add_argument_group("restaurant and first branch (first setup)")
    g.add_argument("--restaurant-name", help="Trading name in English (printed on bills and receipts)")
    g.add_argument("--restaurant-name-km", help="Trading name in Khmer")
    g.add_argument("--legal-name", help="Registered company name")
    g.add_argument("--tax-id", help="Tax identification number, printed on bills and receipts")
    g.add_argument("--branch-code", help="2-10 letters or digits, used in document numbers; only before the first order")
    g.add_argument("--branch-name", help="First branch name in English")
    g.add_argument("--branch-name-km", help="First branch name in Khmer")
    g.add_argument("--branch-address")
    g.add_argument("--branch-phone")
    g.add_argument("--timezone", help="IANA time zone, e.g. Asia/Phnom_Penh; only before the first order")
    args = parser.parse_args()

    with session_factory()() as db:
        ref = seed_reference(db)
        try:
            for line in apply_identity(db, ref,
                                       {"name_en": args.restaurant_name, "name_km": args.restaurant_name_km, "legal_name": args.legal_name, "tax_id": args.tax_id},
                                       {"code": args.branch_code, "name_en": args.branch_name, "name_km": args.branch_name_km, "address": args.branch_address,
                                        "phone": args.branch_phone, "timezone": args.timezone}):
                print(line)
        except ValueError as e:
            db.rollback()
            print(f"Setup rejected: {e}", file=sys.stderr)
            return 1
        if args.demo:
            seed_demo(db, ref)
        if args.admin_password:
            err = password_policy_error(args.admin_password, args.admin_username)
            if err:
                print(f"Admin password rejected: {err}", file=sys.stderr)
                return 1
            create_user(db, args.admin_username, "Administrator", args.admin_password, args.admin_roles.split(","), ref["branch"])
            print(f"Administrator '{args.admin_username}' is ready.")
        db.commit()
    print("Seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
