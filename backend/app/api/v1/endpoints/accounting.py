"""Accounting export (Xero manual journals, one per branch and business day)."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.dependencies import Ctx, require
from app.services import accounting as svc
from app.services.reports import _range

router = APIRouter(prefix="/accounting", tags=["accounting"])
Export = Annotated[Ctx, Depends(require("accounting.export"))]


@router.get("/mapping", summary="Account codes in use; 'placeholder' marks codes not yet replaced in the accounting settings")
def mapping(ctx: Export):
    return svc.mapping(ctx)


@router.get("/journals", summary="Daily journals for review before export; each balances to zero (debits positive, credits negative)")
def journals(ctx: Export, date_from: date | None = None, date_to: date | None = None):
    start, end = _range(date_from, date_to, ctx)
    return {"from": start, "to": end, "branch": ctx.branch.code, "journals": svc.build(ctx, start, end)}


@router.get("/journals/xero.csv", summary="Xero manual journal import file (needs the account mapping confirmed); audited")
def xero(ctx: Export, date_from: date | None = None, date_to: date | None = None):
    start, end = _range(date_from, date_to, ctx)
    body = svc.xero_csv(ctx, svc.build(ctx, start, end))
    return Response("﻿" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="xero-journals-{ctx.branch.code}-{start}-{end}.csv"'})
