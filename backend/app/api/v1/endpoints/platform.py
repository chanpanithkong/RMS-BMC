"""Notifications (NOTIF) and audit trail (AUD)."""
import csv
import io
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.core.dependencies import Ctx, require
from app.core.exceptions import NotFound
from app.models import AuditLog, Notification
from app.schemas.common import ORM, Message, Page
from app.services.platform import audit, verify_audit_chain
from app.utils.timeutil import utcnow

notifications = APIRouter(prefix="/notifications", tags=["notifications"])
audit_router = APIRouter(prefix="/audit-logs", tags=["audit"])
NView = Annotated[Ctx, Depends(require("notifications.view"))]


class NotificationOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    data: dict | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(Page[NotificationOut]):
    unread: int


@notifications.get("", response_model=NotificationPage)
def list_notifications(ctx: NView, unread_only: bool = False, kind: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = select(Notification).where(Notification.recipient_user_id == ctx.user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if kind:
        stmt = stmt.where(Notification.kind == kind)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    unread = ctx.db.scalar(select(func.count()).select_from(Notification).where(Notification.recipient_user_id == ctx.user_id, Notification.read_at.is_(None)))
    rows = ctx.db.scalars(stmt.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": rows, "total": total, "unread": unread, "page": page, "page_size": page_size}


@notifications.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, ctx: NView):
    n = ctx.db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != ctx.user_id:
        raise NotFound("Notification")
    n.read_at = n.read_at or utcnow()
    return n


@notifications.post("/read-all", response_model=Message)
def mark_all_read(ctx: NView):
    ctx.db.execute(update(Notification).where(Notification.recipient_user_id == ctx.user_id, Notification.read_at.is_(None)).values(read_at=utcnow()))
    return {"message": "All notifications marked as read."}


class AuditOut(ORM):
    id: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_type: str
    ip: str | None
    branch_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    before_data: dict | None
    after_data: dict | None
    reason: str | None
    correlation_id: str | None
    entry_hash: str


def _audit_query(ctx: Ctx, entity_type, entity_id, actor_user_id, action, date_from, date_to):
    branches = [b.id for b in ctx.user.branches]
    stmt = select(AuditLog).where((AuditLog.branch_id.in_(branches)) | AuditLog.branch_id.is_(None))
    for col, val in ((AuditLog.entity_type, entity_type), (AuditLog.entity_id, entity_id), (AuditLog.actor_user_id, actor_user_id)):
        if val:
            stmt = stmt.where(col == val)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if date_from:
        stmt = stmt.where(AuditLog.occurred_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.occurred_at < date_to)
    return stmt


@audit_router.get("", response_model=Page[AuditOut], summary="Search by date range, user, action, entity type and id (FR-AUD-007)")
def search(ctx: Annotated[Ctx, Depends(require("audit.view"))], entity_type: str | None = None, entity_id: str | None = None, actor_user_id: uuid.UUID | None = None,
           action: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    stmt = _audit_query(ctx, entity_type, entity_id, actor_user_id, action, date_from, date_to)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


class IntegrityOut(BaseModel):
    valid: bool
    checked: int
    broken_at_id: int | None = None


@audit_router.get("/integrity", response_model=IntegrityOut, summary="Recompute the hash chain (FR-AUD-010)")
def integrity(ctx: Annotated[Ctx, Depends(require("audit.view"))]):
    return verify_audit_chain(ctx.db)


@audit_router.get("/export", summary="CSV export of the filtered audit trail; the export itself is audited (FR-AUD-005, FR-AUD-008)")
def export(ctx: Annotated[Ctx, Depends(require("audit.export"))], entity_type: str | None = None, entity_id: str | None = None, actor_user_id: uuid.UUID | None = None,
           action: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None):
    rows = ctx.db.scalars(_audit_query(ctx, entity_type, entity_id, actor_user_id, action, date_from, date_to).order_by(AuditLog.id).limit(100_000)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "occurred_at", "actor_user_id", "action", "entity_type", "entity_id", "reason", "before", "after", "entry_hash"])
    for r in rows:
        w.writerow([r.id, r.occurred_at.isoformat(), r.actor_user_id, r.action, r.entity_type, r.entity_id, r.reason, r.before_data, r.after_data, r.entry_hash])
    audit(ctx.db, ctx, "audit.export", "AuditLog", None, after={"rows": len(rows), "filters": {"entity_type": entity_type, "action": action}})
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'})
