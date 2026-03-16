"""
AgentLens Python SDK
Auto-instrumentation for AI agent frameworks.
Usage:
    from agentlens_sdk import init, trace_agent, trace_llm, trace_tool

    init(api_key="your-key", endpoint="http://localhost:8000")

    @trace_agent(name="my-agent")
    async def run(query: str): ...
"""
from __future__ import annotations

import asyncio
import contextlib
import functools
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar

import httpx

F = TypeVar("F", bound=Callable)

# ─── Global SDK State ────────────────────────────────────────────────────────

class _SDKState:
    api_key:      str = ""
    endpoint:     str = "http://localhost:8000"
    org_id:       str = ""
    project_id:   str = ""
    environment:  str = "production"
    framework:    str = "custom"
    sdk_version:  str = "1.0.0"
    enabled:      bool = False
    debug:        bool = False
    _span_buffer: List[Dict[str, Any]] = []
    _flush_threshold: int = 50   # auto-flush after N spans
    _http_client: Optional[httpx.AsyncClient] = None

_state = _SDKState()


# ─── Initialization ───────────────────────────────────────────────────────────

def init(
    api_key: str,
    endpoint: str = "http://localhost:8000",
    org_id: str = "default",
    project_id: str = "default",
    environment: str = "production",
    framework: str = "custom",
    debug: bool = False,
    flush_threshold: int = 50,
) -> None:
    """
    Initialize the AgentLens SDK.

    Args:
        api_key:    Your AgentLens API key.
        endpoint:   AgentLens server base URL.
        org_id:     Your organization ID.
        project_id: Your project ID.
        environment: Deployment environment (production|staging|development).
        framework:  Agent framework name (langchain|crewai|autogen|custom).
        debug:      Enable verbose debug logging.
        flush_threshold: Auto-flush after this many buffered spans.
    """
    _state.api_key        = api_key
    _state.endpoint       = endpoint.rstrip("/")
    _state.org_id         = org_id
    _state.project_id     = project_id
    _state.environment    = environment
    _state.framework      = framework
    _state.debug          = debug
    _state.enabled        = True
    _state._flush_threshold = flush_threshold
    _state._span_buffer   = []

    if debug:
        print(f"[AgentLens] SDK initialized → {endpoint}")


# ─── Context Variables ────────────────────────────────────────────────────────

import contextvars

_current_trace_id:   contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id",  default=None)
_current_span_id:    contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("span_id",   default=None)
_current_agent_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("agent_name", default=None)
_current_session_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("session_id", default=None)


# ─── Span Builder ─────────────────────────────────────────────────────────────

def _new_span(
    name: str,
    kind: str,
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    **extra,
) -> Dict[str, Any]:
    return {
        "span_id":       str(uuid.uuid4()),
        "trace_id":      trace_id or _current_trace_id.get() or str(uuid.uuid4()),
        "parent_span_id": parent_span_id or _current_span_id.get(),
        "name":          name,
        "kind":          kind,
        "status":        "UNSET",
        "start_time":    datetime.utcnow().isoformat() + "Z",
        "end_time":      None,
        "duration_ms":   None,
        "agent_id":      agent_id or _current_agent_name.get(),
        "session_id":    _current_session_id.get(),
        "org_id":        _state.org_id,
        "project_id":    _state.project_id,
        "framework":     _state.framework,
        "environment":   _state.environment,
        "sdk_version":   _state.sdk_version,
        "input":         None,
        "output":        None,
        "error":         None,
        "error_type":    None,
        "llm_attributes":  None,
        "tool_attributes": None,
        "attributes":    {},
        "events":        [],
        **extra,
    }


def _finish_span(span: Dict[str, Any], output: Any = None, error: Optional[Exception] = None) -> Dict[str, Any]:
    span["end_time"] = datetime.utcnow().isoformat() + "Z"
    if output is not None:
        span["output"] = output
    if error:
        span["status"]     = "ERROR"
        span["error"]      = str(error)
        span["error_type"] = type(error).__name__
    else:
        span["status"] = "OK"

    start = datetime.fromisoformat(span["start_time"].rstrip("Z"))
    end   = datetime.fromisoformat(span["end_time"].rstrip("Z"))
    span["duration_ms"] = (end - start).total_seconds() * 1000

    _buffer_span(span)
    return span


def _buffer_span(span: Dict[str, Any]) -> None:
    if not _state.enabled:
        return
    _state._span_buffer.append(span)
    if _state.debug:
        print(f"[AgentLens] Span buffered: {span['kind']}/{span['name']} ({span['status']})")
    if len(_state._span_buffer) >= _state._flush_threshold:
        # Fire-and-forget async flush
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(flush())
            else:
                loop.run_until_complete(flush())
        except RuntimeError:
            pass  # No event loop — flush on next opportunity


# ─── HTTP Flush ────────────────────────────────────────────────────────────────

async def flush() -> bool:
    """
    Flush buffered spans to the AgentLens ingestion endpoint.
    Returns True if successful.
    """
    if not _state.enabled or not _state._span_buffer:
        return True

    spans = _state._span_buffer.copy()
    _state._span_buffer.clear()

    payload = {"spans": spans}
    headers = {
        "X-API-Key":    _state.api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_state.endpoint}/api/v1/ingest/spans",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            if _state.debug:
                print(f"[AgentLens] Flushed {len(spans)} spans → {resp.status_code}")
            return True
    except Exception as exc:
        # Re-buffer on failure to avoid data loss
        _state._span_buffer = spans + _state._span_buffer
        if _state.debug:
            print(f"[AgentLens] Flush failed: {exc}")
        return False


def flush_sync() -> bool:
    """Synchronous wrapper for flush (for use in non-async contexts)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, flush())
                return future.result(timeout=15)
        else:
            return loop.run_until_complete(flush())
    except Exception:
        return False


# ─── Decorators ───────────────────────────────────────────────────────────────

def trace_agent(
    name: Optional[str] = None,
    session_id: Optional[str] = None,
    capture_input: bool = True,
    capture_output: bool = True,
):
    """
    Decorator to trace a top-level agent invocation.

    Example:
        @trace_agent(name="research-agent")
        async def run(query: str) -> str:
            ...
    """
    def decorator(func: F) -> F:
        agent_name = name or func.__name__
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                trace_id = str(uuid.uuid4())
                span = _new_span(agent_name, "agent", trace_id=trace_id, agent_id=agent_name)

                t_trace = _current_trace_id.set(trace_id)
                t_span  = _current_span_id.set(span["span_id"])
                t_agent = _current_agent_name.set(agent_name)
                t_sess  = _current_session_id.set(session_id)

                if capture_input:
                    span["input"] = {"args": list(args), "kwargs": kwargs}

                error = None
                result = None
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    _finish_span(span, output=result if capture_output else None, error=error)
                    _current_trace_id.reset(t_trace)
                    _current_span_id.reset(t_span)
                    _current_agent_name.reset(t_agent)
                    _current_session_id.reset(t_sess)

            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                trace_id = str(uuid.uuid4())
                span = _new_span(agent_name, "agent", trace_id=trace_id, agent_id=agent_name)

                t_trace = _current_trace_id.set(trace_id)
                t_span  = _current_span_id.set(span["span_id"])
                t_agent = _current_agent_name.set(agent_name)
                t_sess  = _current_session_id.set(session_id)

                if capture_input:
                    span["input"] = {"args": list(args), "kwargs": kwargs}

                error = None
                result = None
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    _finish_span(span, output=result if capture_output else None, error=error)
                    _current_trace_id.reset(t_trace)
                    _current_span_id.reset(t_span)
                    _current_agent_name.reset(t_agent)
                    _current_session_id.reset(t_sess)

            return sync_wrapper  # type: ignore

    return decorator


def trace_llm(
    provider: str = "openai",
    model: Optional[str] = None,
    capture_prompts: bool = True,
):
    """
    Decorator to trace an LLM call.

    Example:
        @trace_llm(provider="openai", model="gpt-4o")
        def call_llm(messages: list) -> str:
            ...
    """
    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                span = _new_span(
                    name=model or func.__name__,
                    kind="llm",
                    llm_attributes={
                        "provider": provider,
                        "model": model,
                        "token_usage": None,
                        "cost": None,
                    },
                )
                if capture_prompts:
                    span["input"] = {"args": list(args), "kwargs": kwargs}

                error = None
                result = None
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    _finish_span(span, output=result, error=error)

            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                span = _new_span(
                    name=model or func.__name__,
                    kind="llm",
                    llm_attributes={
                        "provider": provider,
                        "model": model,
                        "token_usage": None,
                        "cost": None,
                    },
                )
                if capture_prompts:
                    span["input"] = {"args": list(args), "kwargs": kwargs}

                error = None
                result = None
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    _finish_span(span, output=result, error=error)

            return sync_wrapper  # type: ignore

    return decorator


def trace_tool(name: Optional[str] = None, description: Optional[str] = None):
    """
    Decorator to trace a tool/function call.

    Example:
        @trace_tool(name="web_search", description="Searches the web")
        def search(query: str) -> str:
            ...
    """
    def decorator(func: F) -> F:
        tool_name = name or func.__name__
        is_async  = asyncio.iscoroutinefunction(func)

        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                span = _new_span(
                    name=tool_name,
                    kind="tool",
                    tool_attributes={
                        "tool_name": tool_name,
                        "tool_description": description,
                        "is_mcp_tool": False,
                    },
                )
                span["input"] = {"args": list(args), "kwargs": kwargs}

                error = None
                result = None
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    _finish_span(span, output=result, error=error)

            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                span = _new_span(
                    name=tool_name,
                    kind="tool",
                    tool_attributes={
                        "tool_name": tool_name,
                        "tool_description": description,
                        "is_mcp_tool": False,
                    },
                )
                span["input"] = {"args": list(args), "kwargs": kwargs}

                error = None
                result = None
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = exc
                    raise
                finally:
                    _finish_span(span, output=result, error=error)

            return sync_wrapper  # type: ignore

    return decorator


# ─── Context Manager ─────────────────────────────────────────────────────────

@contextlib.contextmanager
def span(name: str, kind: str = "chain", **attributes):
    """
    Context manager for manual span creation.

    Example:
        with agentlens.span("retrieval-step", kind="retrieval") as s:
            s["attributes"]["query"] = "..."
            results = vector_db.search(query)
    """
    s = _new_span(name, kind)
    s["attributes"].update(attributes)
    error = None
    try:
        yield s
    except Exception as exc:
        error = exc
        raise
    finally:
        _finish_span(s, error=error)


# ─── LangChain Callback Integration ──────────────────────────────────────────

class AgentLensCallbackHandler:
    """
    LangChain callback handler that automatically instruments chains,
    LLM calls, and tool invocations.

    Usage:
        from langchain.callbacks import CallbackManager
        handler = AgentLensCallbackHandler()
        chain = MyChain(callbacks=[handler])
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self._span_stack: Dict[str, Dict] = {}

    def on_chain_start(self, serialized, inputs, run_id=None, **kwargs):
        name = serialized.get("name", "chain") if serialized else "chain"
        s = _new_span(name, "chain")
        s["input"] = inputs
        self._span_stack[str(run_id)] = s

    def on_chain_end(self, outputs, run_id=None, **kwargs):
        s = self._span_stack.pop(str(run_id), None)
        if s:
            _finish_span(s, output=outputs)

    def on_chain_error(self, error, run_id=None, **kwargs):
        s = self._span_stack.pop(str(run_id), None)
        if s:
            _finish_span(s, error=error if isinstance(error, Exception) else Exception(str(error)))

    def on_llm_start(self, serialized, prompts, run_id=None, **kwargs):
        model_name = serialized.get("kwargs", {}).get("model_name", "unknown") if serialized else "unknown"
        s = _new_span(model_name, "llm", llm_attributes={"model": model_name, "provider": "openai"})
        s["input"] = {"prompts": prompts}
        self._span_stack[str(run_id)] = s

    def on_llm_end(self, response, run_id=None, **kwargs):
        s = self._span_stack.pop(str(run_id), None)
        if s:
            output = None
            if hasattr(response, "generations"):
                output = [[g.text for g in gen] for gen in response.generations]
            # Extract token usage if available
            if hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                if usage and s.get("llm_attributes"):
                    s["llm_attributes"]["token_usage"] = {
                        "prompt_tokens":     usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens":      usage.get("total_tokens", 0),
                    }
            _finish_span(s, output=output)

    def on_llm_error(self, error, run_id=None, **kwargs):
        s = self._span_stack.pop(str(run_id), None)
        if s:
            _finish_span(s, error=error if isinstance(error, Exception) else Exception(str(error)))

    def on_tool_start(self, serialized, input_str, run_id=None, **kwargs):
        name = serialized.get("name", "tool") if serialized else "tool"
        s = _new_span(name, "tool", tool_attributes={"tool_name": name})
        s["input"] = input_str
        self._span_stack[str(run_id)] = s

    def on_tool_end(self, output, run_id=None, **kwargs):
        s = self._span_stack.pop(str(run_id), None)
        if s:
            _finish_span(s, output=output)

    def on_tool_error(self, error, run_id=None, **kwargs):
        s = self._span_stack.pop(str(run_id), None)
        if s:
            _finish_span(s, error=error if isinstance(error, Exception) else Exception(str(error)))


# ─── Public API ───────────────────────────────────────────────────────────────

__all__ = [
    "init",
    "flush",
    "flush_sync",
    "trace_agent",
    "trace_llm",
    "trace_tool",
    "span",
    "AgentLensCallbackHandler",
]
