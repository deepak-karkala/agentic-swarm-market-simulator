"""Stage 2: Agent Factory — generates OASIS + C-suite + analyst profiles."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel

from backend.llm.client import LLMClient, LLMRateLimitError, ModelTier
from backend.stage1.graph_builder import GraphResult

logger = logging.getLogger(__name__)


class AgentProfile(BaseModel):
    user_id: str
    name: str
    username: str
    user_char: str
    description: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "username": self.username,
            "user_char": self.user_char,
            "description": self.description,
        }


class AgentFactoryError(Exception):
    """Raised when profile generation falls below the minimum threshold."""


def _prompt_consumer(context: dict, index: int) -> str:
    return (
        f"Generate a realistic social media user profile as valid JSON with keys: "
        f"name, username, user_char, description. "
        f"Person lives in {context.get('geography', 'US')}, interested in "
        f"{context.get('vertical', 'tech')}. Scenario: {context.get('scenario', '')}. "
        f"Index {index} for diversity. Return ONLY JSON."
    )


def _prompt_csuite(context: dict, competitor: dict, role: str, idx: int) -> str:
    return (
        f"Generate an executive profile as valid JSON with keys: "
        f"name, username, user_char, description. "
        f"{role} of {competitor.get('name', 'a company')}. "
        f"Industry: {context.get('vertical', 'tech')}. "
        f"Scenario: {context.get('scenario', '')}. "
        f"Index {idx} for diversity. Return ONLY JSON."
    )


def _prompt_analyst(context: dict, index: int) -> str:
    return (
        f"Generate a sell-side analyst profile as valid JSON with keys: "
        f"name, username, user_char, description. "
        f"Covers {context.get('vertical', 'tech')} sector. "
        f"Geography: {context.get('geography', 'US')}. "
        f"Scenario: {context.get('scenario', '')}. "
        f"Index {index} for diversity. Return ONLY JSON."
    )


def _parse_profile(raw: str, user_id: str, fallback: str) -> AgentProfile | None:
    try:
        data = json.loads(raw)
        return AgentProfile(
            user_id=user_id,
            name=data.get("name", fallback),
            username=data.get("username", fallback),
            user_char=data.get("user_char", data.get("description", "")),
            description=data.get("description", data.get("user_char", "")),
        )
    except (json.JSONDecodeError, ValueError):
        return None


@dataclass
class AgentGenerationResult:
    twitter_profiles_csv: str
    reddit_profiles_json: str
    total_agents: int


async def generate_agents(
    graph: GraphResult,
    llm: LLMClient,
    consumer_count: int = 200,
    csuite_count: int = 50,
    analyst_count: int = 10,
    sim_id: str | None = None,
) -> AgentGenerationResult:
    """Generate all agent profiles for the simulation.

    - Consumer profiles: Haiku (high volume, low cost)
    - C-suite + Analyst profiles: Sonnet (quality matters)
    - asyncio.Semaphore(10) limits concurrent LLM calls
    - Individual failures are skipped; <80% total raises AgentFactoryError
    """
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage2", "message": "Creating agent personas..."},
        )

    context = graph.raw_context or {}
    sem = asyncio.Semaphore(10)

    async def _generate(user_id: str, prompt: str, tier: ModelTier) -> AgentProfile | None:
        async with sem:
            try:
                raw = await llm.complete(prompt, tier=tier)
                return _parse_profile(raw, user_id, "agent")
            except LLMRateLimitError:
                logger.warning("Rate limit for agent %s — skipping", user_id)
                return None
            except Exception:
                logger.exception("Failed to generate profile for %s", user_id)
                return None

    tasks: list[tuple[str, ModelTier, str | None]] = []

    # Consumer agents (Haiku)
    for i in range(consumer_count):
        uid = f"u_{i:03d}"
        prompt = _prompt_consumer(context, i)
        tasks.append((uid, ModelTier.HAIKU, prompt))

    # C-suite agents (Sonnet)
    competitors = context.get("competitors", [])
    if isinstance(competitors, dict):
        competitors = [competitors]
    exec_roles = ["CEO", "CMO", "CFO", "Strategy VP", "Product VP"]
    cs_generated = 0
    for comp in competitors:
        for role in exec_roles:
            if cs_generated >= csuite_count:
                break
            uid = f"c_{cs_generated:03d}"
            prompt = _prompt_csuite(context, comp, role, cs_generated)
            tasks.append((uid, ModelTier.SONNET, prompt))
            cs_generated += 1
        if cs_generated >= csuite_count:
            break

    # Analyst agents (Sonnet)
    for i in range(analyst_count):
        uid = f"a_{i:03d}"
        prompt = _prompt_analyst(context, i)
        tasks.append((uid, ModelTier.SONNET, prompt))

    scheduled_count = len(tasks)
    threshold = int(scheduled_count * 0.8)

    futures = [asyncio.ensure_future(_generate(uid, prompt, tier)) for uid, tier, prompt in tasks]
    done, _ = await asyncio.wait(futures)

    profiles: list[AgentProfile] = []
    for f in done:
        r = f.result()
        if isinstance(r, AgentProfile):
            profiles.append(r)

    if len(profiles) < threshold:
        raise AgentFactoryError(
            f"Only {len(profiles)}/{scheduled_count} profiles generated "
            f"(below 80% threshold of {threshold})"
        )

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {"stage": "stage2", "agent_count": len(profiles)},
        )

    return AgentGenerationResult(
        twitter_profiles_csv=_profiles_to_csv(profiles),
        reddit_profiles_json=_profiles_to_reddit_json(profiles),
        total_agents=len(profiles),
    )


def _profiles_to_csv(profiles: list[AgentProfile]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["user_id", "name", "username", "user_char", "description"])
    writer.writeheader()
    for p in profiles:
        writer.writerow(p.to_csv_row())
    return buf.getvalue()


def _profiles_to_reddit_json(profiles: list[AgentProfile]) -> str:
    return json.dumps([
        {
            "user_id": p.user_id,
            "username": p.username,
            "name": p.name,
            "bio": p.description,
            "persona": p.user_char,
            "karma": 1000,
            "age": 30,
            "gender": "unspecified",
            "mbti": "INTJ",
            "country": "US",
        }
        for p in profiles
    ])
