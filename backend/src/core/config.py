"""
AgentLens — Core Configuration
Loads all settings from environment variables / .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Platform ────────────────────────────────────────────────
    env: str = "development"
    secret_key: str = "change-me-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = Field(default=["http://localhost:3000"])
    debug: bool = Field(default=False)

    # ─── ClickHouse ──────────────────────────────────────────────
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 9000
    clickhouse_db: str = "agentlens"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""

    # ─── Redis ───────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ─── Kafka ───────────────────────────────────────────────────
    kafka_brokers: str = "localhost:9092"
    kafka_topic_traces: str = "agentlens.traces"
    kafka_topic_metrics: str = "agentlens.metrics"
    kafka_topic_alerts: str = "agentlens.alerts"

    # ─── Prometheus ──────────────────────────────────────────────
    prometheus_port: int = 9090

    # ─── Evaluation ──────────────────────────────────────────────
    evaluation_model: str = "gpt-4o"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ─── Object Storage ──────────────────────────────────────────
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "agentlens-artifacts"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"

    # ─── Alerts ──────────────────────────────────────────────────
    slack_webhook_url: str = ""
    pagerduty_api_key: str = ""

    # ─── PII Redaction ───────────────────────────────────────────
    pii_redaction_enabled: bool = True
    pii_redaction_patterns: str = "email,phone,ssn,credit_card"

    # ─── Feature Flags ───────────────────────────────────────────
    feature_evaluations: bool = True
    feature_shadow_agent_discovery: bool = False
    feature_ai_copilot: bool = False

    @property
    def kafka_brokers_list(self) -> List[str]:
        return [b.strip() for b in self.kafka_brokers.split(",")]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
