"""
AgentLens — Ingestion API
Receives OpenTelemetry-compatible spans and full traces from SDK clients.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..core.logging import get_logger
from ..models.trace import Span, Trace
from ..services.ingestion import get_ingestion_service

router = APIRouter()
logger = get_logger("api.ingest")


# ─── Request / Response Schemas ───────────────────────────────────

class IngestSpansRequest(BaseModel):
    spans: List[Span]


class IngestTraceRequest(BaseModel):
    trace: Trace


class IngestResponse(BaseModel):
    accepted: int
    trace_ids: List[str]


# ─── Auth Dependency ──────────────────────────────────────────────

async def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    """
    Validate the API key from the X-API-Key header.
    In production, validate against DB; here we do a basic check.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    # TODO: validate against ApiKey table in DB
    # For now accept any non-empty key (replace with real validation)
    return x_api_key


# ─── Endpoints ────────────────────────────────────────────────────

@router.post("/spans", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_spans(
    request: IngestSpansRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Ingest a batch of OTEL-compatible spans.
    Spans are validated, PII-redacted, cost-enriched, and persisted.
    """
    svc = get_ingestion_service()
    try:
        svc.ingest_spans(request.spans)
        trace_ids = list({s.trace_id for s in request.spans})
        logger.info("Spans accepted", count=len(request.spans), traces=len(trace_ids))
        return IngestResponse(accepted=len(request.spans), trace_ids=trace_ids)
    except Exception as exc:
        logger.error("Span ingestion failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/trace", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_trace(
    request: IngestTraceRequest,
    api_key: str = Depends(verify_api_key),
):
    """
    Ingest a fully-formed trace with all spans attached.
    Preferred for SDK clients that buffer and batch entire traces.
    """
    svc = get_ingestion_service()
    try:
        svc.ingest_trace(request.trace)
        logger.info("Trace accepted", trace_id=request.trace.trace_id)
        return IngestResponse(
            accepted=len(request.trace.spans),
            trace_ids=[request.trace.trace_id],
        )
    except Exception as exc:
        logger.error("Trace ingestion failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
