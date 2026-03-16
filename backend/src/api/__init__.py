"""
AgentLens — API Routers
All REST endpoints for the platform.
"""
# ─── health.py ────────────────────────────────────────────────────────────────
# Save as: backend/src/api/health.py
HEALTH_ROUTER = '''
from fastapi import APIRouter
from datetime import datetime

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
    checks = {}
    overall = "ok"

    # ClickHouse
    try:
        from ..storage.clickhouse import get_storage
        get_storage().client.execute("SELECT 1")
        checks["clickhouse"] = "ok"
    except Exception as e:
        checks["clickhouse"] = f"error: {e}"
        overall = "degraded"

    # Redis (optional check)
    checks["api"] = "ok"

    return {"status": overall, "checks": checks}
'''

# Write the actual files
import os

api_dir = os.path.dirname(os.path.abspath(__file__))
