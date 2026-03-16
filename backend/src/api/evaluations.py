"""AgentLens — Evaluations API"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..core.logging import get_logger
from ..evaluation.engine import get_eval_engine
from ..models.trace import EvalResult

router = APIRouter()
logger = get_logger("api.evaluations")

# In-memory result store (replace with ClickHouse in production)
_results: Dict[str, EvalResult] = {}


class RunEvalRequest(BaseModel):
    trace_id: str
    org_id: str
    project_id: str
    dimensions: Optional[List[str]] = None
    judge_model: Optional[str] = None
    context: Optional[str] = None


@router.get("/templates")
async def list_templates() -> Dict[str, Any]:
    """List all available evaluation dimension templates."""
    engine = get_eval_engine()
    return {"templates": engine.list_templates()}


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def run_evaluation(req: RunEvalRequest) -> Dict[str, Any]:
    """
    Trigger an LLM-as-judge evaluation for a trace.
    The trace is fetched from storage; results are persisted.
    """
    from ..storage.clickhouse import get_storage
    from ..services.ingestion import get_ingestion_service
    from ..models.trace import Trace, SpanStatus, FrameworkType, TokenUsage
    from datetime import datetime

    storage = get_storage()
    engine = get_eval_engine()

    # Fetch trace
    trace_row = storage.get_trace_by_id(req.trace_id, req.org_id)
    if not trace_row:
        raise HTTPException(status_code=404, detail=f"Trace {req.trace_id} not found")

    # Build minimal Trace object for evaluation
    # (in production, deserialize fully from ClickHouse)
    from ..api.traces import _TRACE_COLUMNS, _SPAN_COLUMNS
    trace_dict = dict(zip(_TRACE_COLUMNS, trace_row)) if isinstance(trace_row, (list, tuple)) else trace_row

    span_rows = storage.get_spans_for_trace(req.trace_id, req.org_id)

    # Reconstruct a lightweight Trace for the eval engine
    trace = Trace(
        trace_id=req.trace_id,
        name=trace_dict.get("name", "unknown"),
        agent_name=trace_dict.get("agent_name", "unknown"),
        framework=FrameworkType(trace_dict.get("framework", "custom")),
        environment=trace_dict.get("environment", "production"),
        org_id=req.org_id,
        project_id=req.project_id,
        start_time=trace_dict.get("start_time", datetime.utcnow()),
        status=SpanStatus(trace_dict.get("status", "UNSET")),
        token_usage=TokenUsage(),
    )

    try:
        result = engine.evaluate_trace(
            trace=trace,
            dimensions=req.dimensions,
            judge_model=req.judge_model,
            context=req.context,
        )
        _results[result.eval_id] = result
        logger.info("Evaluation completed", eval_id=result.eval_id, verdict=result.overall_verdict)
        return {
            "eval_id": result.eval_id,
            "overall_score": result.overall_score,
            "overall_verdict": result.overall_verdict,
            "dimensions": [d.model_dump() for d in result.dimensions],
            "cost_usd": result.cost_usd,
        }
    except Exception as exc:
        logger.error("Evaluation failed", trace_id=req.trace_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("")
async def list_evaluations(
    org_id: str = Query(...),
    project_id: str = Query(...),
    trace_id: Optional[str] = Query(None),
    verdict: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    results = [r for r in _results.values()
               if r.org_id == org_id and r.project_id == project_id]
    if trace_id:
        results = [r for r in results if r.trace_id == trace_id]
    if verdict:
        results = [r for r in results if r.overall_verdict.value == verdict]
    return {
        "evaluations": [r.model_dump() for r in results[-limit:]],
        "total": len(results),
    }


@router.get("/{eval_id}")
async def get_evaluation(eval_id: str) -> Dict[str, Any]:
    result = _results.get(eval_id)
    if not result:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return result.model_dump()
