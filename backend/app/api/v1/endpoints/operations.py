"""Phase 4 back-office operations: payment reconciliation (FR-BILL-018), message delivery log (FR-NOTIF-013),
notification preferences (FR-NOTIF-011), recurring expenses (FR-EXP-008) and scheduled report emails (FR-RPT-027)."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

from app.core.dependencies import Ctx, require
from app.schemas.common import Strict
from app.services import messages, reconciliation, schedules

router = APIRouter(tags=["operations"])
Reconcile = Annotated[Ctx, Depends(require("payments.reconcile"))]
Authed = Annotated[Ctx, Depends(require("notifications.view"))]


# ---------------------------------------------------------------- payment reconciliation
class StatementLineIn(Strict):
    reference: str = Field(min_length=1, max_length=80)
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: Literal["USD", "KHR"] = "USD"
    received_at: datetime | None = None


class StatementIn(Strict):
    business_date: date
    method_code: str = Field(min_length=1, max_length=30)
    lines: list[StatementLineIn] = Field(min_length=1, max_length=2000)


class StatementImportIn(Strict):
    business_date: date
    method_code: str = Field(min_length=1, max_length=30)
    csv: str = Field(min_length=1, max_length=2_000_000, description="Header row with reference,amount[,currency][,received_at]")


class MatchIn(Strict):
    payment_id: uuid.UUID | None = Field(None, description="Null unlinks the line")
    note: str = Field(min_length=2, max_length=300)


class ReasonIn(Strict):
    reason: str = Field(min_length=2, max_length=300)


class CloseIn(Strict):
    business_date: date
    method_code: str
    note: str | None = Field(None, max_length=500, description="Required when there are differences")


@router.get("/payment-reconciliation/methods", summary="Electronic payment methods that can be reconciled")
def rec_methods(ctx: Reconcile):
    return [{"code": m.code, "name": m.name, "kind": m.kind} for m in reconciliation.electronic_methods(ctx.db)]


@router.get("/payment-reconciliation/days", summary="Days with electronic payments and their reconciliation state")
def rec_days(ctx: Reconcile, date_from: date | None = None, date_to: date | None = None):
    end = date_to or ctx.business_date()
    return reconciliation.summary(ctx, date_from or end - timedelta(days=30), end)


@router.get("/payment-reconciliation", summary="Recorded payments vs statement lines for one business day and method")
def rec_view(ctx: Reconcile, business_date: date, method_code: str):
    return reconciliation.view(ctx, business_date, method_code)


@router.post("/payment-reconciliation/lines", summary="Add statement lines; a reference already entered is skipped (no duplicates)")
def rec_add(body: StatementIn, ctx: Reconcile):
    return reconciliation.add_lines(ctx, body.business_date, body.method_code, [ln.model_dump() for ln in body.lines])


@router.post("/payment-reconciliation/import", summary="Import a CSV statement; nothing is imported if any row is invalid")
def rec_import(body: StatementImportIn, ctx: Reconcile):
    return reconciliation.add_lines(ctx, body.business_date, body.method_code, reconciliation.parse_csv(body.csv))


@router.post("/payment-reconciliation/lines/{line_id}/match", summary="Match a statement line to a payment by hand, or unlink it")
def rec_match(line_id: uuid.UUID, body: MatchIn, ctx: Reconcile):
    return reconciliation.match(ctx, line_id, body.payment_id, body.note)


@router.post("/payment-reconciliation/lines/{line_id}/remove", summary="Remove a mistyped statement line while the day is open (audited)")
def rec_remove(line_id: uuid.UUID, body: ReasonIn, ctx: Reconcile):
    return reconciliation.remove_line(ctx, line_id, body.reason)


@router.post("/payment-reconciliation/close", summary="Lock the day; differences need a note")
def rec_close(body: CloseIn, ctx: Reconcile):
    return reconciliation.close(ctx, body.business_date, body.method_code, body.note)


# ---------------------------------------------------------------- message delivery log
@router.get("/message-log", summary="Text messages and emails with delivery status, attempts and last error")
def message_log(ctx: Annotated[Ctx, Depends(require("messages.view"))], date_from: date | None = None, date_to: date | None = None,
                channel: Literal["SMS", "Email"] | None = None, status: str | None = None):
    end = date_to or ctx.business_date()
    return messages.log(ctx, date_from or end - timedelta(days=7), end, channel, status)


@router.post("/message-log/{channel}/{message_id}/retry", summary="Give a failed message a fresh set of attempts")
def message_retry(channel: Literal["SMS", "Email"], message_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("messages.retry"))]):
    return messages.retry(ctx, channel, message_id)


# ---------------------------------------------------------------- notification preferences
class PrefsIn(Strict):
    preferences: dict[str, bool]


@router.get("/me/notification-preferences", summary="Mandatory kinds are always on; optional kinds can be muted")
def get_prefs(ctx: Authed):
    return messages.preferences(ctx)


@router.put("/me/notification-preferences")
def put_prefs(body: PrefsIn, ctx: Authed):
    return messages.set_preferences(ctx, body.preferences)


# ---------------------------------------------------------------- recurring expenses
class Rule(Strict):
    day_of_week: int | None = Field(None, ge=0, le=6, description="0 = Monday")
    day_of_month: int | None = Field(None, ge=1, le=31, description="Short months use their last day")


class ExpenseTemplateIn(Rule):
    name: str = Field(min_length=1, max_length=80)
    category_id: uuid.UUID
    description: str = Field(min_length=1, max_length=500)
    payee: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: Literal["USD", "KHR"] = "USD"
    frequency: Literal["Weekly", "Monthly"]
    start_date: date | None = Field(None, description="First date to consider; default today")
    is_active: bool = True


@router.get("/expense-templates", summary="Recurring expenses (FR-EXP-008)")
def templates(ctx: Annotated[Ctx, Depends(require("expenses.view"))]):
    return schedules.list_templates(ctx)


@router.post("/expense-templates", status_code=201, summary="Creates Draft expenses on its schedule; people still submit them")
def create_template(body: ExpenseTemplateIn, ctx: Annotated[Ctx, Depends(require("expenses.create"))]):
    return schedules.save_template(ctx, body.model_dump())


@router.put("/expense-templates/{template_id}")
def update_template(template_id: uuid.UUID, body: ExpenseTemplateIn, ctx: Annotated[Ctx, Depends(require("expenses.create"))]):
    return schedules.save_template(ctx, body.model_dump(), template_id)


@router.post("/expense-templates/generate", summary="Create the drafts that are due now for this branch (the worker also does this hourly)")
def generate_templates(ctx: Annotated[Ctx, Depends(require("expenses.create"))]):
    out = schedules.generate_due(ctx.db, ctx.branch_id)
    return {"created": out["created"], "skipped": out["skipped"], "expense_ids": out["expense_ids"]}


# ---------------------------------------------------------------- scheduled reports
class ReportScheduleIn(Rule):
    report_id: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)
    frequency: Literal["Daily", "Weekly", "Monthly"]
    hour: int = Field(7, ge=0, le=23, description="Branch local time")
    recipient_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    is_active: bool = True

    @model_validator(mode="after")
    def _rule(self):
        if self.frequency == "Monthly" and self.day_of_month and self.day_of_month > 28:
            raise ValueError("Use a day from 1 to 28 for monthly reports")
        return self


Export = Annotated[Ctx, Depends(require("report.export"))]


@router.get("/report-schedules", summary="Scheduled report emails (FR-RPT-027)")
def report_schedules(ctx: Export):
    return schedules.list_schedules(ctx)


@router.post("/report-schedules", status_code=201, summary="Recipients must be able to see the report; they get a sign-in link, not the data")
def create_report_schedule(body: ReportScheduleIn, ctx: Export):
    return schedules.save_schedule(ctx, body.model_dump())


@router.put("/report-schedules/{schedule_id}")
def update_report_schedule(schedule_id: uuid.UUID, body: ReportScheduleIn, ctx: Export):
    return schedules.save_schedule(ctx, body.model_dump(), schedule_id)
