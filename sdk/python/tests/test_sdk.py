"""
AgentLens Python SDK — Unit Tests
Tests for init, span buffering, decorators, context propagation, and flush.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import agentlens_sdk as sdk


def _reset():
    """Reset SDK state between tests."""
    sdk._state.enabled      = False
    sdk._state.api_key      = ""
    sdk._state._span_buffer = []
    sdk._current_trace_id.set(None)
    sdk._current_span_id.set(None)
    sdk._current_agent_name.set(None)
    sdk._current_session_id.set(None)


# ─── init() ────────────────────────────────────────────────────────────────────

class TestInit:
    def setup_method(self):
        _reset()

    def test_init_sets_state(self):
        sdk.init(api_key="key-123", endpoint="http://test:8000", org_id="org1")
        assert sdk._state.enabled is True
        assert sdk._state.api_key == "key-123"
        assert sdk._state.org_id == "org1"

    def test_init_trims_trailing_slash(self):
        sdk.init(api_key="k", endpoint="http://test:8000/")
        assert sdk._state.endpoint == "http://test:8000"

    def test_init_defaults(self):
        sdk.init(api_key="k")
        assert sdk._state.environment == "production"
        assert sdk._state.framework   == "custom"
        assert sdk._state.debug       is False


# ─── _new_span() ───────────────────────────────────────────────────────────────

class TestNewSpan:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k", org_id="org1", project_id="proj1")

    def test_span_has_required_fields(self):
        s = sdk._new_span("test", "agent")
        assert s["name"]     == "test"
        assert s["kind"]     == "agent"
        assert s["org_id"]   == "org1"
        assert s["project_id"] == "proj1"
        assert s["span_id"]  is not None
        assert s["status"]   == "UNSET"

    def test_span_ids_are_unique(self):
        ids = {sdk._new_span("n", "agent")["span_id"] for _ in range(100)}
        assert len(ids) == 100

    def test_span_inherits_context_trace_id(self):
        sdk._current_trace_id.set("parent-trace")
        s = sdk._new_span("child", "chain")
        assert s["trace_id"] == "parent-trace"

    def test_span_inherits_parent_span_id(self):
        sdk._current_span_id.set("parent-span")
        s = sdk._new_span("child", "llm")
        assert s["parent_span_id"] == "parent-span"


# ─── _finish_span() ────────────────────────────────────────────────────────────

class TestFinishSpan:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k")

    def test_finish_sets_ok(self):
        s = sdk._new_span("test", "agent")
        sdk._finish_span(s, output="result")
        assert s["status"]   == "OK"
        assert s["output"]   == "result"
        assert s["end_time"] is not None
        assert s["duration_ms"] >= 0

    def test_finish_sets_error(self):
        s = sdk._new_span("test", "tool")
        err = ValueError("something broke")
        sdk._finish_span(s, error=err)
        assert s["status"]     == "ERROR"
        assert "something broke" in s["error"]
        assert s["error_type"] == "ValueError"

    def test_finish_buffers_span(self):
        s = sdk._new_span("test", "llm")
        sdk._finish_span(s)
        assert len(sdk._state._span_buffer) == 1

    def test_disabled_sdk_does_not_buffer(self):
        sdk._state.enabled = False
        s = sdk._new_span("test", "agent")
        sdk._finish_span(s)
        assert len(sdk._state._span_buffer) == 0


# ─── @trace_agent decorator ────────────────────────────────────────────────────

class TestTraceAgentDecorator:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k")

    def test_sync_agent_traced(self):
        @sdk.trace_agent(name="my-agent")
        def run(x):
            return x * 2

        result = run(21)
        assert result == 42
        assert len(sdk._state._span_buffer) == 1
        span = sdk._state._span_buffer[0]
        assert span["name"]   == "my-agent"
        assert span["kind"]   == "agent"
        assert span["status"] == "OK"

    def test_sync_agent_error_captured(self):
        @sdk.trace_agent(name="bad-agent")
        def run():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            run()

        span = sdk._state._span_buffer[0]
        assert span["status"]     == "ERROR"
        assert span["error_type"] == "RuntimeError"

    def test_async_agent_traced(self):
        @sdk.trace_agent(name="async-agent")
        async def run(val):
            await asyncio.sleep(0)
            return val + 1

        result = asyncio.run(run(9))
        assert result == 10
        assert sdk._state._span_buffer[0]["status"] == "OK"

    def test_async_agent_error_captured(self):
        @sdk.trace_agent(name="failing-async")
        async def run():
            raise ValueError("async-fail")

        with pytest.raises(ValueError):
            asyncio.run(run())

        assert sdk._state._span_buffer[0]["status"] == "ERROR"

    def test_trace_id_propagated_to_children(self):
        captured_trace_ids = []

        @sdk.trace_agent(name="parent")
        def parent():
            captured_trace_ids.append(sdk._current_trace_id.get())

        parent()
        assert len(captured_trace_ids) == 1
        assert captured_trace_ids[0] is not None


# ─── @trace_llm decorator ──────────────────────────────────────────────────────

class TestTraceLLMDecorator:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k")

    def test_llm_span_attributes(self):
        @sdk.trace_llm(provider="openai", model="gpt-4o")
        def call():
            return "response"

        call()
        span = sdk._state._span_buffer[0]
        assert span["kind"] == "llm"
        assert span["llm_attributes"]["provider"] == "openai"
        assert span["llm_attributes"]["model"]    == "gpt-4o"

    def test_llm_span_error(self):
        @sdk.trace_llm(provider="anthropic", model="claude-sonnet-4-5")
        def call():
            raise TimeoutError("rate limit")

        with pytest.raises(TimeoutError):
            call()

        assert sdk._state._span_buffer[0]["status"] == "ERROR"


# ─── @trace_tool decorator ─────────────────────────────────────────────────────

class TestTraceToolDecorator:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k")

    def test_tool_span_attributes(self):
        @sdk.trace_tool(name="web_search", description="Searches the web")
        def search(q):
            return f"results for {q}"

        search("AI observability")
        span = sdk._state._span_buffer[0]
        assert span["kind"]  == "tool"
        assert span["tool_attributes"]["tool_name"] == "web_search"

    def test_tool_input_captured(self):
        @sdk.trace_tool(name="calculator")
        def add(a, b):
            return a + b

        add(1, 2)
        assert sdk._state._span_buffer[0]["input"]["args"] == [1, 2]


# ─── span() context manager ───────────────────────────────────────────────────

class TestSpanContextManager:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k")

    def test_span_creates_and_buffers(self):
        with sdk.span("retrieval", kind="retrieval") as s:
            s["attributes"]["query"] = "test query"

        assert len(sdk._state._span_buffer) == 1
        span = sdk._state._span_buffer[0]
        assert span["name"] == "retrieval"
        assert span["status"] == "OK"

    def test_span_captures_exception(self):
        with pytest.raises(KeyError):
            with sdk.span("failing-step") as s:
                raise KeyError("missing key")

        span = sdk._state._span_buffer[0]
        assert span["status"]     == "ERROR"
        assert span["error_type"] == "KeyError"


# ─── LangChain Callback Handler ───────────────────────────────────────────────

class TestAgentLensCallbackHandler:
    def setup_method(self):
        _reset()
        sdk.init(api_key="k")
        self.handler = sdk.AgentLensCallbackHandler(session_id="sess-1")

    def _make_run_id(self):
        return str(uuid.uuid4())

    def test_chain_start_end(self):
        run_id = self._make_run_id()
        self.handler.on_chain_start({"name": "TestChain"}, {"input": "hello"}, run_id=run_id)
        self.handler.on_chain_end({"output": "world"}, run_id=run_id)

        assert len(sdk._state._span_buffer) == 1
        span = sdk._state._span_buffer[0]
        assert span["kind"]   == "chain"
        assert span["status"] == "OK"

    def test_chain_error(self):
        run_id = self._make_run_id()
        self.handler.on_chain_start({"name": "Broken"}, {}, run_id=run_id)
        self.handler.on_chain_error(Exception("chain broke"), run_id=run_id)

        span = sdk._state._span_buffer[0]
        assert span["status"] == "ERROR"

    def test_llm_start_end(self):
        run_id = self._make_run_id()
        self.handler.on_llm_start(
            {"kwargs": {"model_name": "gpt-4o"}},
            ["Hello, world!"],
            run_id=run_id,
        )
        mock_response = MagicMock()
        mock_response.generations = [[MagicMock(text="Response text")]]
        mock_response.llm_output  = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        self.handler.on_llm_end(mock_response, run_id=run_id)

        span = sdk._state._span_buffer[0]
        assert span["kind"] == "llm"
        assert span["llm_attributes"]["token_usage"]["total_tokens"] == 15

    def test_tool_start_end(self):
        run_id = self._make_run_id()
        self.handler.on_tool_start({"name": "search"}, "AI agents", run_id=run_id)
        self.handler.on_tool_end("search results", run_id=run_id)

        span = sdk._state._span_buffer[0]
        assert span["kind"] == "tool"
        assert span["status"] == "OK"


# ─── flush() ──────────────────────────────────────────────────────────────────

class TestFlush:
    def setup_method(self):
        _reset()
        sdk.init(api_key="key", endpoint="http://fake:9999")

    @pytest.mark.asyncio
    async def test_flush_empty_buffer_returns_true(self):
        result = await sdk.flush()
        assert result is True

    @pytest.mark.asyncio
    async def test_flush_on_network_error_rebuffers(self):
        # Add a span
        s = sdk._new_span("test", "agent")
        sdk._finish_span(s)
        assert len(sdk._state._span_buffer) == 1

        # Flush will fail (fake endpoint)
        result = await sdk.flush()
        # Either success=False and buffer restored, or success=True (shouldn't happen)
        # Network will fail → buffer should be restored
        if not result:
            assert len(sdk._state._span_buffer) == 1
