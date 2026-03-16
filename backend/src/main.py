"""
AgentLens — FastAPI Application
Main entry point: registers all routers, middleware, and startup events.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .core.config import get_settings
from .core.logging import configure_logging, get_logger

# ─── Initialize logging before anything else ─────────────────────
configure_logging()
logger = get_logger("app")

# ─── Prometheus metrics ──────────────────────────────────────────
REQUEST_COUNT = Counter(
    "agentlens_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "agentlens_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
)
SPANS_INGESTED = Counter(
    "agentlens_spans_ingested_total",
    "Total spans ingested",
    ["org_id", "framework"],
)


# ─── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    settings = get_settings()
    logger.info(
        "AgentLens starting",
        env=settings.env,
        version="1.0.0",
    )
    # Initialize ClickHouse schema
    try:
        from .storage.clickhouse import get_storage
        get_storage().initialize_schema()
        logger.info("ClickHouse schema ready")
    except Exception as exc:
        logger.warning("ClickHouse not available at startup", error=str(exc))

    yield

    logger.info("AgentLens shutting down")


# ─── App Factory ──────────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AgentLens API",
        description="AI Agent Observability Platform — REST API",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging & metrics middleware ──────────────────────
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start

        path = request.url.path
        method = request.method
        status = str(response.status_code)

        REQUEST_COUNT.labels(method=method, path=path, status_code=status).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(elapsed)

        logger.debug(
            "HTTP request",
            method=method,
            path=path,
            status=status,
            duration_ms=round(elapsed * 1000, 1),
        )
        return response

    # ── Routes ────────────────────────────────────────────────────
    from .api.ingest import router as ingest_router
    from .api.traces import router as traces_router
    from .api.metrics import router as metrics_router
    from .api.alerts import router as alerts_router
    from .api.evaluations import router as evals_router
    from .api.health import router as health_router

    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(ingest_router, prefix="/api/v1/ingest", tags=["Ingestion"])
    app.include_router(traces_router, prefix="/api/v1/traces", tags=["Traces"])
    app.include_router(metrics_router, prefix="/api/v1/metrics", tags=["Metrics"])
    app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["Alerts"])
    app.include_router(evals_router,  prefix="/api/v1/evaluations", tags=["Evaluations"])

    # ── Prometheus metrics endpoint ───────────────────────────────
    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    return app


app = create_app()
