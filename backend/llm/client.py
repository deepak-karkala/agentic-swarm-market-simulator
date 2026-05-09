"""LLM abstraction layer — all pipeline stages call LLMs through this module."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"


MODEL_IDS: dict[ModelTier, str] = {
    ModelTier.HAIKU: "claude-haiku-4-5-20251001",
    ModelTier.SONNET: "claude-sonnet-4-6",
}

COST_PER_1K_INPUT: dict[ModelTier, float] = {
    ModelTier.HAIKU: 0.00025,
    ModelTier.SONNET: 0.003,
}

COST_PER_1K_OUTPUT: dict[ModelTier, float] = {
    ModelTier.HAIKU: 0.00125,
    ModelTier.SONNET: 0.015,
}

RETRY_DELAYS = (1.0, 2.0, 4.0)
MAX_RETRIES = 3
DEFAULT_COST_CAP = 10.0


class LLMRateLimitError(Exception):
    """Raised after all retries on HTTP 429 are exhausted."""


class LLMCostCapExceeded(Exception):
    """Raised when per-simulation cost exceeds the hard cap."""


class LLMClient:
    """Async client for Anthropic API with model routing, backoff, and cost tracking."""

    def __init__(
        self,
        api_key: str | None = None,
        cost_cap: float = DEFAULT_COST_CAP,
    ):
        self._client = AsyncAnthropic(api_key=api_key)
        self._total_cost = 0.0
        self._cost_cap = cost_cap

    # -- public properties --

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost

    def reset_cost(self) -> None:
        self._total_cost = 0.0

    # -- main API --

    async def complete(self, prompt: str, tier: ModelTier) -> str:
        """Send a prompt to the tier-appropriate model.

        Returns the response text. Handles rate-limit retries and cost caps.
        """
        model_id = MODEL_IDS[tier]

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.messages.create(
                    model=model_id,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                self._track_cost(response, tier)
                return response.content[0].text

            except Exception as e:
                if self._is_rate_limit(e):
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    logger.warning(
                        "HTTP 429 on %s (attempt %d/%d), retrying in %.1fs",
                        model_id,
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

        raise LLMRateLimitError(
            f"Rate limit exceeded after {MAX_RETRIES} retries for {model_id}"
        )

    # -- internals --

    def _track_cost(self, response, tier: ModelTier) -> None:
        usage = response.usage
        input_cost = (usage.input_tokens / 1000) * COST_PER_1K_INPUT[tier]
        output_cost = (usage.output_tokens / 1000) * COST_PER_1K_OUTPUT[tier]
        call_cost = input_cost + output_cost

        self._total_cost += call_cost
        if self._total_cost > self._cost_cap:
            raise LLMCostCapExceeded(
                f"Cost cap exceeded: ${self._total_cost:.4f} > ${self._cost_cap:.2f}"
            )

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status == 429:
            return True
        body = getattr(exc, "body", None)
        if isinstance(body, dict) and body.get("error", {}).get("type") == "rate_limit_error":
            return True
        return False
