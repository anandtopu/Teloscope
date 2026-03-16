"""
AgentLens — Core Data Models
Defines the canonical data structures for traces, spans, events, and metrics.
Aligned with OpenTelemetry GenAI semantic conventions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ─── Enumerations ────────────────────────────────────────────────────────────

class SpanKind(str, Enum):
    AGENT       = "agent"       # Top-level agent invocation
    LLM         = "llm"         # LLM call (gen.ai.client.operation)
    TOOL        = "tool"        # Tool / function call
    RETRIEVAL   = "retrieval"   # Vector / document retrieval
    MEMORY      = "memory"      # Memory read/write
    CHAIN       = "chain"       # Orchestration chain step
    GUARDRAIL   = "guardrail"   # Safety / guardrail check


class SpanStatus(str, Enum):
    UNSET   = "UNSET"
    OK      = "OK"
    ERROR   = "ERROR"


class FrameworkType(str, Enum):
    LANGCHAIN       = "langchain"
    CREWAI          = "crewai"
    AUTOGEN         = "autogen"
    OPENAI_AGENTS   = "openai_agents"
    SEMANTIC_KERNEL = "semantic_kernel"
    LLAMAINDEX      = "llamaindex"
    HAYSTACK        = "haystack"
    BEDROCK_AGENTS  = "bedrock_agents"
    CUSTOM          = "custom"


class LLMProvider(str, Enum):
    OPENAI          = "openai"
    ANTHROPIC       = "anthropic"
    GOOGLE          = "google"
    MISTRAL         = "mistral"
    BEDROCK         = "bedrock"
    AZURE_OPENAI    = "azure_openai"
    COHERE          = "cohere"
    OLLAMA          = "ollama"
    CUSTOM          = "custom"


class AlertSeverity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    ERROR    = "error"
    CRITICAL = "critical"


class EvalVerdict(str, Enum):
    PASS     = "pass"
    FAIL     = "fail"
    PARTIAL  = "partial"
    SKIP     = "skip"


# ─── Token & Cost Models ─────────────────────────────────────────────────────

class TokenUsage(BaseModel):
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0


class CostBreakdown(BaseModel):
    prompt_cost_usd:     float = 0.0
    completion_cost_usd: float = 0.0
    total_cost_usd:      float = 0.0
    currency:            str   = "USD"


# ─── Span / Trace Models ──────────────────────────────────────────────────────

class SpanEvent(BaseModel):
    """An event recorded within a span (e.g., a tool call result)."""
    name:       str
    timestamp:  datetime
    attributes: Dict[str, Any] = Field(default_factory=dict)


class LLMAttributes(BaseModel):
    """OpenTelemetry GenAI semantic attributes for LLM spans."""
    provider:           Optional[LLMProvider] = None
    model:              Optional[str] = None
    request_model:      Optional[str] = None
    response_model:     Optional[str] = None
    system:             Optional[str] = None          # gen.ai.system
    operation:          Optional[str] = None          # gen.ai.operation.name
    token_usage:        Optional[TokenUsage] = None
    cost:               Optional[CostBreakdown] = None
    temperature:        Optional[float] = None
    max_tokens:         Optional[int] = None
    top_p:              Optional[float] = None
    streaming:          bool = False


class ToolAttributes(BaseModel):
    """Attributes for tool/function call spans."""
    tool_name:          Optional[str] = None
    tool_description:   Optional[str] = None
    input_schema:       Optional[Dict[str, Any]] = None
    is_mcp_tool:        bool = False
    mcp_server:         Optional[str] = None


class Span(BaseModel):
    """
    A single unit of work within an agent trace.
    Maps to an OpenTelemetry Span.
    """
    span_id:        str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id:       str
    parent_span_id: Optional[str] = None
    name:           str
    kind:           SpanKind
    status:         SpanStatus = SpanStatus.UNSET
    start_time:     datetime
    end_time:       Optional[datetime] = None
    duration_ms:    Optional[float] = None

    # Context
    agent_id:       Optional[str] = None
    session_id:     Optional[str] = None
    org_id:         str
    project_id:     str
    framework:      FrameworkType = FrameworkType.CUSTOM
    environment:    str = "production"
    sdk_version:    Optional[str] = None

    # Payload (redacted in transit if PII enabled)
    input:          Optional[Any] = None
    output:         Optional[Any] = None
    error:          Optional[str] = None
    error_type:     Optional[str] = None

    # Type-specific attributes
    llm_attributes:  Optional[LLMAttributes] = None
    tool_attributes: Optional[ToolAttributes] = None

    # Generic attributes bag (OTEL compatible)
    attributes:     Dict[str, Any] = Field(default_factory=dict)
    events:         List[SpanEvent] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def compute_duration(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("duration_ms") is None and data.get("start_time") and data.get("end_time"):
                delta = data["end_time"] - data["start_time"]
                data["duration_ms"] = delta.total_seconds() * 1000
        return data


class Trace(BaseModel):
    """
    A complete agent execution — a tree of spans.
    """
    trace_id:       str = Field(default_factory=lambda: str(uuid.uuid4()))
    root_span_id:   Optional[str] = None
    name:           str
    agent_name:     str
    agent_version:  Optional[str] = None
    framework:      FrameworkType = FrameworkType.CUSTOM
    environment:    str = "production"
    org_id:         str
    project_id:     str
    session_id:     Optional[str] = None
    user_id:        Optional[str] = None

    start_time:     datetime
    end_time:       Optional[datetime] = None
    duration_ms:    Optional[float] = None
    status:         SpanStatus = SpanStatus.UNSET

    # Aggregated metrics (computed on ingestion)
    total_spans:    int = 0
    llm_call_count: int = 0
    tool_call_count:int = 0
    error_count:    int = 0
    token_usage:    TokenUsage = Field(default_factory=TokenUsage)
    total_cost_usd: float = 0.0

    spans:          List[Span] = Field(default_factory=list)
    tags:           Dict[str, str] = Field(default_factory=dict)
    metadata:       Dict[str, Any] = Field(default_factory=dict)


# ─── Session Models ───────────────────────────────────────────────────────────

class Session(BaseModel):
    """
    Groups multiple traces into a logical user interaction session.
    """
    session_id:         str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id:             str
    project_id:         str
    user_id:            Optional[str] = None
    agent_name:         str

    start_time:         datetime
    end_time:           Optional[datetime] = None
    last_activity:      Optional[datetime] = None

    turn_count:         int = 0
    trace_count:        int = 0
    total_tokens:       int = 0
    total_cost_usd:     float = 0.0
    resolution_status:  Optional[str] = None   # resolved | escalated | abandoned

    trace_ids:          List[str] = Field(default_factory=list)
    metadata:           Dict[str, Any] = Field(default_factory=dict)


# ─── Metrics Models ───────────────────────────────────────────────────────────

class AgentMetricsSummary(BaseModel):
    """Aggregated metrics for an agent over a time window."""
    agent_name:         str
    org_id:             str
    project_id:         str
    window_start:       datetime
    window_end:         datetime

    invocation_count:   int = 0
    success_count:      int = 0
    error_count:        int = 0
    error_rate:         float = 0.0

    avg_latency_ms:     float = 0.0
    p50_latency_ms:     float = 0.0
    p95_latency_ms:     float = 0.0
    p99_latency_ms:     float = 0.0

    total_tokens:       int = 0
    total_cost_usd:     float = 0.0
    avg_cost_per_call:  float = 0.0

    llm_calls_per_trace:float = 0.0
    tool_calls_per_trace:float = 0.0


# ─── Alert Models ─────────────────────────────────────────────────────────────

class AlertRule(BaseModel):
    """Configuration for a monitoring alert rule."""
    rule_id:        str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id:         str
    project_id:     str
    name:           str
    description:    Optional[str] = None
    severity:       AlertSeverity = AlertSeverity.WARNING
    enabled:        bool = True

    # Trigger condition
    metric:         str                  # e.g., "error_rate", "p95_latency_ms", "cost_usd"
    operator:       str                  # gt | lt | gte | lte | eq
    threshold:      float
    window_minutes: int = 5
    agent_filter:   Optional[str] = None # glob pattern, None = all agents

    # Notification channels
    notify_slack:   bool = False
    notify_email:   List[str] = Field(default_factory=list)
    notify_pagerduty: bool = False

    created_at:     datetime = Field(default_factory=datetime.utcnow)
    updated_at:     datetime = Field(default_factory=datetime.utcnow)


class Alert(BaseModel):
    """A fired alert instance."""
    alert_id:       str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id:        str
    org_id:         str
    severity:       AlertSeverity
    title:          str
    description:    str
    metric:         str
    current_value:  float
    threshold:      float
    agent_name:     Optional[str] = None
    fired_at:       datetime = Field(default_factory=datetime.utcnow)
    resolved_at:    Optional[datetime] = None
    acknowledged:   bool = False
    acknowledged_by: Optional[str] = None


# ─── Evaluation Models ────────────────────────────────────────────────────────

class EvalDimension(BaseModel):
    """A single evaluation dimension result."""
    name:       str        # e.g., "relevance", "faithfulness", "tool_selection"
    score:      float      # 0.0 – 1.0
    verdict:    EvalVerdict
    reasoning:  Optional[str] = None
    raw_output: Optional[str] = None


class EvalResult(BaseModel):
    """Complete evaluation result for a trace or span."""
    eval_id:        str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id:       str
    span_id:        Optional[str] = None
    org_id:         str
    project_id:     str

    judge_model:    str
    eval_template:  str
    dimensions:     List[EvalDimension] = Field(default_factory=list)
    overall_score:  Optional[float] = None
    overall_verdict: EvalVerdict = EvalVerdict.SKIP

    latency_ms:     Optional[float] = None
    cost_usd:       Optional[float] = None
    evaluated_at:   datetime = Field(default_factory=datetime.utcnow)


# ─── Auth Models ─────────────────────────────────────────────────────────────

class ApiKey(BaseModel):
    key_id:     str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id:     str
    name:       str
    key_hash:   str          # bcrypt hash — never store plaintext
    role:       str = "developer"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used:  Optional[datetime] = None
    revoked:    bool = False
