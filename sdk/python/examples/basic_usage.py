"""
AgentLens SDK — Usage Examples

Demonstrates all instrumentation patterns:
  1. Decorator-based agent tracing
  2. LangChain callback integration
  3. Manual span context manager
  4. Async agent pattern
"""
import asyncio
from agentlens_sdk import (
    init, flush, trace_agent, trace_llm, trace_tool, span,
    AgentLensCallbackHandler,
)

# ─── 1. Initialize ────────────────────────────────────────────────────────────

init(
    api_key="your-api-key",
    endpoint="http://localhost:8000",
    org_id="acme-corp",
    project_id="customer-support-bot",
    environment="production",
    framework="langchain",
    debug=True,
)


# ─── 2. Decorator: Trace a synchronous agent ─────────────────────────────────

@trace_agent(name="support-agent")
def run_support_agent(user_query: str) -> str:
    """A simple synchronous agent."""
    response = call_support_llm(user_query)
    if needs_search(user_query):
        context = web_search(user_query)
        response = call_support_llm(user_query, context=context)
    return response


@trace_llm(provider="openai", model="gpt-4o")
def call_support_llm(query: str, context: str = "") -> str:
    """LLM call — automatically traced."""
    # In practice: call openai.chat.completions.create(...)
    return f"Answer to: {query}"


@trace_tool(name="web_search", description="Searches the web for current information")
def web_search(query: str) -> str:
    """Tool call — automatically traced."""
    return f"Search results for: {query}"


def needs_search(query: str) -> bool:
    return "current" in query.lower() or "latest" in query.lower()


# ─── 3. Decorator: Async agent ───────────────────────────────────────────────

@trace_agent(name="async-research-agent", capture_input=True, capture_output=True)
async def run_research_agent(topic: str) -> dict:
    """Async agent with multiple tool calls."""
    with span("planning-step", kind="chain") as planning_span:
        planning_span["attributes"]["topic"] = topic
        plan = await plan_research(topic)

    results = []
    for subtopic in plan:
        result = await fetch_information(subtopic)
        results.append(result)

    summary = await summarize_results(results)
    return {"topic": topic, "summary": summary, "sources": len(results)}


@trace_llm(provider="anthropic", model="claude-sonnet-4-5")
async def plan_research(topic: str) -> list:
    await asyncio.sleep(0.01)  # Simulate API call
    return [f"{topic} - part 1", f"{topic} - part 2"]


@trace_tool(name="fetch_information")
async def fetch_information(subtopic: str) -> str:
    await asyncio.sleep(0.01)
    return f"Information about: {subtopic}"


@trace_llm(provider="openai", model="gpt-4o")
async def summarize_results(results: list) -> str:
    await asyncio.sleep(0.01)
    return f"Summary of {len(results)} results"


# ─── 4. Manual Span Context Manager ─────────────────────────────────────────

def run_custom_agent(query: str) -> str:
    """Agent instrumented using manual context manager spans."""

    # Root agent span
    with span("custom-agent", kind="agent") as root:
        root["input"] = {"query": query}

        # Child: retrieval step
        with span("vector-retrieval", kind="retrieval") as retrieval:
            retrieval["attributes"]["collection"] = "product-docs"
            retrieval["attributes"]["top_k"] = 5
            docs = ["doc1", "doc2", "doc3"]  # Simulate retrieval
            retrieval["attributes"]["retrieved_count"] = len(docs)

        # Child: LLM call
        with span("generate-response", kind="llm") as llm_span:
            llm_span["llm_attributes"] = {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "token_usage": {"prompt_tokens": 500, "completion_tokens": 150, "total_tokens": 650},
            }
            answer = f"Based on docs: answer to {query}"

        root["output"] = answer
        return answer


# ─── 5. LangChain Integration ────────────────────────────────────────────────

def setup_langchain_agent():
    """
    Integrate AgentLens with a LangChain agent via callback handler.
    The handler automatically captures all chain, LLM, and tool events.
    """
    handler = AgentLensCallbackHandler(session_id="session-abc-123")

    # Pass the handler to any LangChain component:
    # chain = LLMChain(llm=ChatOpenAI(), prompt=prompt, callbacks=[handler])
    # agent = AgentExecutor(agent=agent, tools=tools, callbacks=[handler])

    print("LangChain handler ready:", handler)
    return handler


# ─── 6. Session Tracking ─────────────────────────────────────────────────────

SESSION_ID = str(__import__("uuid").uuid4())

@trace_agent(name="conversational-agent", session_id=SESSION_ID)
async def chat_turn(message: str, turn: int) -> str:
    """Each turn in a multi-turn conversation shares the same session_id."""
    return f"Turn {turn} response to: {message}"


async def run_conversation():
    messages = ["Hello!", "Tell me about AI.", "What is observability?"]
    for i, msg in enumerate(messages):
        response = await chat_turn(msg, turn=i + 1)
        print(f"Turn {i+1}: {response}")

    # Flush all buffered spans when conversation ends
    await flush()


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Sync Agent ===")
    result = run_support_agent("What is your return policy?")
    print("Result:", result)

    print("\n=== Async Research Agent ===")
    result = asyncio.run(run_research_agent("quantum computing"))
    print("Result:", result)

    print("\n=== Manual Spans ===")
    result = run_custom_agent("How do I reset my password?")
    print("Result:", result)

    print("\n=== Multi-turn Session ===")
    asyncio.run(run_conversation())

    print(f"\nBuffered spans: {len(__import__('agentlens_sdk')._state._span_buffer)}")
