"""Customer credit accounts (FR-CUST-011, FR-BILL-017)."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select

from app.core.dependencies import Ctx, require
from app.models import CreditAccount
from app.schemas.common import Strict
from app.services import billing
from app.services import credit as svc
from app.services.reports import _range

router = APIRouter(tags=["credit accounts"])


class AccountIn(Strict):
    customer_id: uuid.UUID
    credit_limit: Decimal = Field(ge=0)
    terms_days: int | None = Field(None, ge=0, le=365, description="Default from the credit settings (30 days)")
    company_name: str | None = Field(None, max_length=120)
    billing_contact: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=500)


class AccountPatch(Strict):
    credit_limit: Decimal | None = Field(None, ge=0)
    terms_days: int | None = Field(None, ge=0, le=365)
    company_name: str | None = Field(None, max_length=120)
    billing_contact: str | None = Field(None, max_length=120)
    status: Literal["Active", "Suspended", "Closed"] | None = None
    notes: str | None = Field(None, max_length=500)


class ChargeIn(Strict):
    account_id: uuid.UUID
    approval_id: uuid.UUID | None = Field(None, description="Manager approval (action credit_override) when over the limit or the account is overdue")


class SettleIn(Strict):
    amount: Decimal = Field(gt=0)
    method: Literal["CASH_USD", "BANK_TRANSFER", "KHQR", "CARD"]
    reference: str | None = Field(None, max_length=80)


@router.get("/credit-accounts", summary="Accounts with balance, available credit and overdue amount")
def accounts(ctx: Annotated[Ctx, Depends(require("credit.view"))], status: str | None = None, overdue_only: bool = False):
    stmt = select(CreditAccount)
    if status:
        stmt = stmt.where(CreditAccount.status == status)
    rows = [svc.account_out(ctx, a) for a in ctx.db.scalars(stmt.order_by(CreditAccount.account_no))]
    return [r for r in rows if r["overdue"] > 0] if overdue_only else rows


@router.post("/credit-accounts", status_code=201, summary="Open an account (Owner, GM or Accountant)")
def open_account(body: AccountIn, ctx: Annotated[Ctx, Depends(require("credit.manage"))]):
    return svc.account_out(ctx, svc.open_account(ctx, body.model_dump()))


@router.get("/credit-accounts/{account_id}")
def get_account(account_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("credit.view"))]):
    a = svc.get_account(ctx, account_id)
    return {**svc.account_out(ctx, a), "ageing": svc.ageing(ctx, a)}


@router.patch("/credit-accounts/{account_id}", summary="Change limit, terms or status (Owner, GM or Accountant)")
def update_account(account_id: uuid.UUID, body: AccountPatch, ctx: Annotated[Ctx, Depends(require("credit.manage"))]):
    return svc.account_out(ctx, svc.update_account(ctx, svc.get_account(ctx, account_id, lock=True), body.model_dump(exclude_unset=True)))


@router.post("/bills/{bill_id}/charge-to-account", summary="Transfer the bill's balance to a credit account (FR-BILL-017); over limit or overdue needs a manager")
def charge(bill_id: uuid.UUID, body: ChargeIn, ctx: Annotated[Ctx, Depends(require("credit.charge"))]):
    return svc.charge_bill(ctx, billing.get_bill(ctx, bill_id, lock=True), body.account_id, body.approval_id)


@router.post("/credit-accounts/{account_id}/settlements", status_code=201, summary="Record a payment from the customer; oldest charges are settled first")
def settle(account_id: uuid.UUID, body: SettleIn, ctx: Annotated[Ctx, Depends(require("credit.settle"))]):
    a = svc.get_account(ctx, account_id, lock=True)
    t = svc.settle(ctx, a, body.amount, body.method, body.reference)
    return {"transaction_no": t.txn_no, "amount": -t.amount, "account": svc.account_out(ctx, a)}


@router.get("/credit-accounts/{account_id}/statement", summary="Statement with opening and closing balance and ageing by due date")
def statement(account_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("credit.view"))], date_from: date | None = None, date_to: date | None = None):
    start, end = _range(date_from, date_to, ctx)
    return svc.statement(ctx, svc.get_account(ctx, account_id), start, end)
