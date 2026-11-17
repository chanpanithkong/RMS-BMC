"""Seed reference data (idempotent). Usage:

    python -m scripts.seed                      # reference data only
    python -m scripts.seed --demo               # plus demo menu, tables, ingredients
    python -m scripts.seed --admin-username admin --admin-password '...'

The first administrator is created only when you pass --admin-password (never a hard-coded default).
"""
import argparse
import sys

from app.core.database import session_factory
from app.core.security import password_policy_error
from app.services.seed import create_user, seed_demo, seed_reference


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password")
    parser.add_argument("--admin-roles", default="SYSADMIN,OWNER", help="Comma separated role codes for the first user")
    args = parser.parse_args()

    with session_factory()() as db:
        ref = seed_reference(db)
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
