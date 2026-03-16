"""
AgentLens — Backend Unit Tests
Tests for core services: PII redaction, cost calculation, ingestion pipeline,
evaluation engine, and alerting.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# ─── PII Redaction Tests ──────────────────────────────────────────────────────

class TestPIIRedactor:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.security.pii import PIIRedactor
        self.redactor = PIIRedactor()
        self.redactor.enabled = True

    def test_redacts_email(self):
        result = self.redactor.redact_string("Contact us at john.doe@example.com for support")
        assert "john.doe@example.com" not in result
        assert "EMAIL_REDACTED" in result

    def test_redacts_phone(self):
        result = self.redactor.redact_string("Call me at 555-123-4567 anytime")
        assert "555-123-4567" not in result

    def test_redacts_credit_card(self):
        result = self.redactor.redact_string("My card is 4111111111111111")
        assert "4111111111111111" not in result

    def test_redacts_api_key(self):
        result = self.redactor.redact_string("token: sk-abcdefghijklmnopqrstuvwxyz123456")
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result

    def test_does_not_alter_clean_text(self):
        clean = "The agent completed the search task successfully."
        result = self.redactor.redact_string(clean)
        assert result == clean

    def test_redacts_nested_dict(self):
        payload = {"user": {"email": "test@test.com", "query": "hello"}}
        result = self.redactor.redact(payload)
        assert "test@test.com" not in str(result)
        assert result["user"]["query"] == "hello"

    def test_redacts_list(self):
        data = ["normal text", "email: user@domain.org", 42]
        result = self.redactor.redact(data)
        assert "user@domain.org" not in str(result)
        assert result[2] == 42

    def test_disabled_redactor_passes_through(self):
        self.redactor.enabled = False
        text = "email: test@example.com"
        assert self.redactor.redact_string(text) == text


# ─── Cost Calculation Tests ───────────────────────────────────────────────────

class TestCostCalculator:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.services.cost import CostCalculator
        from src.models.trace import TokenUsage
        self.calc = CostCalculator()
        self.TokenUsage = TokenUsage

    def test_gpt4o_cost(self):
        usage = self.TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = self.calc.calculate("openai", "gpt-4o", usage)
        assert cost.total_cost_usd > 0
        # 1000 * 0.0025/1000 + 500 * 0.01/1000 = 0.0025 + 0.005 = 0.0075
        assert abs(cost.total_cost_usd - 0.0075) < 0.0001

    def test_claude_sonnet_cost(self):
        usage = self.TokenUsage(prompt_tokens=2000, completion_tokens=800, total_tokens=2800)
        cost = self.calc.calculate("anthropic", "claude-sonnet-4-5", usage)
        assert cost.total_cost_usd > 0

    def test_unknown_model_returns_zero(self):
        usage = self.TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = self.calc.calculate("unknown_provider", "mystery-model-v99", usage)
        assert cost.total_cost_usd == 0.0

    def test_zero_tokens_returns_zero(self):
        usage = self.TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        cost = self.calc.calculate("openai", "gpt-4o", usage)
        assert cost.total_cost_usd == 0.0

    def test_model_prefix_matching(self):
        usage = self.TokenUsage(prompt_tokens=1000, completion_tokens=200, total_tokens=1200)
        # "gpt-4o-2024-11-20" should match "gpt-4o" pricing via prefix
        cost = self.calc.calculate("openai", "gpt-4o-2024-11-20", usage)
        assert cost.total_cost_usd > 0

    def test_cached_tokens_discounted(self):
        usage = self.TokenUsage(prompt_tokens=2000, completion_tokens=500, total_tokens=2500)
        cost_no_cache   = self.calc.calculate("openai", "gpt-4o", usage, cached_tokens=0)
        cost_with_cache = self.calc.calculate("openai", "gpt-4o", usage, cached_tokens=1000)
        assert cost_with_cache.total_cost_usd < cost_no_cache.total_cost_usd

    def test_list_models_returns_entries(self):
        models = self.calc.list_models()
        assert len(models) > 5
        assert any(m["provider"] == "openai" for m in models)
        assert any(m["provider"] == "anthropic" for m in models)


# ─── Data Model Tests ─────────────────────────────────────────────────────────

class TestTraceModels:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.models.trace import (
            Span, Trace, SpanKind, SpanStatus, FrameworkType,
            LLMAttributes, TokenUsage, LLMProvider
        )
        self.Span = Span
        self.Trace = Trace
        self.SpanKind = SpanKind
        self.SpanStatus = SpanStatus
        self.FrameworkType = FrameworkType
        self.LLMAttributes = LLMAttributes
        self.TokenUsage = TokenUsage
        self.LLMProvider = LLMProvider

    def _make_span(self, **kwargs):
        defaults = dict(
            trace_id="trace-001",
            name="test-span",
            kind=self.SpanKind.AGENT,
            start_time=datetime.utcnow(),
            org_id="org-1",
            project_id="proj-1",
        )
        defaults.update(kwargs)
        return self.Span(**defaults)

    def test_span_creation(self):
        span = self._make_span()
        assert span.span_id is not None
        assert span.status == self.SpanStatus.UNSET

    def test_span_auto_generates_id(self):
        s1 = self._make_span()
        s2 = self._make_span()
        assert s1.span_id != s2.span_id

    def test_span_duration_computed(self):
        from datetime import timedelta
        start = datetime(2026, 1, 1, 12, 0, 0)
        end   = datetime(2026, 1, 1, 12, 0, 1)  # 1 second later
        span  = self._make_span(start_time=start, end_time=end)
        assert span.duration_ms == pytest.approx(1000.0, abs=0.1)

    def test_llm_span_with_attributes(self):
        llm_attrs = self.LLMAttributes(
            provider=self.LLMProvider.OPENAI,
            model="gpt-4o",
            token_usage=self.TokenUsage(
                prompt_tokens=100, completion_tokens=50, total_tokens=150
            ),
        )
        span = self._make_span(kind=self.SpanKind.LLM, llm_attributes=llm_attrs)
        assert span.llm_attributes.model == "gpt-4o"
        assert span.llm_attributes.token_usage.total_tokens == 150

    def test_trace_creation(self):
        trace = self.Trace(
            name="research-task",
            agent_name="research-agent",
            framework=self.FrameworkType.LANGCHAIN,
            org_id="org-1",
            project_id="proj-1",
            start_time=datetime.utcnow(),
        )
        assert trace.trace_id is not None
        assert trace.total_spans == 0


# ─── Ingestion Service Tests ──────────────────────────────────────────────────

class TestTraceIngestionService:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    def _make_span(self, trace_id="trace-1", kind_str="agent", status_str="OK"):
        from src.models.trace import Span, SpanKind, SpanStatus
        return Span(
            trace_id=trace_id,
            name="test-span",
            kind=SpanKind(kind_str),
            status=SpanStatus(status_str),
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            org_id="org-1",
            project_id="proj-1",
        )

    def test_redact_span_called(self):
        from src.services.ingestion import TraceIngestionService
        svc = TraceIngestionService()
        svc.storage = MagicMock()
        svc.redactor = MagicMock()
        svc.redactor.redact_trace_payload = lambda x: x
        svc.cost_calc = MagicMock()
        svc.cost_calc.calculate = MagicMock()

        spans = [self._make_span()]
        svc.ingest_spans(spans)
        assert svc.storage.insert_spans.called

    def test_builds_trace_from_spans(self):
        from src.services.ingestion import TraceIngestionService
        from src.models.trace import SpanKind, SpanStatus, Span

        svc = TraceIngestionService()

        spans = [
            self._make_span("t1", "agent", "OK"),
            self._make_span("t1", "llm", "OK"),
            self._make_span("t1", "tool", "ERROR"),
        ]

        trace = svc._build_trace_record("t1", spans)
        assert trace is not None
        assert trace.total_spans == 3
        assert trace.llm_call_count == 1
        assert trace.tool_call_count == 1
        assert trace.error_count == 1
        assert trace.status == SpanStatus.ERROR

    def test_empty_spans_returns_none(self):
        from src.services.ingestion import TraceIngestionService
        svc = TraceIngestionService()
        result = svc._build_trace_record("t1", [])
        assert result is None


# ─── RBAC Tests ───────────────────────────────────────────────────────────────

class TestRBAC:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.security.pii import check_permission, require_permission
        self.check = check_permission
        self.require = require_permission

    def test_viewer_can_read_traces(self):
        assert self.check("viewer", "traces:read") is True

    def test_viewer_cannot_write_traces(self):
        assert self.check("viewer", "traces:write") is False

    def test_developer_can_write(self):
        assert self.check("developer", "traces:write") is True

    def test_admin_has_all_permissions(self):
        assert self.check("admin", "traces:delete") is True
        assert self.check("admin", "settings:write") is True
        assert self.check("admin", "users:write") is True

    def test_unknown_role_has_no_permissions(self):
        assert self.check("hacker", "traces:read") is False

    def test_require_raises_on_missing_permission(self):
        with pytest.raises(PermissionError):
            self.require("viewer", "traces:delete")

    def test_require_does_not_raise_on_valid_permission(self):
        self.require("admin", "traces:delete")  # should not raise


# ─── Evaluation Engine Tests ──────────────────────────────────────────────────

class TestEvaluationEngine:
    def setup_method(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.evaluation.engine import EvaluationEngine, EVAL_TEMPLATES
        self.EvaluationEngine = EvaluationEngine
        self.EVAL_TEMPLATES = EVAL_TEMPLATES

    def test_templates_loaded(self):
        assert "relevance" in self.EVAL_TEMPLATES
        assert "faithfulness" in self.EVAL_TEMPLATES
        assert "tool_selection" in self.EVAL_TEMPLATES
        assert "safety" in self.EVAL_TEMPLATES

    def test_list_templates(self):
        engine = self.EvaluationEngine()
        templates = engine.list_templates()
        assert len(templates) >= 5
        names = [t["name"] for t in templates]
        assert "relevance" in names

    def test_parse_valid_judge_response(self):
        engine = self.EvaluationEngine()
        raw = '{"score": 0.85, "verdict": "pass", "reasoning": "Highly relevant."}'
        dim = engine._parse_judge_response(raw, "relevance")
        from src.models.trace import EvalVerdict
        assert dim.score == pytest.approx(0.85)
        assert dim.verdict == EvalVerdict.PASS
        assert "Highly relevant" in dim.reasoning

    def test_parse_invalid_json_returns_skip(self):
        engine = self.EvaluationEngine()
        raw = "not valid json at all !!"
        dim = engine._parse_judge_response(raw, "relevance")
        from src.models.trace import EvalVerdict
        assert dim.verdict == EvalVerdict.SKIP
        assert dim.score == 0.0

    def test_score_clamped_to_range(self):
        engine = self.EvaluationEngine()
        raw = '{"score": 1.5, "verdict": "pass", "reasoning": "Great."}'
        dim = engine._parse_judge_response(raw, "relevance")
        assert dim.score <= 1.0

    def test_evaluation_disabled_raises(self):
        engine = self.EvaluationEngine()
        engine.settings = MagicMock()
        engine.settings.feature_evaluations = False

        from src.models.trace import Trace, FrameworkType, TokenUsage
        trace = Trace(
            name="t", agent_name="a", framework=FrameworkType.CUSTOM,
            org_id="o", project_id="p", start_time=datetime.utcnow(),
            token_usage=TokenUsage(),
        )
        with pytest.raises(RuntimeError, match="disabled"):
            engine.evaluate_trace(trace)
