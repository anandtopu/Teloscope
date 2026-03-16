"""AgentLens — Metrics API"""
from __future__ import annotations
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query
from ..storage.clickhouse import get_storage

router = APIRouter()


@router.get("/summary")
async def metrics_summary(
    org_id: str = Query(...),
    project_id: str = Query(...),
    window_minutes: int = Query(60, ge=5, le=10080),
    agent_name: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Returns aggregated performance metrics for the specified time window.
    Includes: invocation count, error rate, latency percentiles, token usage, cost.
    """
    storage = get_storage()
    summary = storage.get_metrics_summary(
        org_id=org_id,
        project_id=project_id,
        window_minutes=window_minutes,
        agent_name=agent_name,
    )
    return {
        "org_id": org_id,
        "project_id": project_id,
        "window_minutes": window_minutes,
        "agent_name": agent_name,
        "metrics": dict(summary) if summary else {},
    }


@router.get("/errors")
async def error_breakdown(
    org_id: str = Query(...),
    project_id: str = Query(...),
    window_minutes: int = Query(60),
) -> Dict[str, Any]:
    """Error breakdown by type for the time window."""
    storage = get_storage()
    rows = storage.get_error_breakdown(org_id, project_id, window_minutes)
    return {"errors": [{"error_type": r[0], "count": r[1], "pct": r[2]} for r in rows]}


@router.get("/cost")
async def cost_by_model(
    org_id: str = Query(...),
    project_id: str = Query(...),
    window_minutes: int = Query(1440),
) -> Dict[str, Any]:
    """LLM cost breakdown by provider and model."""
    storage = get_storage()
    rows = storage.get_cost_by_model(org_id, project_id, window_minutes)
    return {
        "window_minutes": window_minutes,
        "breakdown": [
            {
                "provider": r[0], "model": r[1],
                "call_count": r[2], "total_tokens": r[3], "cost_usd": r[4],
            }
            for r in rows
        ],
    }
