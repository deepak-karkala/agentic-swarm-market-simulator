"""Tests for LLMClient router, backoff, cost tracking, and MockLLMClient."""

import pytest

from backend.llm.client import (
    LLMClient,
    LLMCostCapExceeded,
    LLMRateLimitError,
    MODEL_IDS,
    ModelTier,
)
from backend.llm.mock_client import MockLLMClient, MockFixtureMissing


def _make_response(text="ok", input_tokens=100, output_tokens=50):
    """Build a fake Anthropic response object for test monkeypatching."""
    return type(
        "FakeResponse",
        (),
        {
            "content": [type("FakeBlock", (), {"text": text})()],
            "usage": type("FakeUsage", (), {"input_tokens": input_tokens, "output_tokens": output_tokens})(),
        },
    )()


class TestModelTier:
    def test_haiku_routes_to_correct_model_id(self):
        assert MODEL_IDS[ModelTier.HAIKU] == "claude-haiku-4-5-20251001"

    def test_sonnet_routes_to_correct_model_id(self):
        assert MODEL_IDS[ModelTier.SONNET] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_complete_passes_model_to_api(self, monkeypatch):
        received_model = None

        async def mock_create(*args, **kwargs):
            nonlocal received_model
            received_model = kwargs.get("model")
            return _make_response()

        monkeypatch.setattr(
            "anthropic.resources.messages.AsyncMessages.create",
            mock_create,
        )

        client = LLMClient(api_key="fake-key")
        client._cost_cap = 999.0

        await client.complete("test", tier=ModelTier.HAIKU)
        assert received_model == "claude-haiku-4-5-20251001"

        await client.complete("test", tier=ModelTier.SONNET)
        assert received_model == "claude-sonnet-4-6"


class TestMockLLMClient:
    @pytest.mark.asyncio
    async def test_returns_fixture_by_key(self):
        client = MockLLMClient(responses={"test-prompt": '{"result": "ok"}'})

        result = await client.complete("test-prompt", tier=ModelTier.HAIKU)

        assert result == '{"result": "ok"}'

    @pytest.mark.asyncio
    async def test_raises_on_missing_fixture(self):
        client = MockLLMClient(responses={})

        with pytest.raises(MockFixtureMissing):
            await client.complete("unknown-prompt", tier=ModelTier.HAIKU)

    @pytest.mark.asyncio
    async def test_key_matches_by_prefix(self):
        client = MockLLMClient(responses={"hello world": "found"})

        result = await client.complete("hello world and more text", tier=ModelTier.HAIKU)

        assert result == "found"

    @pytest.mark.asyncio
    async def test_accumulates_cost_from_fixture(self):
        client = MockLLMClient(
            responses={"prompt-a": "response-a"},
            cost_per_call=0.05,
        )

        await client.complete("prompt-a", tier=ModelTier.HAIKU)
        await client.complete("prompt-a", tier=ModelTier.SONNET)

        assert client.total_cost_usd == pytest.approx(0.10)

    def test_reset_cost(self):
        client = MockLLMClient(
            responses={"prompt-a": "response-a"},
            cost_per_call=0.05,
        )
        client._total_cost = 1.00
        client.reset_cost()
        assert client.total_cost_usd == 0.0


class TestLLMClientRateLimit:
    @pytest.mark.asyncio
    async def test_retries_on_429_then_succeeds(self, monkeypatch):
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                exc = Exception("rate limited")
                exc.status_code = 429
                raise exc
            return _make_response(text="success")

        monkeypatch.setattr(
            "anthropic.resources.messages.AsyncMessages.create",
            mock_create,
        )

        client = LLMClient(api_key="fake-key")

        result = await client.complete("test", tier=ModelTier.HAIKU)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_three_attempts_fail_raises_rate_limit_error(self, monkeypatch):
        async def mock_create(*args, **kwargs):
            exc = Exception("rate limited")
            exc.status_code = 429
            raise exc

        monkeypatch.setattr(
            "anthropic.resources.messages.AsyncMessages.create",
            mock_create,
        )

        client = LLMClient(api_key="fake-key")

        with pytest.raises(LLMRateLimitError):
            await client.complete("test", tier=ModelTier.HAIKU)


class TestLLMClientCostTracking:
    @pytest.mark.asyncio
    async def test_cost_accumulates_from_response(self, monkeypatch):
        async def mock_create(*args, **kwargs):
            return _make_response(input_tokens=1000, output_tokens=100)

        monkeypatch.setattr(
            "anthropic.resources.messages.AsyncMessages.create",
            mock_create,
        )

        client = LLMClient(api_key="fake-key")
        client._cost_cap = 999.0

        await client.complete("test", tier=ModelTier.HAIKU)

        # Haiku: $0.00025/1K input + $0.00125/1K output
        expected = (1000 / 1000) * 0.00025 + (100 / 1000) * 0.00125
        assert client.total_cost_usd == pytest.approx(expected, rel=1e-3)

    @pytest.mark.asyncio
    async def test_cost_cap_raises_error(self, monkeypatch):
        async def mock_create(*args, **kwargs):
            return _make_response(input_tokens=1_000_000, output_tokens=500_000)

        monkeypatch.setattr(
            "anthropic.resources.messages.AsyncMessages.create",
            mock_create,
        )

        client = LLMClient(api_key="fake-key")
        client._cost_cap = 1.0

        with pytest.raises(LLMCostCapExceeded):
            await client.complete("test", tier=ModelTier.SONNET)
