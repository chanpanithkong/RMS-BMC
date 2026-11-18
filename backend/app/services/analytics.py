"""Advanced analytics (owner's choice for Phase 3): daily summary tables, menu engineering, background report jobs.

Daily summaries follow SRS §12's reporting architecture: sales by item, category, hour, payment method and employee,
and consumption by ingredient, rebuilt per branch and business day at day-end and refreshed during the day by the
worker. Every rebuild replaces the day's rows, so it is safe to run again. Figures use the same bases as the reports:
item and category sales from finalised bills (RPT-03/04), hours and employees from completed orders (RPT-05/09),
payments by method (RPT-07), ingredient use from recipe consumption at weighted average cost (RPT-16).
"""
import csv
import io
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.dependencies import Ctx
from app.core.exceptions import BusinessRuleError, Conflict, Forbidden, NotFound
from app.models import (AnalyticsDaily, Bill, BillLine, Branch, Ingredient, InventoryTransaction, Order, OrderItem, Payment, ReportJob, User)
from app.services.platform import audit
from app.utils.money import ZERO, q
from app.utils.timeutil import utcnow

DIMENSIONS = ("item", "category", "hour", "method", "employee", "ingredient")
REPORT_DIR = Path(__file__).resolve().parents[2] / "uploads" / "reports"
JOB_HOURS = 24


# ---------------------------------------------------------------- daily summaries
def refresh_day(db: Session, branch: Branch, d: date) -> int:
    rows: dict[tuple[str, str], dict] = {}

    def row(dim: str, key: str, label: str, group: str | None = None) -> dict:
        r = rows.setdefault((dim, key), {"label": label, "group_label": group, "count": 0, "quantity": ZERO, "gross": ZERO, "discount": ZERO, "net": ZERO,
                                         "cost": ZERO})
        r["label"] = label
        return r

    # items and categories: bill lines of finalised bills (a split bill carries its share of each item)
    lines = db.execute(select(OrderItem.id, OrderItem.menu_item_id, OrderItem.item_name_en_snapshot, OrderItem.category_name_snapshot, OrderItem.quantity,
                              BillLine.quantity_share, BillLine.amount_gross, BillLine.amount_discount, BillLine.amount_net)
                       .join(BillLine, BillLine.order_item_id == OrderItem.id).join(Bill, Bill.id == BillLine.bill_id)
                       .where(Bill.branch_id == branch.id, Bill.status.in_(("Paid", "Refunded")), Bill.business_date == d)).all()
    cost = dict(db.execute(select(InventoryTransaction.source_id, func.sum(InventoryTransaction.total_cost)).where(
        InventoryTransaction.source_type == "OrderItem", InventoryTransaction.txn_type.in_(("SALE_CONSUMPTION", "SALE_REVERSAL")),
        InventoryTransaction.source_id.in_({x[0] for x in lines} or {None})).group_by(InventoryTransaction.source_id)).all())
    for oid, mid, name, cat, qty, share, gross, disc, net in lines:
        c = -(cost.get(oid) or ZERO) * share
        for dim, key, label, group in (("item", str(mid), name, cat), ("category", cat[:80], cat, None)):
            r = row(dim, key, label, group)
            r["quantity"] += qty * share
            r["gross"] += gross
            r["discount"] += disc
            r["net"] += net
            r["cost"] += c

    # hours and employees: completed orders
    tz = ZoneInfo(branch.timezone)
    names = {}
    for o in db.scalars(select(Order).where(Order.branch_id == branch.id, Order.order_status == "Completed", Order.business_date == d)):
        h = o.created_at.astimezone(tz).hour
        for dim, key, label in (("hour", f"{h:02d}", f"{h:02d}:00"), ("employee", str(o.server_user_id), None)):
            if dim == "employee":
                if o.server_user_id not in names:
                    names[o.server_user_id] = db.scalar(select(User.full_name).where(User.id == o.server_user_id)) or "Unknown"
                label = names[o.server_user_id]
            r = row(dim, key, label)
            r["count"] += 1
            r["quantity"] += o.guest_count or 0
            r["net"] += o.subtotal
            r["discount"] += o.discount_total

    # payments by method and currency
    for method, cur, n, base in db.execute(select(Payment.method_code, Payment.currency, func.count(), func.sum(Payment.amount_base)).where(
            Payment.branch_id == branch.id, Payment.status == "Confirmed", Payment.business_date == d).group_by(Payment.method_code, Payment.currency)):
        r = row("method", f"{method}:{cur}", f"{method} ({cur})")
        r["count"], r["net"] = n, base

    # ingredients consumed by recipes
    for ing, iname, qty, c in db.execute(select(InventoryTransaction.ingredient_id, Ingredient.name_en, func.sum(InventoryTransaction.quantity),
                                                func.sum(InventoryTransaction.total_cost)).join(Ingredient, Ingredient.id == InventoryTransaction.ingredient_id)
                                         .where(InventoryTransaction.branch_id == branch.id, InventoryTransaction.business_date == d,
                                                InventoryTransaction.txn_type.in_(("SALE_CONSUMPTION", "SALE_REVERSAL")))
                                         .group_by(InventoryTransaction.ingredient_id, Ingredient.name_en)):
        r = row("ingredient", str(ing), iname)
        r["quantity"], r["cost"] = -qty, -(c or ZERO)

    db.execute(delete(AnalyticsDaily).where(AnalyticsDaily.branch_id == branch.id, AnalyticsDaily.business_date == d))
    now = utcnow()
    for (dim, key), r in rows.items():
        db.add(AnalyticsDaily(branch_id=branch.id, business_date=d, dimension=dim, key=key, label=(r["label"] or key)[:160], group_label=r["group_label"],
                              count=r["count"], quantity=Decimal(r["quantity"]).quantize(Decimal("0.001")), gross=q(r["gross"]),
                              discount=q(r["discount"]), net=q(r["net"]), cost=q(r["cost"]), refreshed_at=now))
    db.flush()
    return len(rows)


def refresh_recent(db: Session) -> dict:
    """Worker: today and yesterday for every active branch (late refunds and completions land in yesterday's figures)."""
    from app.utils.timeutil import business_date_for

    out = {}
    for b in db.scalars(select(Branch).where(Branch.is_active)):
        today = business_date_for(utcnow(), b.timezone, b.day_end_time)
        out[b.code] = sum(refresh_day(db, b, d) for d in (today - timedelta(days=1), today))
    return out


def rebuild(ctx: Ctx, start: date, end: date) -> dict:
    if (end - start).days > 400:
        raise BusinessRuleError("RANGE_TOO_LONG", "Rebuild at most 400 days at a time.")
    n, d = 0, start
    while d <= end:
        n += refresh_day(ctx.db, ctx.branch, d)
        d += timedelta(days=1)
    audit(ctx.db, ctx, "analytics.rebuild", "Branch", ctx.branch_id, after={"from": start, "to": end, "rows": n})
    return {"from": start, "to": end, "rows": n}


def summary(ctx: Ctx, dimension: str, start: date, end: date, group: str | None = None) -> dict:
    if dimension not in DIMENSIONS:
        raise BusinessRuleError("VALIDATION_ERROR", f"dimension must be one of {', '.join(DIMENSIONS)}.")
    stmt = select(AnalyticsDaily.key, func.max(AnalyticsDaily.label), func.max(AnalyticsDaily.group_label), func.sum(AnalyticsDaily.count),
                  func.sum(AnalyticsDaily.quantity), func.sum(AnalyticsDaily.gross), func.sum(AnalyticsDaily.discount), func.sum(AnalyticsDaily.net),
                  func.sum(AnalyticsDaily.cost)).where(AnalyticsDaily.branch_id == ctx.branch_id, AnalyticsDaily.dimension == dimension,
                                                       AnalyticsDaily.business_date.between(start, end)).group_by(AnalyticsDaily.key)
    if group:
        stmt = stmt.where(AnalyticsDaily.group_label == group)
    rows = [{"key": k, "label": lab, "group": grp, "count": n, "quantity": qty, "gross": g, "discount": dsc, "net": net, "cost": c}
            for k, lab, grp, n, qty, g, dsc, net, c in ctx.db.execute(stmt)]
    rows.sort(key=lambda r: r["key"] if dimension == "hour" else -r["net"] if dimension != "ingredient" else -r["cost"])
    days, last = ctx.db.execute(select(func.count(func.distinct(AnalyticsDaily.business_date)), func.max(AnalyticsDaily.refreshed_at)).where(
        AnalyticsDaily.branch_id == ctx.branch_id, AnalyticsDaily.business_date.between(start, end))).one()
    return {"dimension": dimension, "from": start, "to": end, "rows": rows, "days_with_data": days, "days_in_range": (end - start).days + 1,
            "last_refreshed": last, "note": "Days without sales have no rows. Run a rebuild for dates before the summaries were introduced."}


# ---------------------------------------------------------------- menu engineering (RPT-23 purpose)
def menu_engineering(ctx: Ctx, start: date, end: date, category: str | None = None) -> dict:
    """Kasavana-Smith matrix. Popularity is high when an item's share of quantity is at least 70 % of an even share
    (0.7 / number of items); profitability is high when its contribution margin per unit is at least the menu's
    quantity-weighted average. Items without recipe cost are listed but not classified (their margin is unknown)."""
    rows = summary(ctx, "item", start, end, category)["rows"]
    costed = [r for r in rows if r["cost"] > 0 and r["quantity"] > 0]
    total_qty = sum((r["quantity"] for r in costed), ZERO)
    total_cm = sum((r["net"] - r["cost"] for r in costed), ZERO)
    n = len(costed)
    pop_threshold = (Decimal("0.7") / n) if n else ZERO
    avg_cm = (total_cm / total_qty) if total_qty else ZERO
    out = []
    for r in rows:
        item = {"menu_item_id": r["key"], "item": r["label"], "category": r["group"], "quantity": r["quantity"], "net_sales": r["net"], "food_cost": r["cost"],
                "average_price": q(r["net"] / r["quantity"]) if r["quantity"] else ZERO}
        if r in costed:
            cm_unit = (r["net"] - r["cost"]) / r["quantity"]
            mix = r["quantity"] / total_qty
            high_pop, high_cm = mix >= pop_threshold, cm_unit >= avg_cm
            item.update(contribution_margin_per_unit=q(cm_unit), total_contribution=q(r["net"] - r["cost"]), menu_mix_percent=q(mix * 100),
                        food_cost_percent=q(r["cost"] * 100 / r["net"]) if r["net"] else ZERO,
                        classification="Star" if high_pop and high_cm else "Plowhorse" if high_pop else "Puzzle" if high_cm else "Dog")
        else:
            item.update(contribution_margin_per_unit=None, total_contribution=None, menu_mix_percent=None, food_cost_percent=None, classification="Unclassified")
        out.append(item)
    order = {"Star": 0, "Plowhorse": 1, "Puzzle": 2, "Dog": 3, "Unclassified": 4}
    out.sort(key=lambda x: (order[x["classification"]], -x["quantity"]))
    counts = defaultdict(int)
    for x in out:
        counts[x["classification"]] += 1
    return {"from": start, "to": end, "category": category, "items_classified": n, "popularity_threshold_percent": q(pop_threshold * 100),
            "average_contribution_margin": q(avg_cm), "counts": dict(counts), "rows": out,
            "note": "Star: keep and feature. Plowhorse: popular but low margin, review price or cost. Puzzle: profitable but slow, promote or reposition. "
                    "Dog: consider removing. Unclassified items have no recipe cost."}


# ---------------------------------------------------------------- background report jobs (NFR-PERF-009)
def create_job(ctx: Ctx, report_id: str, params: dict) -> ReportJob:
    from app.services.reports import _all_reports, _range

    reports = _all_reports()
    if report_id not in reports:
        raise NotFound("Report")
    if not any(ctx.can(p) for p in reports[report_id][1]):
        raise Forbidden(f"You don't have access to {reports[report_id][0]}.", code="REPORT_FORBIDDEN")
    try:
        parsed = {k: date.fromisoformat(v) if isinstance(v, str) else v for k, v in params.items() if k in ("date_from", "date_to")}
    except ValueError:
        raise BusinessRuleError("VALIDATION_ERROR", "Dates must be YYYY-MM-DD.")
    start, end = _range(parsed.get("date_from"), parsed.get("date_to"), ctx)
    busy = ctx.db.scalar(select(func.count()).select_from(ReportJob).where(ReportJob.requested_by == ctx.user_id, ReportJob.status.in_(("Queued", "Running"))))
    if busy >= 3:
        raise Conflict("TOO_MANY_JOBS", "Wait for your running reports to finish first.")
    job = ReportJob(branch_id=ctx.branch_id, requested_by=ctx.user_id, report_id=report_id,
                    params=jsonable_encoder({**params, "date_from": start, "date_to": end}))
    ctx.db.add(job)
    ctx.db.flush()
    audit(ctx.db, ctx, "report.job_queued", "ReportJob", job.id, after={"report": report_id, "from": start, "to": end})
    return job


def job_out(j: ReportJob) -> dict:
    return {"id": j.id, "report_id": j.report_id, "params": j.params, "status": j.status, "rows": j.rows, "error": j.error, "created_at": j.created_at,
            "finished_at": j.finished_at, "expires_at": j.expires_at,
            "download": f"/api/v1/report-jobs/{j.id}/download" if j.status == "Done" and j.expires_at and j.expires_at > utcnow() else None}


def _to_csv(data: dict) -> str:
    data = jsonable_encoder(data)
    buf = io.StringIO()
    rows = data["rows"]
    if rows:
        keys = list(dict.fromkeys(k for r in rows for k in r.keys()))
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    buf.write(f"\n# {data['name']} {data['from']}..{data['to']} branch {data['branch']} generated {data['generated_at']} by {data['generated_by']}. {data['note']}\n")
    return "﻿" + buf.getvalue()


def run_job(db: Session, job: ReportJob) -> None:
    """Runs as the requester, with their permissions as they are now (a revoked permission stops the job)."""
    from app.core.dependencies import load_permissions
    from app.services import reports

    user = db.get(User, job.requested_by)
    branch = db.get(Branch, job.branch_id)
    if user is None or user.status != "Active":
        raise Forbidden("The requesting user is no longer active.")
    perms, limits = load_permissions(db, user)
    ctx = Ctx(db=db, user=user, session_id=uuid.UUID(int=0), branch=branch, permissions=perms, roles={r.code for r in user.roles}, _limits=limits)
    p = job.params
    data = reports.run(ctx, job.report_id, date.fromisoformat(p["date_from"]), date.fromisoformat(p["date_to"]),
                       {k: v for k, v in p.items() if k not in ("date_from", "date_to", "schedule_id")})
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{job.id}.csv"
    (REPORT_DIR / name).write_text(_to_csv(data), encoding="utf-8")
    job.rows, job.file_name = len(data["rows"]), name


def process_jobs(db: Session, limit: int = 3) -> dict:
    out = {"done": 0, "failed": 0, "expired": 0}
    for job in db.scalars(select(ReportJob).where(ReportJob.status == "Queued").order_by(ReportJob.created_at).limit(limit).with_for_update(skip_locked=True)).all():
        job.status, job.started_at = "Running", utcnow()
        db.commit()
        try:
            with db.begin_nested():
                run_job(db, job)
            job.status, job.finished_at, job.expires_at = "Done", utcnow(), utcnow() + timedelta(hours=JOB_HOURS)
            from app.services.schedules import on_job_done

            on_job_done(db, job)  # FR-RPT-027: scheduled jobs email the recipient a link
            out["done"] += 1
        except Exception as e:  # noqa: BLE001 - the error is stored on the job for the user
            job.status, job.finished_at, job.error = "Failed", utcnow(), (getattr(e, "message", None) or str(e))[:500]
            out["failed"] += 1
        db.commit()
    for job in db.scalars(select(ReportJob).where(ReportJob.status == "Done", ReportJob.expires_at < utcnow(), ReportJob.file_name.is_not(None))):
        (REPORT_DIR / job.file_name).unlink(missing_ok=True)  # expired links stop working and the file is removed
        job.file_name = None
        out["expired"] += 1
    db.commit()
    return out


def download(ctx: Ctx, job_id: uuid.UUID) -> tuple[Path, ReportJob]:
    j = ctx.db.get(ReportJob, job_id)
    if j is None or j.requested_by != ctx.user_id:
        raise NotFound("Report job")  # only the requester can download
    if j.status != "Done" or not j.file_name or not j.expires_at or j.expires_at < utcnow():
        raise Conflict("REPORT_NOT_AVAILABLE", "This report isn't ready or its download has expired.")
    audit(ctx.db, ctx, "report.export", "Report", None, after={"report": j.report_id, "job": j.id, "rows": j.rows, "background": True})  # FR-RPT-024
    return REPORT_DIR / j.file_name, j
