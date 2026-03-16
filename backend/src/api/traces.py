"""
AgentLens — Traces API
Query, list, and inspect agent traces and their spans.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core.logging import get_logger
from ..models.trace import SpanStatus
from ..storage.clickhouse import get_storage

router = APIRouter()
logger = get_logger("api.traces")


class TraceListResponse(BaseModel):
    traces: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class TraceDetailResponse(BaseModel):
    trace: Dict[str, Any]
    spans: List[Dict[str, Any]]


@router.get("", response_model=TraceListResponse)
async def list_traces(
    org_id: str = Query(..., description="Organization ID"),
    project_id: str = Query(..., description="Project ID"),
    agent_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="OK | ERROR"),
    environment: Optional[str] = Query(None, description="production | staging | development"),
    start_after: Optional[datetime] = Query(None),
    end_before: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List traces with optional filters.
    Returns paginated results sorted by start_time descending.
    """
    storage = get_storage()
    try:
        status_enum = SpanStatus(status) if status else None
        rows = storage.get_traces(
            org_id=org_id,
            project_id=project_id,
            agent_name=agent_name,
            status=status_enum,
            environment=environment,
            start_after=start_after,
            end_before=end_before,
            limit=limit,
            offset=offset,
        )
        # ClickHouse returns tuples — convert to dicts using column names
        traces = [dict(zip(_TRACE_COLUMNS, row)) for row in rows]
        return TraceListResponse(
            traces=traces,
            total=len(traces),
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.error("Failed to list traces", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(
    trace_id: str,
    org_id: str = Query(...),
):
    """Get a single trace with all its spans."""
    storage = get_storage()
    trace_row = storage.get_trace_by_id(trace_id=trace_id, org_id=org_id)
    if not trace_row:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    span_rows = storage.get_spans_for_trace(trace_id=trace_id, org_id=org_id)
    trace = dict(zip(_TRACE_COLUMNS, trace_row)) if isinstance(trace_row, (list, tuple)) else trace_row
    spans = [dict(zip(_SPAN_COLUMNS, row)) for row in span_rows]

    return TraceDetailResponse(trace=trace, spans=spans)


@router.get("/{trace_id}/spans")
async def get_trace_spans(
    trace_id: str,
    org_id: str = Query(...),
) -> Dict[str, Any]:
    """Get only the spans for a trace (lightweight)."""
    storage = get_storage()
    span_rows = storage.get_spans_for_trace(trace_id=trace_id, org_id=org_id)
    spans = [dict(zip(_SPAN_COLUMNS, row)) for row in span_rows]
    return {"trace_id": trace_id, "spans": spans, "count": len(spans)}


# Column name lists for ClickHouse tuple → dict conversion
_TRACE_COLUMNS = [
    "trace_id", "root_span_id", "name", "agent_name", "agent_version",
    "framework", "environment", "org_id", "project_id", "session_id",
    "user_id", "start_time", "end_time", "duration_ms", "status",
    "total_spans", "llm_call_count", "tool_call_count", "error_count",
    "prompt_tokens", "completion_tokens", "total_tokens", "total_cost_usd",
    "tags_json", "metadata_json", "ingested_at",
]

_SPAN_COLUMNS = [
    "span_id", "trace_id", "parent_span_id", "name", "kind", "status",
    "start_time", "end_time", "duration_ms", "agent_id", "session_id",
    "org_id", "project_id", "framework", "environment", "sdk_version",
    "input_json", "output_json", "error", "error_type",
    "llm_provider", "llm_model", "prompt_tokens", "completion_tokens",
    "total_tokens", "cost_usd", "attributes_json", "events_json", "ingested_at",
]
