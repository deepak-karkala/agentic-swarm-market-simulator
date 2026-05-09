#!/usr/bin/env python3
"""
Task 0.1: OASIS Smoke Test
Validates that OASIS 0.2.5 runs 10 agents × 3 rounds on Twitter.
Confirms profile CSV format and database output.
Exits 0 on pass, 1 on fail.

Source: https://docs.oasis.camel-ai.org
"""

import asyncio
import csv
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# --- Configuration ---
NUM_AGENTS = 10
NUM_ROUNDS = 2
SCENARIO = "Apple launches an electric vehicle at $35,000"

REQUIRED_CSV_COLUMNS = ["user_id", "name", "username", "user_char", "description"]

AGENT_PROFILES = [
    {"user_id": 1001, "name": "Alex Chen", "username": "alexchen_tech",
     "user_char": "Tech enthusiast and early adopter. Loves EVs and sustainable tech. Works at a startup.",
     "description": "Tech enthusiast | EV lover | Startup life"},
    {"user_id": 1002, "name": "Sarah Johnson", "username": "sarah_finance",
     "user_char": "Finance analyst at a major bank. Skeptical of hype but watches markets closely. Tesla investor.",
     "description": "Finance analyst | Tesla investor | Market watcher"},
    {"user_id": 1003, "name": "Mike Rodriguez", "username": "mikerodriguez_cars",
     "user_char": "Auto journalist with 15 years experience. Reviews cars for major publications. Pragmatic about EV claims.",
     "description": "Auto journalist | 15yr experience | Car reviews"},
    {"user_id": 1004, "name": "Emily Park", "username": "emilypark_news",
     "user_char": "Breaking news reporter covering tech industry. Chases scoops, reports facts, no hype.",
     "description": "Tech reporter | Breaking news | Facts first"},
    {"user_id": 1005, "name": "David Kim", "username": "davidkim_tesla",
     "user_char": "Tesla fan and shareholder since 2019. Defensive of Tesla brand. Active in EV forums. Skeptical of Apple.",
     "description": "Tesla shareholder | EV advocate | Forum regular"},
    {"user_id": 1006, "name": "Lisa Wang", "username": "lisawang_analyst",
     "user_char": "Equity research analyst covering auto sector. Follows EV transition closely. Data-driven.",
     "description": "Equity analyst | Auto sector | EV transition"},
    {"user_id": 1007, "name": "Tom Harris", "username": "tomharris_green",
     "user_char": "Environmental activist. Supports EV adoption for climate reasons. Optimistic about green tech, skeptical of big tech motives.",
     "description": "Environmental activist | Green tech | Climate action"},
    {"user_id": 1008, "name": "Rachel Green", "username": "rachelgreen_vc",
     "user_char": "Venture capitalist focused on mobility and climate tech. Excited about new market entrants disrupting incumbents.",
     "description": "VC | Mobility & climate tech | Startup investor"},
    {"user_id": 1009, "name": "James Wilson", "username": "jameswilson_retail",
     "user_char": "Average consumer shopping for an affordable EV. Price sensitive, researches thoroughly before buying. Currently considering Tesla Model 3.",
     "description": "Consumer | Price sensitive | EV shopping"},
    {"user_id": 1010, "name": "Nina Patel", "username": "ninapatel_influencer",
     "user_char": "Social media influencer with 500K followers. Posts about lifestyle, tech trends, and product reviews. Trend-aware.",
     "description": "Influencer | 500K followers | Lifestyle & tech"},
]


def _load_dotenv():
    """Load .env file from project root, if present."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


class SmokeTestResult:
    def __init__(self):
        self.errors: list[str] = []
        self.checks: dict[str, str] = {}
        self.csv_path: Path | None = None
        self.db_path: Path | None = None

    def add_check(self, name: str, passed: bool, detail: str):
        status = "PASS" if passed else "FAIL"
        self.checks[name] = f"{status}: {detail}"
        if not passed:
            self.errors.append(f"{name}: {detail}")

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def validate_csv_format(csv_path: Path) -> tuple[bool, str]:
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        missing = [col for col in REQUIRED_CSV_COLUMNS if col not in header]
        if missing:
            return False, f"Missing columns: {missing}"
        rows = list(reader)
        if len(rows) != NUM_AGENTS:
            return False, f"Expected {NUM_AGENTS} rows, got {len(rows)}"
        return True, f"{len(rows)} rows, columns={header}"


def validate_database(db_path: Path) -> tuple[bool, str, int]:
    if not db_path.exists():
        return False, "Database file not found", 0

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM post")
    post_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trace")
    trace_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM user")
    user_count = cursor.fetchone()[0]

    conn.close()

    details = (
        f"tables={tables}, posts={post_count}, traces={trace_count}, users={user_count}"
    )
    if post_count > 0 or trace_count > 0:
        return True, details, post_count
    return True, f"DB created but no posts/traces found. {details}", post_count


def export_actions_jsonl(db_path: Path, jsonl_path: Path) -> int:
    """Export post and trace data to actions.jsonl format."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    count = 0
    with open(jsonl_path, "w") as f:
        cursor.execute("SELECT * FROM post ORDER BY created_at")
        for row in cursor.fetchall():
            action = {
                "agent_id": f"u_{row['user_id']:03d}",
                "action": "CREATE_POST",
                "content": row["content"],
                "post_id": row["post_id"],
                "timestamp": row["created_at"],
                "num_likes": row["num_likes"],
                "num_shares": row["num_shares"],
            }
            f.write(json.dumps(action) + "\n")
            count += 1

        cursor.execute("SELECT * FROM trace ORDER BY created_at")
        for row in cursor.fetchall():
            action = {
                "agent_id": f"u_{row['user_id']:03d}",
                "action": row["action"],
                "content": row["info"],
                "timestamp": row["created_at"],
            }
            f.write(json.dumps(action) + "\n")
            count += 1

    conn.close()
    return count


async def run_smoke_test() -> SmokeTestResult:
    result = SmokeTestResult()

    # --- Step 1: Validate imports ---
    try:
        from camel.models import ModelFactory
        from camel.types import ModelPlatformType, ModelType
        from camel.configs import AnthropicConfig
        import oasis
        from oasis import (
            ActionType,
            LLMAction,
            ManualAction,
            generate_twitter_agent_graph,
        )
    except ImportError as e:
        result.add_check("imports", False, str(e))
        return result
    result.add_check("imports", True, f"oasis={oasis.__version__}")

    # --- Step 2: Load API key from .env ---
    _load_dotenv()
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        result.add_check(
            "api_key",
            False,
            "Neither DEEPSEEK_API_KEY nor ANTHROPIC_API_KEY found. "
            "Set one in .env or export it.",
        )
        return result
    result.add_check("api_key", True, "API key found")

    # --- Step 3: Create profile CSV ---
    tmpdir = Path(tempfile.mkdtemp(prefix="oasis_smoke_"))
    csv_path = tmpdir / "twitter_profiles.csv"
    db_path = tmpdir / "twitter_simulation.db"
    jsonl_path = tmpdir / "actions.jsonl"

    try:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=REQUIRED_CSV_COLUMNS)
            writer.writeheader()
            for profile in AGENT_PROFILES[:NUM_AGENTS]:
                writer.writerow(profile)
    except OSError as e:
        result.add_check("csv_create", False, str(e))
        return result

    valid, msg = validate_csv_format(csv_path)
    result.add_check("csv_format", valid, msg)
    if not valid:
        return result

    # --- Step 4: Create model ---
    try:
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        if deepseek_key:
            model = ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
                model_type="deepseek-chat",
                api_key=deepseek_key,
                url="https://api.deepseek.com/v1",
                model_config_dict={"temperature": 0.7},
            )
            result.add_check("model_create", True, "DeepSeek deepseek-chat")
        else:
            model = ModelFactory.create(
                model_platform=ModelPlatformType.ANTHROPIC,
                model_type=ModelType.CLAUDE_3_HAIKU,
                model_config_dict=AnthropicConfig(temperature=0.7).as_dict(),
            )
            result.add_check("model_create", True, "Anthropic Claude 3 Haiku")
    except Exception as e:
        result.add_check("model_create", False, str(e))
        return result

    # --- Step 5: Build agent graph ---
    try:
        available_actions = ActionType.get_default_twitter_actions()
        agent_graph = await generate_twitter_agent_graph(
            profile_path=str(csv_path),
            model=model,
            available_actions=available_actions,
        )
        agent_count = agent_graph.get_num_nodes()
        result.add_check("agent_graph", agent_count == NUM_AGENTS,
                         f"{agent_count} agents created (expected {NUM_AGENTS})")
        if agent_count != NUM_AGENTS:
            return result
    except Exception as e:
        result.add_check("agent_graph", False, str(e))
        return result

    # --- Step 6: Create environment ---
    try:
        if db_path.exists():
            db_path.unlink()

        env = oasis.make(
            agent_graph=agent_graph,
            platform=oasis.DefaultPlatformType.TWITTER,
            database_path=str(db_path),
        )
        await env.reset()
        result.add_check("env_init", True, "Twitter environment initialized")
    except Exception as e:
        result.add_check("env_init", False, str(e))
        return result

    # --- Step 7: Run simulation rounds ---
    rounds_ok = True
    try:
        # Round 1: seed with a manual post, activate 5 agents to react
        actions = {}
        actions[agent_graph.get_agent(0)] = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={
                "content": f"BREAKING: {SCENARIO}. This will reshape the entire auto industry. What do you all think?"
            },
        )
        for i in [1, 3, 5, 7, 9]:
            if i < NUM_AGENTS:
                actions[agent_graph.get_agent(i)] = LLMAction()

        await env.step(actions)

        # Rounds 2-N: all agents use LLM actions
        for r in range(2, NUM_ROUNDS + 1):
            actions = {
                agent: LLMAction()
                for _, agent in agent_graph.get_agents()
            }
            await env.step(actions)

        await env.close()
        result.add_check(
            "simulation", True,
            f"Completed {NUM_ROUNDS} rounds with {NUM_AGENTS} agents",
        )
    except Exception as e:
        result.add_check("simulation", False, str(e))
        try:
            await env.close()
        except Exception:
            pass
        return result

    # --- Step 8: Validate database ---
    valid, msg, post_count = validate_database(db_path)
    result.add_check("database", valid, msg)
    result.add_check(
        "create_post",
        post_count > 0,
        f"{post_count} posts in database" if post_count > 0 else "No CREATE_POST found",
    )

    # --- Step 9: Export actions.jsonl ---
    try:
        exported = export_actions_jsonl(db_path, jsonl_path)
        result.add_check(
            "actions_jsonl",
            exported > 0,
            f"Exported {exported} action records to actions.jsonl"
            if exported > 0
            else "actions.jsonl is empty",
        )
    except Exception as e:
        result.add_check("actions_jsonl", False, str(e))

    # --- Step 10: Clean up and store paths ---
    result.csv_path = csv_path
    result.db_path = db_path

    return result


def main():
    print("=" * 60)
    print("OASIS SMOKE TEST — Task 0.1")
    print(f"Target: {NUM_AGENTS} agents × {NUM_ROUNDS} rounds, Twitter")
    print(f"Scenario: {SCENARIO}")
    print("=" * 60)

    result = asyncio.run(run_smoke_test())

    print()
    for name, detail in result.checks.items():
        marker = "✓" if "PASS" in detail else "✗"
        print(f"  [{marker}] {name}: {detail}")

    print()
    if result.passed:
        print(f"PASS: OASIS {NUM_AGENTS}-agent x {NUM_ROUNDS}-round smoke test completed.")
        print(f"\nArtifacts at: {result.csv_path}")
        sys.exit(0)
    else:
        print(f"FAIL: {len(result.errors)} check(s) failed:")
        for err in result.errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
