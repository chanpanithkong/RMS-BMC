import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import get_engine
from app.core.exceptions import register_exception_handlers
from app.core.realtime import hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await hub.start(get_settings().REDIS_URL)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=f"{s.APP_NAME} API",
        version="1.0.0",
        description="Backend for the Restaurant Management System (SRS RMS-SRS-001). Money values are decimal strings. "
        "Tax, service-charge and exchange-rate values are configurable and the seeded ones are illustrative, not verified.",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match", "X-Branch-Id", "Accept-Language"],
        expose_headers=["X-Correlation-Id"],
    )

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["system"])
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
