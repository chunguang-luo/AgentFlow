import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.commit()

    logger.info(
        "AgentFlow backend started",
        extra={"environment": settings.environment, "database": str(settings.db_path)},
    )
    yield
    dispose_engine()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: dict[str, Any]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0a0",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    install_error_handlers(app)

    def health_payload(database_status: str = "ok") -> HealthResponse:
        return HealthResponse(
            status="ok" if database_status in {"ok", "not_checked"} else "degraded",
            service=settings.app_name,
            version=app.version,
            environment=settings.environment,
            database={"status": database_status, "engine": "sqlite"},
        )

    @app.get("/healthz", tags=["system"])
    def liveness() -> HealthResponse:
        return health_payload("not_checked")

    @app.get("/readyz", tags=["system"])
    def readiness() -> HealthResponse:
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            logger.exception("Database readiness check failed")
            return health_payload("unavailable")
        return health_payload()

    @app.get(f"{settings.api_prefix}/health", tags=["system"])
    def api_health() -> HealthResponse:
        return readiness()

    return app


settings = get_settings()
app = create_app()
