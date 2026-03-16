"""
AgentLens — ClickHouse Storage Adapter
Handles trace and span persistence using ClickHouse columnar storage.
Schema is designed for high-throughput ingest and fast analytics queries.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from clickhouse_driver import Client as SyncClient  # type: ignore

from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.trace import Span, SpanStatus, Trace

logger = get_logger("storage.clickhouse")


# ─── DDL: Table Schemas ───────────────────────────────────────────────────────

CREATE_DATABASE = "CREATE DATABASE IF NOT EXISTS {db}"

CREATE_SPANS_TABLE = """
CREATE TABLE IF NOT EXISTS {db}.spans (
    span_id          String,
    trace_id         String,
    parent_span_id   Nullable(String),
    name             String,
    kind             LowCardinality(String),
    status           LowCardinality(String),
    start_time       DateTime64(3, 'UTC'),
    end_time         Nullable(DateTime64(3, 'UTC')),
    duration_ms      Nullable(Float64),
    agent_id         Nullable(String),
    session_id       Nullable(String),
    org_id           String,
    project_id       String,
    framework        LowCardinality(String),
    environment      LowCardinality(String),
    sdk_version      Nullable(String),
    input_json       Nullable(String),
    output_json      Nullable(String),
    error            Nullable(String),
    error_type       Nullable(String),
    llm_provider     Nullable(LowCardinality(String)),
    llm_model        Nullable(String),
    prompt_tokens    UInt32,
    completion_tokens UInt32,
    total_tokens     UInt32,
    cost_usd         Float64,
    attributes_json  String,
    events_json      String,
    ingested_at      DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(start_time)
ORDER BY (org_id, project_id, trace_id, start_time)
TTL start_time + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
"""

CREATE_TRACES_TABLE = """
CREATE TABLE IF NOT EXISTS {db}.traces (
    trace_id         String,
    root_span_id     Nullable(String),
    name             String,
    agent_name       String,
    agent_version    Nullable(String),
    framework        LowCardinality(String),
    environment      LowCardinality(String),
    org_id           String,
    project_id       String,
    session_id       Nullable(String),
    user_id          Nullable(String),
    start_time       DateTime64(3, 'UTC'),
    end_time         Nullable(DateTime64(3, 'UTC')),
    duration_ms      Nullable(Float64),
    status           LowCardinality(String),
    total_spans      UInt16,
    llm_call_count   UInt16,
    tool_call_count  UInt16,
    error_count      UInt16,
    prompt_tokens    UInt32,
    completion_tokens UInt32,
    total_tokens     UInt32,
    total_cost_usd   Float64,
    tags_json        String,
    metadata_json    String,
    ingested_at      DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(start_time)
ORDER BY (org_id, project_id, start_time, trace_id)
TTL start_time + INTERVAL 90 DAY
SETTINGS index_granularity = 8192
"""

CREATE_EVALS_TABLE = """
CREATE TABLE IF NOT EXISTS {db}.eval_results (
    eval_id          String,
    trace_id         String,
    span_id          Nullable(String),
    org_id           String,
    project_id       String,
    judge_model      LowCardinality(String),
    eval_template    LowCardinality(String),
    overall_score    Nullable(Float32),
    overall_verdict  LowCardinality(String),
    dimensions_json  String,
    latency_ms       Nullable(Float64),
    cost_usd         Nullable(Float64),
    evaluated_at     DateTime64(3, 'UTC')
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(evaluated_at)
ORDER BY (org_id, project_id, trace_id, evaluated_at)
SETTINGS index_granularity = 8192
"""

CREATE_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS {db}.alerts (
    alert_id         String,
    rule_id          String,
    org_id           String,
    severity         LowCardinality(String),
    title            String,
    description      String,
    metric           String,
    current_value    Float64,
    threshold        Float64,
    agent_name       Nullable(String),
    fired_at         DateTime64(3, 'UTC'),
    resolved_at      Nullable(DateTime64(3, 'UTC')),
    acknowledged     UInt8,
    acknowledged_by  Nullable(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(fired_at)
ORDER BY (org_id, fired_at, alert_id)
SETTINGS index_granularity = 8192
"""


class ClickHouseStorage:
    """
    Synchronous ClickHouse storage adapter.
    For production, use an async wrapper or connection pool.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Optional[SyncClient] = None

    @property
    def client(self) -> SyncClient:
        if self._client is None:
            self._client = SyncClient(
                host=self.settings.clickhouse_host,
                port=self.settings.clickhouse_port,
                database=self.settings.clickhouse_db,
                user=self.settings.clickhouse_user,
                password=self.settings.clickhouse_password,
                connect_timeout=5,
                send_receive_timeout=30,
                settings={"use_numpy": False},
            )
        return self._client

    def initialize_schema(self) -> None:
        """Create database and tables if they don't exist."""
        db = self.settings.clickhouse_db
        self.client.execute(CREATE_DATABASE.format(db=db))
        self.client.execute(CREATE_SPANS_TABLE.format(db=db))
        self.client.execute(CREATE_TRACES_TABLE.format(db=db))
        self.client.execute(CREATE_EVALS_TABLE.format(db=db))
        self.client.execute(CREATE_ALERTS_TABLE.format(db=db))
        logger.info("ClickHouse schema initialized", database=db)

    # ─── Span Operations ─────────────────────────────────────────────

    def insert_spans(self, spans: List[Span]) -> None:
        """Batch-insert a list of spans."""
        rows = [self._span_to_row(s) for s in spans]
        self.client.execute(
            f"INSERT INTO {self.settings.clickhouse_db}.spans VALUES",
            rows,
        )
        logger.debug("Inserted spans", count=len(spans))

    def get_spans_for_trace(self, trace_id: str, org_id: str) -> List[Any]:
        result = self.client.execute(
            f"""
            SELECT *
            FROM {self.settings.clickhouse_db}.spans
            WHERE trace_id = %(trace_id)s AND org_id = %(org_id)s
            ORDER BY start_time ASC
            """,
            {"trace_id": trace_id, "org_id": org_id},
        )
        return result

    # ─── Trace Operations ────────────────────────────────────────────

    def insert_trace(self, trace: Trace) -> None:
        row = self._trace_to_row(trace)
        self.client.execute(
            f"INSERT INTO {self.settings.clickhouse_db}.traces VALUES",
            [row],
        )

    def get_traces(
        self,
        org_id: str,
        project_id: str,
        agent_name: Optional[str] = None,
        status: Optional[SpanStatus] = None,
        environment: Optional[str] = None,
        start_after: Optional[datetime] = None,
        end_before: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Any]:
        conditions = ["org_id = %(org_id)s", "project_id = %(project_id)s"]
        params: Dict[str, Any] = {"org_id": org_id, "project_id": project_id}

        if agent_name:
            conditions.append("agent_name = %(agent_name)s")
            params["agent_name"] = agent_name
        if status:
            conditions.append("status = %(status)s")
            params["status"] = status.value
        if environment:
            conditions.append("environment = %(environment)s")
            params["environment"] = environment
        if start_after:
            conditions.append("start_time >= %(start_after)s")
            params["start_after"] = start_after
        if end_before:
            conditions.append("start_time <= %(end_before)s")
            params["end_before"] = end_before

        where = " AND ".join(conditions)
        query = f"""
            SELECT *
            FROM {self.settings.clickhouse_db}.traces
            WHERE {where}
            ORDER BY start_time DESC
            LIMIT %(limit)s OFFSET %(offset)s
        """
        params.update({"limit": limit, "offset": offset})
        return self.client.execute(query, params)

    def get_trace_by_id(self, trace_id: str, org_id: str) -> Optional[Dict[str, Any]]:
        result = self.client.execute(
            f"""
            SELECT *
            FROM {self.settings.clickhouse_db}.traces
            WHERE trace_id = %(trace_id)s AND org_id = %(org_id)s
            LIMIT 1
            """,
            {"trace_id": trace_id, "org_id": org_id},
        )
        return result[0] if result else None

    # ─── Analytics Queries ───────────────────────────────────────────

    def get_metrics_summary(
        self,
        org_id: str,
        project_id: str,
        window_minutes: int = 60,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        agent_filter = "AND agent_name = %(agent_name)s" if agent_name else ""
        params: Dict[str, Any] = {
            "org_id": org_id,
            "project_id": project_id,
            "window_minutes": window_minutes,
        }
        if agent_name:
            params["agent_name"] = agent_name

        result = self.client.execute(
            f"""
            SELECT
                count()                                         AS invocation_count,
                countIf(status = 'OK')                         AS success_count,
                countIf(status = 'ERROR')                      AS error_count,
                round(countIf(status = 'ERROR') / count(), 4)  AS error_rate,
                round(avg(duration_ms), 2)                     AS avg_latency_ms,
                round(quantile(0.50)(duration_ms), 2)          AS p50_latency_ms,
                round(quantile(0.95)(duration_ms), 2)          AS p95_latency_ms,
                round(quantile(0.99)(duration_ms), 2)          AS p99_latency_ms,
                sum(total_tokens)                              AS total_tokens,
                round(sum(total_cost_usd), 6)                  AS total_cost_usd,
                round(avg(total_cost_usd), 6)                  AS avg_cost_per_call
            FROM {self.settings.clickhouse_db}.traces
            WHERE
                org_id      = %(org_id)s
                AND project_id  = %(project_id)s
                AND start_time >= now() - INTERVAL %(window_minutes)s MINUTE
                {agent_filter}
            """,
            params,
        )
        return result[0] if result else {}

    def get_error_breakdown(
        self,
        org_id: str,
        project_id: str,
        window_minutes: int = 60,
    ) -> List[Any]:
        result = self.client.execute(
            f"""
            SELECT
                error_type,
                count()  AS count,
                round(count() / sum(count()) OVER (), 4) AS pct
            FROM {self.settings.clickhouse_db}.spans
            WHERE
                org_id      = %(org_id)s
                AND project_id  = %(project_id)s
                AND status      = 'ERROR'
                AND start_time >= now() - INTERVAL %(window_minutes)s MINUTE
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 20
            """,
            {"org_id": org_id, "project_id": project_id, "window_minutes": window_minutes},
        )
        return result

    def get_cost_by_model(
        self,
        org_id: str,
        project_id: str,
        window_minutes: int = 1440,  # 24h default
    ) -> List[Any]:
        return self.client.execute(
            f"""
            SELECT
                llm_provider,
                llm_model,
                count()             AS call_count,
                sum(total_tokens)   AS total_tokens,
                round(sum(cost_usd), 6) AS cost_usd
            FROM {self.settings.clickhouse_db}.spans
            WHERE
                org_id      = %(org_id)s
                AND project_id  = %(project_id)s
                AND kind        = 'llm'
                AND start_time >= now() - INTERVAL %(window_minutes)s MINUTE
            GROUP BY llm_provider, llm_model
            ORDER BY cost_usd DESC
            """,
            {"org_id": org_id, "project_id": project_id, "window_minutes": window_minutes},
        )

    # ─── Private Helpers ────────────────────────────────────────────

    @staticmethod
    def _span_to_row(span: Span) -> tuple:
        llm = span.llm_attributes
        tool = span.tool_attributes
        return (
            span.span_id,
            span.trace_id,
            span.parent_span_id,
            span.name,
            span.kind.value,
            span.status.value,
            span.start_time,
            span.end_time,
            span.duration_ms,
            span.agent_id,
            span.session_id,
            span.org_id,
            span.project_id,
            span.framework.value,
            span.environment,
            span.sdk_version,
            json.dumps(span.input) if span.input is not None else None,
            json.dumps(span.output) if span.output is not None else None,
            span.error,
            span.error_type,
            llm.provider.value if llm and llm.provider else None,
            llm.model if llm else None,
            llm.token_usage.prompt_tokens if llm and llm.token_usage else 0,
            llm.token_usage.completion_tokens if llm and llm.token_usage else 0,
            llm.token_usage.total_tokens if llm and llm.token_usage else 0,
            llm.cost.total_cost_usd if llm and llm.cost else 0.0,
            json.dumps(span.attributes),
            json.dumps([e.model_dump() for e in span.events]),
        )

    @staticmethod
    def _trace_to_row(trace: Trace) -> tuple:
        return (
            trace.trace_id,
            trace.root_span_id,
            trace.name,
            trace.agent_name,
            trace.agent_version,
            trace.framework.value,
            trace.environment,
            trace.org_id,
            trace.project_id,
            trace.session_id,
            trace.user_id,
            trace.start_time,
            trace.end_time,
            trace.duration_ms,
            trace.status.value,
            trace.total_spans,
            trace.llm_call_count,
            trace.tool_call_count,
            trace.error_count,
            trace.token_usage.prompt_tokens,
            trace.token_usage.completion_tokens,
            trace.token_usage.total_tokens,
            trace.total_cost_usd,
            json.dumps(trace.tags),
            json.dumps(trace.metadata),
        )


# ─── Singleton ────────────────────────────────────────────────────────────────

_storage: Optional[ClickHouseStorage] = None


def get_storage() -> ClickHouseStorage:
    global _storage
    if _storage is None:
        _storage = ClickHouseStorage()
    return _storage
