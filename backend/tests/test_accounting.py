"""Accounting export: balanced daily journals and the Xero manual-journal CSV."""
import csv
import io
from datetime import date
from decimal import Decimal

from tests.helpers import menu, money
from tests.test_config_reports import paid_order
from tests.test_recipes_stock import opening, refs


def lines_by_code(journal):
    out = {}
    for ln in journal["lines"]:
        out[ln["account_code"]] = out.get(ln["account_code"], Decimal(0)) + money(ln["amount"])
    return out


def test_daily_journal_balances_and_maps(api):
    c, gm, acct, owner, inv, s = api("cashier"), api("gm"), api("acct"), api("owner"), api("invoff"), api("supv")
    m = menu(c)
    o, bill = paid_order(c, m)  # 9.50 food + 0.95 tax, paid by KHQR
    pay = c.get(f"/orders/{o['id']}/bills").json()[0]
    units, locs, items = refs(inv)
    opening(inv, locs["Dry store"], items["ING-001"], "10", units["kg"], "2.00")  # 20.00 of opening stock
    cat = next(x for x in s.get("/expense-categories").json() if x["name_en"] == "Water")["id"]
    e = s.post("/expenses", {"category_id": cat, "expense_date": date.today().isoformat(), "description": "Water", "amount": "20", "payee": "Shop"}).json()
    s.post(f"/expenses/{e['id']}/submit")
    assert acct.post(f"/expenses/{e['id']}/pay", {"method": "BANK_TRANSFER", "reference": "BT-9"}).status_code == 200
    assert c.get("/accounting/journals").status_code == 403
    j = acct.get("/accounting/journals").json()["journals"]
    assert len(j) == 1
    day = j[0]
    assert sum(money(x["amount"]) for x in day["lines"]) == 0 and money(day["debits"]) == money(day["credits"]) and not day["warnings"]
    by = lines_by_code(day)
    assert by["4000"] == Decimal("-9.50") and by["2200"] == Decimal("-0.95") and by["1020"] == Decimal("10.45")  # sales, tax, KHQR clearing
    assert by["1150"] == 0  # everything billed was paid the same day: "bills finalised" and "payments applied" cancel out
    assert by["1300"] == Decimal("20.00") and by["3900"] == Decimal("-20.00")  # opening stock
    assert by["6000"] == Decimal("20") and by["2170"] == 0  # expense incurred and paid the same day
    assert by["1030"] == Decimal("-20")  # expense paid by bank transfer
    assert pay["status"] == "Paid"


def test_xero_csv_needs_confirmed_mapping(api):
    c, owner, acct = api("cashier"), api("owner"), api("acct")
    m = menu(c)
    paid_order(c, m)
    assert acct.get("/accounting/mapping").json()["accounts"]["sales"] == {"code": "4000", "name": "Food and beverage sales", "placeholder": True}
    assert acct.get("/accounting/journals/xero.csv").json()["error"]["code"] == "MAPPING_NOT_CONFIRMED"
    cat = m["MN-02"]
    category = next(i["category_name_en"] for i in c.get("/menu/pos").json()["items"] if i["code"] == "MN-02")
    r = owner.put("/settings/accounting", {"value": {"mapping_confirmed": True, "accounts": {"sales": "200"}, "category_accounts": {category: "210"},
                                                     "tax_rate_name": "No Tax"}})
    assert r.status_code == 200, r.json()
    assert acct.get("/accounting/mapping").json()["accounts"]["sales"]["placeholder"] is False
    res = acct.get("/accounting/journals/xero.csv")
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))
    assert rows[0] == ["*Narration", "*Date", "Description", "*AccountCode", "*TaxRate", "*Amount", "TrackingName1", "TrackingOption1"]
    body = rows[1:]
    assert body[0][0].startswith("RMS RVS daily summary") and body[0][1] == date.today().isoformat() and all(r[0] == "" and r[1] == "" for r in body[1:])
    assert sum(Decimal(r[5]) for r in body) == 0 and {r[4] for r in body} == {"No Tax"} and {r[7] for r in body} == {"RVS"}
    codes = {r[3]: Decimal(r[5]) for r in body}
    assert codes["210"] == Decimal("-9.50") and "200" not in codes  # all of today's sales are in the mapped category
    assert api("auditor").get("/audit-logs?action=accounting.export").json()["total"] == 1
    assert cat  # menu lookup used above
