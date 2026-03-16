"""
AgentLens — Trace Ingestion Service
Core pipeline: receives OTEL spans → enriches → redacts PII → persists.
Also aggregates per-trace metrics and updates cost breakdowns.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from ..core.logging import get_logger
from ..models.trace import (
    Span,
    SpanKind,
    SpanStatus,
    Trace,
    TokenUsage,
)
from ..security.pii import get_redactor
from ..services.cost import get_cost_calculator
from ..storage.clickhouse import get_storage

logger = get_logger("services.ingestion")


class TraceIngestionService:
    """
    Processes incoming spans and traces through the enrichment pipeline.

    Pipeline steps:
      1. Validate inbound spans (Pydantic)
      2. Redact PII from input/output payloads
      3. Calculate LLM costs
      4. Aggregate per-trace metrics
      5. Persist to ClickHouse
    """

    def __init__(self) -> None:
        self.storage = get_storage()
        self.redactor = get_redactor()
        self.cost_calc = get_cost_calculator()

    def ingest_spans(self, spans: List[Span]) -> None:
        """
        Ingest a batch of spans.
        Spans may belong to multiple traces; groups them and persists.
        """
        if not spans:
            return

        # Step 1: PII redaction
        redacted = [self._redact_span(s) for s in spans]

        # Step 2: Cost calculation for LLM spans
        enriched = [self._enrich_costs(s) for s in redacted]

        # Step 3: Group by trace_id
        traces_map: dict[str, List[Span]] = {}
        for span in enriched:
            traces_map.setdefault(span.trace_id, []).append(span)

        # Step 4: Persist spans
        self.storage.insert_spans(enriched)
        logger.info("Spans ingested", count=len(enriched))

        # Step 5: Build and persist trace records
        for trace_id, trace_spans in traces_map.items():
            trace = self._build_trace_record(trace_id, trace_spans)
            if trace:
                self.storage.insert_trace(trace)

    def ingest_trace(self, trace: Trace) -> None:
        """Ingest a fully-formed trace object (with all spans attached)."""
        # Redact and enrich all spans
        trace.spans = [self._enrich_costs(self._redact_span(s)) for s in trace.spans]

        # Recalculate aggregated metrics
        trace = self._aggregate_trace_metrics(trace)

        self.storage.insert_spans(trace.spans)
        self.storage.insert_trace(trace)
        logger.info("Trace ingested", trace_id=trace.trace_id, spans=len(trace.spans))

    # ─── Pipeline Steps ──────────────────────────────────────────────

    def _redact_span(self, span: Span) -> Span:
        """Apply PII redaction to span payloads."""
        span_dict = span.model_dump()
        redacted_dict = self.redactor.redact_trace_payload(span_dict)
        return Span(**redacted_dict)

    def _enrich_costs(self, span: Span) -> Span:
        """Calculate cost for LLM spans."""
        if span.kind != SpanKind.LLM or not span.llm_attributes:
            return span

        llm = span.llm_attributes
        if llm.provider and llm.model and llm.token_usage:
            cost = self.cost_calc.calculate(
                provider=llm.provider.value,
                model=llm.model,
                token_usage=llm.token_usage,
            )
            llm.cost = cost
        return span

    def _build_trace_record(
        self, trace_id: str, spans: List[Span]
    ) -> Optional[Trace]:
        """Build a Trace summary record from a list of spans."""
        if not spans:
            return None

        # Find root span (no parent)
        root = next((s for s in spans if s.parent_span_id is None), spans[0])

        # Determine overall status
        has_error = any(s.status == SpanStatus.ERROR for s in spans)
        status = SpanStatus.ERROR if has_error else SpanStatus.OK

        # Aggregate token usage and cost
        total_prompt = sum(
            (s.llm_attributes.token_usage.prompt_tokens
             if s.llm_attributes and s.llm_attributes.token_usage else 0)
            for s in spans
        )
        total_completion = sum(
            (s.llm_attributes.token_usage.completion_tokens
             if s.llm_attributes and s.llm_attributes.token_usage else 0)
            for s in spans
        )
        total_cost = sum(
            (s.llm_attributes.cost.total_cost_usd
             if s.llm_attributes and s.llm_attributes.cost else 0.0)
            for s in spans
        )

        # Compute duration from span times
        start_times = [s.start_time for s in spans if s.start_time]
        end_times   = [s.end_time   for s in spans if s.end_time]
        start_time  = min(start_times) if start_times else datetime.utcnow()
        end_time    = max(end_times)   if end_times   else None
        duration_ms = (
            (end_time - start_time).total_seconds() * 1000
            if end_time else None
        )

        return Trace(
            trace_id=trace_id,
            root_span_id=root.span_id,
            name=root.name,
            agent_name=root.agent_id or root.name,
            framework=root.framework,
            environment=root.environment,
            org_id=root.org_id,
            project_id=root.project_id,
            session_id=root.session_id,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=status,
            total_spans=len(spans),
            llm_call_count=sum(1 for s in spans if s.kind == SpanKind.LLM),
            tool_call_count=sum(1 for s in spans if s.kind == SpanKind.TOOL),
            error_count=sum(1 for s in spans if s.status == SpanStatus.ERROR),
            token_usage=TokenUsage(
                prompt_tokens=total_prompt,
                completion_tokens=total_completion,
                total_tokens=total_prompt + total_completion,
            ),
            total_cost_usd=round(total_cost, 8),
            spans=spans,
        )

    def _aggregate_trace_metrics(self, trace: Trace) -> Trace:
        """Recalculate aggregated fields on a Trace from its spans."""
        spans = trace.spans
        trace.total_spans    = len(spans)
        trace.llm_call_count = sum(1 for s in spans if s.kind == SpanKind.LLM)
        trace.tool_call_count= sum(1 for s in spans if s.kind == SpanKind.TOOL)
        trace.error_count    = sum(1 for s in spans if s.status == SpanStatus.ERROR)

        total_prompt = sum(
            (s.llm_attributes.token_usage.prompt_tokens
             if s.llm_attributes and s.llm_attributes.token_usage else 0)
            for s in spans
        )
        total_completion = sum(
            (s.llm_attributes.token_usage.completion_tokens
             if s.llm_attributes and s.llm_attributes.token_usage else 0)
            for s in spans
        )
        trace.token_usage = TokenUsage(
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            total_tokens=total_prompt + total_completion,
        )
        trace.total_cost_usd = round(
            sum(
                (s.llm_attributes.cost.total_cost_usd
                 if s.llm_attributes and s.llm_attributes.cost else 0.0)
                for s in spans
            ),
            8,
        )
        if any(s.status == SpanStatus.ERROR for s in spans):
            trace.status = SpanStatus.ERROR
        return trace


# ─── Singleton ────────────────────────────────────────────────────────────────

_service: Optional[TraceIngestionService] = None


def get_ingestion_service() -> TraceIngestionService:
    global _service
    if _service is None:
        _service = TraceIngestionService()
    return _service
