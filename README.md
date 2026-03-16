# AgentLens — AI Agent Observability Platform

> Cross-platform observability, tracing, evaluation, and monitoring for AI agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-compatible-orange)](https://opentelemetry.io)
[![Python SDK](https://img.shields.io/badge/Python-3.10%2B-green)](sdk/python)
[![Node.js SDK](https://img.shields.io/badge/Node.js-18%2B-green)](sdk/nodejs)

---

## Overview

AgentLens provides end-to-end observability for AI agents built on any framework — LangChain, CrewAI, AutoGen, OpenAI Agents SDK, Semantic Kernel, or custom implementations. It collects distributed traces, monitors LLM costs and latency, runs automated evaluations, and provides a real-time dashboard — all deployable independently as SaaS, self-hosted Docker, or air-gapped on-premises.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Applications                        │
│  LangChain │ CrewAI │ AutoGen │ OpenAI SDK │ Custom Agents   │
└──────────────────────┬──────────────────────────────────────┘
                       │ OTEL Spans (gRPC / HTTP)
┌──────────────────────▼──────────────────────────────────────┐
│              AgentLens Collection Layer                      │
│         Python SDK │ Node.js SDK │ Generic OTEL              │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Ingestion & Processing (FastAPI)                │
│   Kafka/NATS  │  Stream Processor  │  Evaluation Engine      │
└───────────┬───────────┬────────────────────────────────────┘
            │           │
   ┌────────▼───┐  ┌────▼──────────┐  ┌────────────────────┐
   │ ClickHouse │  │  Prometheus   │  │    Object Store    │
   │  (traces) │  │  (metrics)    │  │ (eval artifacts)   │
   └────────────┘  └───────────────┘  └────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              REST / GraphQL / WebSocket API                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              React Dashboard + CLI                           │
└─────────────────────────────────────────────────────────────┘
```

## Repository Structure

```
agentlens/
├── backend/               # FastAPI server (Python)
│   ├── src/
│   │   ├── api/           # REST API routes
│   │   ├── core/          # Configuration, logging, telemetry
│   │   ├── models/        # Pydantic data models
│   │   ├── services/      # Business logic layer
│   │   ├── storage/       # ClickHouse, Prometheus, Redis adapters
│   │   ├── evaluation/    # LLM-as-judge evaluation engine
│   │   └── security/      # Auth, RBAC, PII redaction
│   ├── tests/
│   └── config/
├── frontend/              # React + TypeScript dashboard
│   └── src/
│       ├── components/    # UI components
│       ├── pages/         # Dashboard, Traces, Evals, Alerts
│       ├── hooks/         # Data fetching hooks
│       └── store/         # Zustand state management
├── sdk/
│   ├── python/            # Python instrumentation SDK
│   └── nodejs/            # Node.js instrumentation SDK
├── docker/                # Docker Compose + Helm charts
└── docs/                  # API documentation
```

## Quick Start

### Docker Compose (Self-Hosted)

```bash
git clone https://github.com/your-org/agentlens
cd agentlens
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d
# Dashboard: http://localhost:3000
# API:       http://localhost:8000
```

### Instrument Your Agent (Python)

```python
from agentlens_sdk import init, trace_agent

init(api_key="your-key", endpoint="http://localhost:8000")

@trace_agent(name="my-research-agent")
async def run_agent(query: str):
    # your agent code here ...
    pass
```

### Instrument Your Agent (Node.js)

```javascript
const { init, traceAgent } = require('agentlens-sdk');
init({ apiKey: 'your-key', endpoint: 'http://localhost:8000' });

const result = await traceAgent('my-agent', async () => {
  // your agent code here ...
});
```

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|---|---|---|
| `AGENTLENS_API_KEY` | Platform API key | — |
| `CLICKHOUSE_URL` | ClickHouse connection | `localhost:9000` |
| `REDIS_URL` | Redis for caching | `localhost:6379` |
| `KAFKA_BROKERS` | Kafka brokers | `localhost:9092` |
| `EVALUATION_MODEL` | Judge LLM model | `gpt-4o` |
| `OPENAI_API_KEY` | For evaluations | — |

## License

MIT © AgentLens Contributors
