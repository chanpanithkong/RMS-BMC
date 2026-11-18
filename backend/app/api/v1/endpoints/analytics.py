"""Analytics: daily summaries, menu engineering, background report jobs."""
import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.dependencies import Ctx, require
from app.models import ReportJob
from app.services import analytics as svc
from app.services.reports import _range

router = APIRouter(tags=["analytics"])
Fin = Annotated[Ctx, Depends(require("report.financial.view"))]


@router.get("/analytics/summary", summary="Totals from the daily summaries by item, category, hour, method, employee or ingredient")
def summary(ctx: Fin, dimension: str = "item", date_from: date | None = None, date_to: date | None = None, group: str | None = None):
    start, end = _range(date_from, date_to, ctx)
    return svc.summary(ctx, dimension, start, end, group)


@router.post("/analytics/rebuild", summary="Rebuild the daily summaries for a date range (after corrections or for history)")
def rebuild(ctx: Annotated[Ctx, Depends(require("report.financial.view", "settings.manage"))], date_from: date | None = None, date_to: date | None = None):
    start, end = _range(date_from, date_to, ctx)
    return svc.rebuild(ctx, start, end)


@router.get("/analytics/menu-engineering", summary="Star / Plowhorse / Puzzle / Dog classification by popularity and contribution margin")
def menu_engineering(ctx: Fin, date_from: date | None = None, date_to: date | None = None, category: str | None = None):
    start, end = _range(date_from, date_to, ctx)
    return svc.menu_engineering(ctx, start, end, category)


@router.post("/reports/{report_id}/jobs", status_code=202, summary="Run a long report in the background (NFR-PERF-009); same access rules as the report")
def create_job(report_id: str, ctx: Annotated[Ctx, Depends(require("report.export"))], params: Annotated[dict[str, Any], Body()]):
    allowed = {"date_from", "date_to", "user_id", "customer_id", "supplier_id", "station_code", "category"}
    return svc.job_out(svc.create_job(ctx, report_id, {k: v for k, v in params.items() if k in allowed and v is not None}))


@router.get("/report-jobs", summary="My background reports")
def jobs(ctx: Annotated[Ctx, Depends(require("report.export"))]):
    return [svc.job_out(j) for j in ctx.db.scalars(select(ReportJob).where(ReportJob.requested_by == ctx.user_id).order_by(ReportJob.created_at.desc()).limit(50))]


@router.get("/report-jobs/{job_id}")
def job(job_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("report.export"))]):
    j = ctx.db.get(ReportJob, job_id)
    if j is None or j.requested_by != ctx.user_id:
        from app.core.exceptions import NotFound

        raise NotFound("Report job")
    return svc.job_out(j)


@router.get("/report-jobs/{job_id}/download", summary="CSV download; requester only, until the link expires (24 hours); audited")
def download(job_id: uuid.UUID, ctx: Annotated[Ctx, Depends(require("report.export"))]):
    path, j = svc.download(ctx, job_id)
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=f"{j.report_id}-{j.params['date_from']}-{j.params['date_to']}.csv")
