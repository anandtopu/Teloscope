"""Health check endpoints."""
from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def health_check():
    return {
        "status": "ok",
        "service": "agentlens-api",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe — checks critical dependencies."""
    checks: dict = {}
    overall = "ok"

    try:
        from ..storage.clickhouse import get_storage
        get_storage().client.execute("SELECT 1")
        checks["clickhouse"] = "ok"
    except Exception as exc:
        checks["clickhouse"] = f"error: {exc}"
        overall = "degraded"

    checks["api"] = "ok"
    return {"status": overall, "checks": checks}
