"""
AgentLens — LLM Cost Tracking Service
Computes per-request USD costs for all major LLM providers.
Pricing tables reflect Q1 2026 rates — update as providers change pricing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..core.logging import get_logger
from ..models.trace import CostBreakdown, LLMProvider, TokenUsage

logger = get_logger("services.cost")


@dataclass
class ModelPricing:
    """Per-token pricing in USD per 1,000 tokens."""
    provider:           LLMProvider
    model:              str
    input_per_1k:       float   # prompt tokens
    output_per_1k:      float   # completion tokens
    cached_input_per_1k: float = 0.0  # cached prompt discount


# ─── Pricing Table ─────────────────────────────────────────────────────────────
# Source: Provider pricing pages, Q1 2026. Update as pricing changes.

PRICING_TABLE: Dict[Tuple[str, str], ModelPricing] = {
    # ── OpenAI ───────────────────────────────────────────────────────────────
    ("openai", "gpt-4o"):                    ModelPricing(LLMProvider.OPENAI, "gpt-4o",                    0.0025, 0.01,   0.00125),
    ("openai", "gpt-4o-mini"):               ModelPricing(LLMProvider.OPENAI, "gpt-4o-mini",               0.00015, 0.0006, 0.000075),
    ("openai", "o1"):                        ModelPricing(LLMProvider.OPENAI, "o1",                        0.015,  0.06,   0.0075),
    ("openai", "o1-mini"):                   ModelPricing(LLMProvider.OPENAI, "o1-mini",                   0.003,  0.012,  0.0015),
    ("openai", "o3"):                        ModelPricing(LLMProvider.OPENAI, "o3",                        0.01,   0.04,   0.005),
    ("openai", "o3-mini"):                   ModelPricing(LLMProvider.OPENAI, "o3-mini",                   0.0011, 0.0044, 0.00055),
    ("openai", "gpt-4.1"):                   ModelPricing(LLMProvider.OPENAI, "gpt-4.1",                   0.002,  0.008,  0.001),
    ("openai", "gpt-3.5-turbo"):             ModelPricing(LLMProvider.OPENAI, "gpt-3.5-turbo",             0.0005, 0.0015, 0.0),

    # ── Anthropic ────────────────────────────────────────────────────────────
    ("anthropic", "claude-opus-4-5"):        ModelPricing(LLMProvider.ANTHROPIC, "claude-opus-4-5",       0.015,  0.075,  0.0075),
    ("anthropic", "claude-sonnet-4-5"):      ModelPricing(LLMProvider.ANTHROPIC, "claude-sonnet-4-5",     0.003,  0.015,  0.00150),
    ("anthropic", "claude-haiku-4-5"):       ModelPricing(LLMProvider.ANTHROPIC, "claude-haiku-4-5",      0.00025, 0.00125, 0.000125),
    ("anthropic", "claude-3-opus-20240229"): ModelPricing(LLMProvider.ANTHROPIC, "claude-3-opus",         0.015,  0.075,  0.0075),
    ("anthropic", "claude-3-5-sonnet-20241022"): ModelPricing(LLMProvider.ANTHROPIC, "claude-3-5-sonnet", 0.003, 0.015,  0.0015),

    # ── Google ───────────────────────────────────────────────────────────────
    ("google", "gemini-2.0-flash"):          ModelPricing(LLMProvider.GOOGLE, "gemini-2.0-flash",          0.0001, 0.0004, 0.0),
    ("google", "gemini-2.0-flash-thinking"): ModelPricing(LLMProvider.GOOGLE, "gemini-2.0-flash-thinking", 0.00035, 0.0015, 0.0),
    ("google", "gemini-2.5-pro"):            ModelPricing(LLMProvider.GOOGLE, "gemini-2.5-pro",            0.00125, 0.01,  0.0),
    ("google", "gemini-1.5-pro"):            ModelPricing(LLMProvider.GOOGLE, "gemini-1.5-pro",            0.00125, 0.005, 0.0),
    ("google", "gemini-1.5-flash"):          ModelPricing(LLMProvider.GOOGLE, "gemini-1.5-flash",          0.000075, 0.0003, 0.0),

    # ── Mistral ──────────────────────────────────────────────────────────────
    ("mistral", "mistral-large-latest"):     ModelPricing(LLMProvider.MISTRAL, "mistral-large",            0.002,  0.006,  0.0),
    ("mistral", "mistral-small-latest"):     ModelPricing(LLMProvider.MISTRAL, "mistral-small",            0.0002, 0.0006, 0.0),

    # ── AWS Bedrock ──────────────────────────────────────────────────────────
    ("bedrock", "anthropic.claude-3-5-sonnet-20241022-v2:0"):
        ModelPricing(LLMProvider.BEDROCK, "bedrock-claude-3-5-sonnet",                                     0.003,  0.015,  0.0),
    ("bedrock", "amazon.titan-text-express-v1"):
        ModelPricing(LLMProvider.BEDROCK, "titan-text-express",                                             0.0002, 0.0006, 0.0),

    # ── Azure OpenAI (same token prices as OpenAI) ──────────────────────────
    ("azure_openai", "gpt-4o"):              ModelPricing(LLMProvider.AZURE_OPENAI, "azure-gpt-4o",        0.0025, 0.01,   0.0),
}


class CostCalculator:
    """Calculates USD cost for LLM API calls."""

    def get_pricing(
        self, provider: str, model: str
    ) -> Optional[ModelPricing]:
        # Exact match first
        key = (provider.lower(), model.lower())
        if key in PRICING_TABLE:
            return PRICING_TABLE[key]

        # Prefix match (e.g., "gpt-4o-2024-11-20" → "gpt-4o")
        for (p, m), pricing in PRICING_TABLE.items():
            if p == provider.lower() and model.lower().startswith(m):
                return pricing

        logger.debug("No pricing found for model", provider=provider, model=model)
        return None

    def calculate(
        self,
        provider: str,
        model: str,
        token_usage: TokenUsage,
        cached_tokens: int = 0,
    ) -> CostBreakdown:
        pricing = self.get_pricing(provider, model)
        if not pricing:
            return CostBreakdown()

        billable_prompt = token_usage.prompt_tokens - cached_tokens
        prompt_cost = (max(billable_prompt, 0) / 1000) * pricing.input_per_1k
        cached_cost = (cached_tokens / 1000) * pricing.cached_input_per_1k
        completion_cost = (token_usage.completion_tokens / 1000) * pricing.output_per_1k

        return CostBreakdown(
            prompt_cost_usd=round(prompt_cost + cached_cost, 8),
            completion_cost_usd=round(completion_cost, 8),
            total_cost_usd=round(prompt_cost + cached_cost + completion_cost, 8),
        )

    def list_models(self) -> list:
        return [
            {
                "provider": p,
                "model": m,
                "input_per_1k_usd": pricing.input_per_1k,
                "output_per_1k_usd": pricing.output_per_1k,
            }
            for (p, m), pricing in sorted(PRICING_TABLE.items())
        ]


# ─── Singleton ────────────────────────────────────────────────────────────────

_calculator: Optional[CostCalculator] = None


def get_cost_calculator() -> CostCalculator:
    global _calculator
    if _calculator is None:
        _calculator = CostCalculator()
    return _calculator
