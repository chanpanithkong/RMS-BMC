"""Problem-details style errors (SRS §13.1)."""
import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("rms")


class AppError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, status_code: int | None = None, details: list[dict] | None = None, **extra: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code:
            self.status_code = status_code
        self.details = details or []
        self.extra = extra


class NotFound(AppError):
    def __init__(self, entity: str = "Record"):
        super().__init__("NOT_FOUND", f"{entity} not found.", 404)


class Conflict(AppError):
    status_code = 409


class Forbidden(AppError):
    def __init__(self, message: str = "You don't have permission to do this.", code: str = "FORBIDDEN"):
        super().__init__(code, message, 403)


class Unauthorized(AppError):
    def __init__(self, message: str = "Sign in to continue.", code: str = "UNAUTHORIZED"):
        super().__init__(code, message, 401)


class BusinessRuleError(AppError):
    status_code = 422


def _body(code: str, message: str, request: Request, details: list | None = None, **extra: Any) -> dict:
    cid = getattr(request.state, "correlation_id", None) or str(uuid.uuid4())
    return {"error": {"code": code, "message": message, "details": details or [], **extra, "correlation_id": cid}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, request, exc.details, **exc.extra), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "issue": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("VALIDATION_ERROR", "Some fields are invalid.", request, details), status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        log.info("integrity error on %s", constraint)
        return JSONResponse(_body("CONFLICT", "This change conflicts with existing data.", request, [{"constraint": constraint}] if constraint else []), status_code=409)

    @app.exception_handler(StaleDataError)
    async def stale(request: Request, exc: StaleDataError):
        return JSONResponse(_body("VERSION_CONFLICT", "This record was changed by someone else. Reload and try again.", request), status_code=409)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 429: "RATE_LIMITED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code, str(exc.detail), request), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(_body("INTERNAL_ERROR", "Something went wrong. Quote the reference when reporting it.", request), status_code=500)
