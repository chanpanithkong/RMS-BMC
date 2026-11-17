"""Dashboard, reports and the real-time WebSocket."""
import csv
import io
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.core.database import session_factory
from app.core.dependencies import Ctx, authenticate, load_permissions, require
from app.core.exceptions import AppError, BusinessRuleError
from app.core.realtime import hub
from app.services import reports as svc
from app.services.platform import audit

router = APIRouter(tags=["reports"])
ws_router = APIRouter(tags=["realtime"])


@router.get("/dashboard", summary="Widgets permitted for your role; financial values need report.financial.view (FR-DASH-001)")
def dashboard(ctx: Annotated[Ctx, Depends(require("dashboard.view"))], date_from: date | None = None, date_to: date | None = None):
    return svc.dashboard(ctx, date_from, date_to)


@router.get("/reports", summary="Report catalogue filtered by permission")
def catalogue(ctx: Annotated[Ctx, Depends(require("notifications.view"))]):
    return svc.catalogue(ctx)


@router.get("/reports/{report_id}")
def run(report_id: str, ctx: Annotated[Ctx, Depends(require("notifications.view"))], date_from: date | None = None, date_to: date | None = None):
    return svc.run(ctx, report_id, date_from, date_to)


@router.get("/reports/{report_id}/export", summary="CSV export (audited). PDF and Excel are not built yet.")
def export(report_id: str, ctx: Annotated[Ctx, Depends(require("report.export"))], format: str = Query("csv"), date_from: date | None = None, date_to: date | None = None):
    if format != "csv":
        raise BusinessRuleError("FORMAT_NOT_AVAILABLE", "Only CSV export is available in this release.", 501)
    data = jsonable_encoder(svc.run(ctx, report_id, date_from, date_to))
    buf = io.StringIO()
    rows = data["rows"]
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    buf.write(f"\n# {data['name']} {data['from']}..{data['to']} branch {data['branch']} generated {data['generated_at']} by {data['generated_by']}. {data['note']}\n")
    audit(ctx.db, ctx, "report.export", "Report", None, after={"report": report_id, "from": data["from"], "to": data["to"], "rows": len(rows)})  # FR-RPT-024
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{report_id}.csv"'})


@ws_router.websocket("/ws")
async def websocket(ws: WebSocket, token: str):
    """Connect with ?token=<access token>. Send {"action":"subscribe","topic":"station:<branch_id>:HOT"}.

    Topics: branch:<branch_id>, tables:<branch_id>, station:<branch_id>:<code>, user:<your user id>.
    """
    db = session_factory()()
    try:
        user, _ = authenticate(db, token)
        perms, _ = load_permissions(db, user)
        branches = {str(b.id) for b in user.branches}
        uid = str(user.id)
    except AppError:
        db.close()
        await ws.close(code=4401)
        return
    db.close()
    await ws.accept()
    allowed_prefix = {"branch": "orders.view", "tables": "tables.view", "station": "kitchen.view"}
    try:
        while True:
            msg = await ws.receive_json()
            topic = str(msg.get("topic", ""))
            kind, _, rest = topic.partition(":")
            ok = (kind == "user" and rest == uid) or (kind in allowed_prefix and rest.split(":")[0] in branches and allowed_prefix[kind] in perms)
            if msg.get("action") == "subscribe" and ok:
                hub.subscribe(ws, topic)
                await ws.send_json({"type": "subscribed", "topic": topic})
            else:
                await ws.send_json({"type": "error", "code": "TOPIC_FORBIDDEN", "topic": topic})
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe_all(ws)


_ = uuid
