"""Phase 4 operations: FR-BILL-018 reconciliation, FR-NOTIF-013 delivery log, FR-NOTIF-011 preferences, FR-EXP-008 recurring
expenses and FR-RPT-027 scheduled report emails."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, text

from tests.helpers import line, menu, money


def bank_payment(c, ref: str) -> dict:
    m = menu(c)
    o = c.post("/orders", {"order_type": "Takeaway", "pickup_name": "R", "items": [line(m, "DR-03", 2)]}, idem=True).json()
    bill = c.post(f"/orders/{o['id']}/bills", {"mode": "single"}).json()[0]
    r = c.post("/payments", {"bill_id": bill["id"], "method": "BANK_TRANSFER", "currency": "USD", "reference": ref}, idem=True)
    assert r.status_code == 201, r.json()
    return r.json() | {"total": bill["total"]}


def test_reconciliation_matches_statement_to_payments(api):
    c, acct, cashier2 = api("cashier"), api("acct"), api("cashier2")
    p1 = bank_payment(c, "BT-1001")
    p2 = bank_payment(c, "BT-1002")
    bank_payment(c, "BT-1003")  # not on the statement
    day = acct.get("/payment-reconciliation/methods").json()
    assert {m["code"] for m in day} >= {"BANK_TRANSFER", "KHQR", "CARD"} and "CASH_USD" not in {m["code"] for m in day}
    bdate = p1["business_date"] if "business_date" in p1 else date.today().isoformat()
    v = acct.get(f"/payment-reconciliation?business_date={bdate}&method_code=BANK_TRANSFER").json()
    assert v["status"] == "NotStarted" and v["counts"]["not_on_statement"] == 3 and v["balanced"] is False
    body = {"business_date": bdate, "method_code": "BANK_TRANSFER", "lines": [
        {"reference": "bt-1001", "amount": str(money(p1["total"]))},          # matched (reference ignores case)
        {"reference": "BT-1002", "amount": str(money(p2["total"]) + 1)},      # amount differs
        {"reference": "BT-9999", "amount": "5.00"},                           # no payment recorded
    ]}
    r = acct.post("/payment-reconciliation/lines", body)
    assert r.status_code == 200, r.json()
    v = r.json()
    status = {ln["reference"]: ln["match_status"] for ln in v["lines"]}
    assert status == {"bt-1001": "Matched", "BT-1002": "AmountMismatch", "BT-9999": "NotRecorded"}
    assert v["counts"] == {"matched": 1, "amount_mismatch": 1, "not_recorded": 1, "not_on_statement": 1}
    # Importing the same entries again adds nothing (no duplicates)
    again = acct.post("/payment-reconciliation/import", {"business_date": bdate, "method_code": "BANK_TRANSFER",
                                                         "csv": "reference,amount\nBT-1001,1.00\nBT-9999,5.00\n"}).json()
    assert again["added"] == 0 and again["skipped"] == 2 and len(again["lines"]) == 3
    bad = acct.post("/payment-reconciliation/import", {"business_date": bdate, "method_code": "BANK_TRANSFER", "csv": "reference,amount\nX,abc\n"})
    assert bad.json()["error"]["code"] == "IMPORT_INVALID"
    # Manual match of the unknown line to the payment that wasn't on the statement
    missing = next(p for p in v["payments"] if p["status"] == "NotOnStatement")
    line9 = next(ln for ln in v["lines"] if ln["reference"] == "BT-9999")
    m = acct.post(f"/payment-reconciliation/lines/{line9['id']}/match", {"payment_id": missing["payment_id"], "note": "Bank shortened the reference"}).json()
    assert next(ln for ln in m["lines"] if ln["id"] == line9["id"])["match_status"] in ("Matched", "AmountMismatch")
    taken = acct.post(f"/payment-reconciliation/lines/{line9['id']}/match", {"payment_id": p1["payment_id"], "note": "wrong"})
    assert taken.json()["error"]["code"] == "PAYMENT_ALREADY_MATCHED"
    # Differences need a note to lock the day; then it is read-only
    assert acct.post("/payment-reconciliation/close", {"business_date": bdate, "method_code": "BANK_TRANSFER"}).json()["error"]["code"] == "RECONCILIATION_DIFFERENCES"
    closed = acct.post("/payment-reconciliation/close", {"business_date": bdate, "method_code": "BANK_TRANSFER", "note": "BT-1002 bank fee, checked with bank"}).json()
    assert closed["status"] == "Closed"
    assert acct.post("/payment-reconciliation/lines", body).json()["error"]["code"] == "RECONCILIATION_CLOSED"
    # Payments are untouched and permissions are checked
    assert money(c.get(f"/bills/{p1['bill']['id']}").json()["paid_total"]) == money(p1["total"])
    assert cashier2.get(f"/payment-reconciliation?business_date={bdate}&method_code=BANK_TRANSFER").status_code == 403
    days = acct.get("/payment-reconciliation/days").json()
    assert any(d["method_code"] == "BANK_TRANSFER" and d["status"] == "Closed" for d in days)
    assert acct.get(f"/payment-reconciliation?business_date={bdate}&method_code=CASH_USD").json()["error"]["code"] == "NOT_ELECTRONIC"


def test_message_log_and_retry(api, engine):
    from app.core.database import session_factory
    from app.models import OutboxEvent, SmsMessage
    from app.workers.celery_app import MAX_ATTEMPTS

    gm, cashier, admin = api("gm"), api("cashier"), api("admin")
    with session_factory()() as db:
        bid = db.execute(text("select id from branches limit 1")).scalar()
        sms = SmsMessage(branch_id=bid, to_msisdn="85512345678", purpose="order_ready", content="Your order is ready", status="Failed", attempts=5, last_error="HTTP 503")
        mail = OutboxEvent(branch_id=bid, event_type="email.purchase_order", topic="po", payload={"email": "sales@supplier.example", "po_no": "PO-1"},
                           attempts=MAX_ATTEMPTS, last_error="SMTP timeout", delivery_status="Failed")
        ok = OutboxEvent(branch_id=bid, event_type="email.online_order_confirmation", topic="o", payload={"email": "guest@example.com"},
                         processed_at=datetime.now(timezone.utc), delivery_status="Logged")
        db.add_all([sms, mail, ok])
        db.commit()
        ids = {"sms": sms.id, "mail": mail.id, "ok": ok.id}
    rows = gm.get("/message-log").json()
    by_id = {r["id"]: r for r in rows}
    assert by_id[str(ids["sms"])]["status"] == "Failed" and by_id[str(ids["sms"])]["last_error"] == "HTTP 503"
    assert by_id[str(ids["mail"])]["status"] == "Failed" and by_id[str(ids["ok"])]["status"] == "Logged"
    # GM may see customer contact details; the system administrator sees them masked and no SMS text
    assert by_id[str(ids["sms"])]["to"] == "85512345678"
    masked = {r["id"]: r for r in admin.get("/message-log").json()}
    assert masked[str(ids["sms"])]["to"] != "85512345678" and masked[str(ids["sms"])]["summary"] is None
    assert masked[str(ids["mail"])]["to"].startswith("s•••@")
    assert cashier.get("/message-log").status_code == 403
    assert api("auditor").post(f"/message-log/SMS/{ids['sms']}/retry").status_code == 403
    assert gm.post(f"/message-log/Email/{ids['ok']}/retry").json()["error"]["code"] == "NOT_FAILED"
    assert gm.post(f"/message-log/SMS/{ids['sms']}/retry").json()["status"] == "Queued"
    assert gm.post(f"/message-log/Email/{ids['mail']}/retry").json()["status"] == "Queued"
    after = {r["id"]: r for r in gm.get("/message-log").json()}
    assert after[str(ids["sms"])]["status"] == "Queued" and after[str(ids["mail"])]["status"] == "Queued"
    assert len(gm.get("/message-log?channel=Email&status=Logged").json()) >= 1


def test_email_backoff_and_status(api, engine, monkeypatch):
    from app.core.database import session_factory
    from app.models import OutboxEvent
    from app.workers import celery_app

    with session_factory()() as db:
        e = OutboxEvent(event_type="email.online_order_rejected", topic="t", payload={"email": "a@example.com", "order_no": "1", "branch": "B", "reason": "Closed"})
        db.add(e)
        db.commit()
        eid = e.id

    def boom(self, to, subject, body):
        raise OSError("connection refused")

    monkeypatch.setattr(celery_app.EmailSender, "send", boom)
    celery_app.process_outbox()
    with session_factory()() as db:
        e = db.get(OutboxEvent, eid)
        assert e.attempts == 1 and e.last_error == "connection refused" and e.next_attempt_at is not None and e.processed_at is None
    celery_app.process_outbox()  # still backing off: not attempted again yet
    with session_factory()() as db:
        assert db.get(OutboxEvent, eid).attempts == 1
        db.get(OutboxEvent, eid).next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(celery_app.EmailSender, "send", lambda self, to, subject, body: "Logged")
    celery_app.process_outbox()
    with session_factory()() as db:
        e = db.get(OutboxEvent, eid)
        assert e.processed_at is not None and e.delivery_status == "Logged" and e.last_error is None


def test_notification_preferences(api, seeded):
    from app.core.database import session_factory
    from app.models import Notification
    from app.services.platform import notify_users

    gm = api("gm")
    prefs = {p["kind"]: p for p in gm.get("/me/notification-preferences").json()}
    assert prefs["Approval"]["mandatory"] and prefs["Stock"]["enabled"] and not prefs["Stock"]["mandatory"]
    assert gm.put("/me/notification-preferences", {"preferences": {"Approval": False}}).json()["error"]["code"] == "NOTIFICATION_MANDATORY"
    out = {p["kind"]: p["enabled"] for p in gm.put("/me/notification-preferences", {"preferences": {"Stock": False}}).json()}
    assert out["Stock"] is False and out["Approval"] is True
    uid = seeded["users"]["gm"]
    with session_factory()() as db:
        notify_users(db, [uid], seeded["branch_id"], "Stock", "Low stock: Rice", "2 kg left")
        notify_users(db, [uid], seeded["branch_id"], "Approval", "Expense awaiting approval", "EX-1")
        db.commit()
        kinds = set(db.scalars(select(Notification.kind).where(Notification.recipient_user_id == uid)))
    assert "Approval" in kinds and "Stock" not in kinds


def test_recurring_expense_templates(api):
    s, gm, waiter = api("supv"), api("gm"), api("waiter")
    cat = next(c["id"] for c in s.get("/expense-categories").json() if c["name_en"] == "Water")
    today = date.today()
    body = {"name": "Water delivery", "category_id": cat, "description": "Weekly drinking water", "payee": "Water Co", "amount": "18.00",
            "frequency": "Weekly", "day_of_week": today.weekday(), "start_date": (today - timedelta(days=14)).isoformat()}
    r = s.post("/expense-templates", body)
    assert r.status_code == 201, r.json()
    t = r.json()
    assert t["next_run_date"] == (today - timedelta(days=14)).isoformat()
    assert s.post("/expense-templates", {**body, "day_of_week": None}).json()["error"]["code"] == "VALIDATION_ERROR"
    assert waiter.post("/expense-templates", body).status_code == 403
    out = s.post("/expense-templates/generate").json()
    assert out["created"] == 3  # two weeks ago, last week and today
    again = s.post("/expense-templates/generate").json()
    assert again["created"] == 0  # one draft per date, however often it runs
    drafts = [e for e in gm.get("/expenses").json()["data"] if e["description"] == "Weekly drinking water"] if isinstance(gm.get("/expenses").json(), dict) else \
        [e for e in gm.get("/expenses").json() if e["description"] == "Weekly drinking water"]
    assert len(drafts) == 3 and all(d["status"] == "Draft" for d in drafts)
    assert {money(d["amount"]) for d in drafts} == {Decimal("18.00")}
    nxt = next(x for x in s.get("/expense-templates").json() if x["id"] == t["id"])["next_run_date"]
    assert nxt == (today + timedelta(days=7)).isoformat()
    monthly = s.post("/expense-templates", {**body, "name": "Rent", "frequency": "Monthly", "day_of_week": None, "day_of_month": 31, "start_date": "2027-02-01"}).json()
    assert monthly["next_run_date"] == "2027-02-28"  # short months use their last day


def test_report_schedule_emails_a_link(api, engine, seeded):
    from app.core.database import session_factory
    from app.models import OutboxEvent, ReportJob, ReportSchedule
    from app.services import analytics, schedules

    gm, acct, cashier = api("gm"), api("acct"), api("cashier")
    users = seeded["users"]
    with engine.begin() as conn:
        conn.execute(text("update users set email = username || '@rms.example' where username in ('gm','acct')"))
    catalogue = gm.get("/reports").json()
    report_id = next(r["id"] for r in (catalogue if isinstance(catalogue, list) else catalogue["reports"]) if r.get("available", True))
    bad = gm.post("/report-schedules", {"report_id": report_id, "name": "Daily sales", "frequency": "Daily", "hour": 7, "recipient_ids": [str(users["cashier"])]})
    assert bad.json()["error"]["code"] == "RECIPIENT_NOT_PERMITTED"
    assert gm.post("/report-schedules", {"report_id": report_id, "name": "x", "frequency": "Weekly", "recipient_ids": [str(users["gm"])]}).json()["error"]["code"] == "VALIDATION_ERROR"
    assert cashier.post("/report-schedules", {"report_id": report_id, "name": "x", "frequency": "Daily", "recipient_ids": [str(users["cashier"])]}).status_code == 403
    r = gm.post("/report-schedules", {"report_id": report_id, "name": "Daily sales", "frequency": "Daily", "hour": 7, "recipient_ids": [str(users["gm"]), str(users["acct"])]})
    assert r.status_code == 201, r.json()
    sched = r.json()
    assert len(sched["recipients"]) == 2 and sched["next_run_at"]
    with session_factory()() as db:
        s = db.get(ReportSchedule, uuid.UUID(sched["id"]))
        s.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        out = schedules.run_due_schedules(db)
        db.commit()
        assert out["jobs"] == 2
        assert schedules.run_due_schedules(db)["jobs"] == 0  # not due again until tomorrow
        db.commit()
        analytics.process_jobs(db, limit=5)
        jobs = db.scalars(select(ReportJob).where(ReportJob.params["schedule_id"].astext == sched["id"])).all()
        assert {j.status for j in jobs} == {"Done"}, [j.error for j in jobs]
        mails = db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == "email.scheduled_report")).all()
        assert sorted(m.payload["email"] for m in mails) == ["acct@rms.example", "gm@rms.example"]
        assert all("rows" not in m.payload for m in mails)  # a link, not the data
    # Each recipient sees their own job in "My background reports"
    assert any(j.get("report_id") == report_id for j in acct.get("/report-jobs").json())
