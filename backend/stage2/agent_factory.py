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
    """A single agent profile for OASIS or other simulation tracks."""

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


def _build_consumer_prompt(context: dict, index: int) -> str:
    return (
        f"Generate a realistic social media user profile as valid JSON with keys: "
        f"name, username, user_char, description. "
        f"This person lives in {context.get('geography', 'US')} and is interested in "
        f"{context.get('vertical', 'tech')}. "
        f"Scenario context: {context.get('scenario', '')}. "
        f"Their personality should be diverse and unique (index {index}). "
        f"Return ONLY the JSON object, no other text."
    )


def _build_csuite_prompt(context: dict, competitor: dict, exec_type: str) -> str:
    return (
        f"Generate a realistic executive profile as valid JSON with keys: "
        f"name, username, user_char, description. "
        f"This person is the {exec_type} of {competitor.get('name', 'a company')}. "
        f"Industry: {context.get('vertical', 'tech')}. "
        f"Scenario: {context.get('scenario', '')}. "
        f"Return ONLY the JSON object, no other text."
    )


def _build_analyst_prompt(context: dict, index: int) -> str:
    return (
        f"Generate a realistic sell-side financial analyst profile as valid JSON "
        f"with keys: name, username, user_char, description. "
        f"This analyst covers the {context.get('vertical', 'tech')} sector. "
        f"Geography: {context.get('geography', 'US')}. "
        f"Scenario: {context.get('scenario', '')}. "
        f"Return ONLY the JSON object, no other text."
    )


def _parse_profile(raw: str, user_id: str, username_fallback: str) -> AgentProfile | None:
    try:
        data = json.loads(raw)
        return AgentProfile(
            user_id=user_id,
            name=data.get("name", username_fallback),
            username=data.get("username", username_fallback),
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

    Uses asyncio.Semaphore(10) to limit concurrent LLM calls.
    Individual profile failures are skipped; <80% success rate raises.
    """
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage2", "message": "Creating agent personas..."},
        )

    context = graph.raw_context or {}

    semaphore = asyncio.Semaphore(10)
    profiles: list[AgentProfile] = []

    async def _generate_one(user_id: str, prompt: str, fallback_user: str) -> AgentProfile | None:
        async with semaphore:
            try:
                raw = await llm.complete(prompt, tier=ModelTier.HAIKU)
                return _parse_profile(raw, user_id, fallback_user)
            except LLMRateLimitError:
                logger.warning("Rate limit hit for agent %s — skipping", user_id)
                return None
            except Exception:
                logger.exception("Failed to generate profile for %s", user_id)
                return None

    # Consumer agents (Haiku)
    tasks = []
    for i in range(consumer_count):
        uid = f"u_{i:03d}"
        prompt = _build_consumer_prompt(context, i)
        tasks.append(_generate_one(uid, prompt, f"user_{i}"))

    # C-suite agents (Sonnet)
    competitors = context.get("competitors", [])
    if isinstance(competitors, dict):
        competitors = [competitors]
    exec_roles = ["CEO", "CMO", "CFO", "Strategy VP", "Product VP"]
    for comp_idx, comp in enumerate(competitors[:10]):
        for role_idx, role in enumerate(exec_roles):
            if len([t for t in tasks]) >= consumer_count + csuite_count:
                break
            uid = f"c_{comp_idx:03d}_{role_idx:02d}"
            prompt = _build_csuite_prompt(context, comp, role)
            tasks.append(_generate_one(uid, prompt, f"exec_{comp_idx}_{role_idx}"))

    # Analyst agents (Sonnet)
    for i in range(analyst_count):
        uid = f"a_{i:03d}"
        prompt = _build_analyst_prompt(context, i)
        tasks.append(_generate_one(uid, prompt, f"analyst_{i}"))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, AgentProfile):
            profiles.append(r)
        elif isinstance(r, Exception):
            logger.warning("Agent generation task raised: %s", r)

    total_target = consumer_count + csuite_count + analyst_count
    threshold = int(total_target * 0.8)
    if len(profiles) < threshold:
        raise AgentFactoryError(
            f"Only {len(profiles)}/{total_target} profiles generated "
            f"(below 80% threshold of {threshold})"
        )

    csv_output = _profiles_to_csv(profiles)
    reddit_output = _profiles_to_reddit_json(profiles)

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {"stage": "stage2", "agent_count": len(profiles)},
        )

    return AgentGenerationResult(
        twitter_profiles_csv=csv_output,
        reddit_profiles_json=reddit_output,
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
    items = []
    for p in profiles:
        items.append({
            "realname": p.name,
            "username": p.username,
            "bio": p.description,
            "persona": p.user_char,
            "age": 30,
            "gender": "unspecified",
            "mbti": "INTJ",
            "country": "US",
        })
    return json.dumps(items)
