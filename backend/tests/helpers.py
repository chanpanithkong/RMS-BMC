from decimal import Decimal


def menu(api_user) -> dict:
    """code -> {variants: {name: id}, mods: {name: id}, item_id}"""
    out = {}
    for item in api_user.get("/menu/pos").json()["items"]:
        mods = {m["name_en"]: m["id"] for g in item["modifier_groups"] for m in g["modifiers"]}
        out[item["code"]] = {"id": item["id"], "variants": {v["name_en"]: v["id"] for v in item["variants"]}, "mods": mods}
    return out


def line(m: dict, code: str, qty: int = 1, mods: tuple[str, ...] = (), variant: str = "Regular", **extra) -> dict:
    return {"variant_id": m[code]["variants"][variant], "quantity": str(qty), "modifiers": [{"modifier_id": m[code]["mods"][x]} for x in mods], **extra}


def tables(api_user) -> dict:
    return {t["table_code"]: t for t in api_user.get("/tables").json()}


def money(v) -> Decimal:
    return Decimal(str(v))
