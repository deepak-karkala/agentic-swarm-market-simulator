"""Mock LLM client returning deterministic fixture responses for tests."""

from __future__ import annotations

from backend.llm.client import LLMCostCapExceeded, ModelTier


class MockFixtureMissing(Exception):
    """Raised when no fixture response is configured for a given prompt."""


class MockLLMClient:
    """Drop-in replacement for LLMClient in tests. No real API calls.

    Fixture responses are keyed by prompt prefix — the longest matching
    prefix in the ``responses`` dict is returned.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        cost_per_call: float = 0.0,
        cost_cap: float = 10.0,
    ):
        self._responses: dict[str, str] = dict(responses or {})
        self._cost_per_call = cost_per_call
        self._cost_cap = cost_cap
        self._total_cost = 0.0

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost

    def reset_cost(self) -> None:
        self._total_cost = 0.0

    async def complete(self, prompt: str, tier: ModelTier) -> str:
        """Return the fixture response whose key is the longest prefix match."""
        match = ""
        for key, value in self._responses.items():
            if prompt.startswith(key) and len(key) > len(match):
                match = key

        if not match:
            raise MockFixtureMissing(
                f"No fixture found for prompt: {prompt[:64]}..."
            )

        self._total_cost += self._cost_per_call
        if self._total_cost > self._cost_cap:
            raise LLMCostCapExceeded(
                f"Cost cap exceeded: ${self._total_cost:.4f} > ${self._cost_cap:.2f}"
            )

        return self._responses[match]
