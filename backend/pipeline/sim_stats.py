"""SimulationStats: canonical aggregation of actions.jsonl after Track 1.

Consumed by Stage 3.5 Expert Panel and Stage 4 ReACT agent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

_POSITIVE_WORDS = {
    "love", "great", "amazing", "excellent", "good", "fantastic", "wonderful",
    "game-changer", "bullish", "buy", "opportunity", "excited",
    "looking forward", "could be decent", "promising", "breakthrough", "innovative",
}
_NEGATIVE_WORDS = {
    "hate", "terrible", "awful", "bad", "worst", "disaster", "sell", "bearish",
    "crash", "worry", "concern", "fear", "risk", "overpriced", "doomed",
}


class SimulationStats(BaseModel):
    total_rounds: int = 0
    per_round_sentiment: list[dict] = []
    adoption_proxy: dict = {}
    top_content: list[dict] = []
    inflection_points: list[dict] = []
    agent_group_summary: dict = {}

    @classmethod
    def aggregate(cls, path: Path) -> "SimulationStats":
        import json

        if not path.exists() or path.stat().st_size == 0:
            return cls()

        records = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        if not records:
            return cls()

        rounds_seen = set()
        for r in records:
            rnd = r.get("round", 0)
            if isinstance(rnd, int) and rnd > 0:
                rounds_seen.add(rnd)

        per_round = []
        posts = []
        # adoption: count unique agents per action-category per round
        adoption_agents: dict[int, dict[str, set[str]]] = {}

        for rnd in sorted(rounds_seen):
            round_records = [r for r in records if r.get("round") == rnd]
            pos, neg, neu = 0, 0, 0
            agents_per_action: dict[str, set[str]] = {"early": set(), "mainstream": set(), "laggards": set()}

            for rec in round_records:
                action = rec.get("action", "")
                content = rec.get("content", "")
                agent_id = rec.get("agent_id", "")

                if action == "CREATE_POST":
                    text = content.lower()
                    if any(w in text for w in _NEGATIVE_WORDS):
                        neg += 1
                    elif any(w in text for w in _POSITIVE_WORDS):
                        pos += 1
                    else:
                        neu += 1
                    posts.append({
                        "post_id": rec.get("post_id"),
                        "content": content,
                        "likes": rec.get("num_likes", 0),
                        "shares": rec.get("num_shares", 0),
                        "agent_group": agent_id,
                        "round": rnd,
                    })
                elif action in ("LIKE_POST", "REPOST"):
                    neu += 1

                # Adoption proxy: deduplicated per agent
                if action in ("CREATE_POST", "LIKE_POST"):
                    agents_per_action["early"].add(agent_id)
                elif action == "REPOST":
                    agents_per_action["mainstream"].add(agent_id)
                elif action == "DO_NOTHING":
                    agents_per_action["laggards"].add(agent_id)

            adoption_agents[rnd] = agents_per_action

            total_sent = pos + neg + neu
            per_round.append({
                "round": rnd,
                "positive_pct": round(pos / max(total_sent, 1) * 100, 1),
                "negative_pct": round(neg / max(total_sent, 1) * 100, 1),
                "neutral_pct": round(neu / max(total_sent, 1) * 100, 1),
            })

        # Inflection points: pick the larger delta that crossed >20%
        inflections = []
        for i in range(1, len(per_round)):
            prev = per_round[i - 1]
            curr = per_round[i]
            pos_delta = abs(curr["positive_pct"] - prev["positive_pct"])
            neg_delta = abs(curr["negative_pct"] - prev["negative_pct"])

            if pos_delta > 20 or neg_delta > 20:
                if neg_delta >= pos_delta:
                    inflections.append({
                        "round": curr["round"],
                        "caused_by": "negative",
                        "shift_pct": round(neg_delta, 1),
                    })
                else:
                    inflections.append({
                        "round": curr["round"],
                        "caused_by": "positive",
                        "shift_pct": round(pos_delta, 1),
                    })

        # Top content by engagement
        top = sorted(posts, key=lambda p: p["likes"] + p["shares"], reverse=True)[:10]

        # Adoption proxy: each agent assigned to highest engagement level seen
        agent_levels: dict[str, str] = {}
        for agents in adoption_agents.values():
            for aid in agents["early"]:
                agent_levels[aid] = "early"
            for aid in agents["mainstream"]:
                if aid not in agent_levels:
                    agent_levels[aid] = "mainstream"
            for aid in agents["laggards"]:
                if aid not in agent_levels:
                    agent_levels[aid] = "laggards"

        denom = max(len(agent_levels), 1)
        adoption = {
            "early_adopters_pct": round(sum(1 for v in agent_levels.values() if v == "early") / denom * 100, 1),
            "mainstream_pct": round(sum(1 for v in agent_levels.values() if v == "mainstream") / denom * 100, 1),
            "laggards_pct": round(sum(1 for v in agent_levels.values() if v == "laggards") / denom * 100, 1),
        }

        # Agent group summary: simple prefix-based grouping
        group_counts: dict[str, int] = {}
        seen_agents = set()
        for rec in records:
            aid = rec.get("agent_id", "")
            if aid in seen_agents:
                continue
            seen_agents.add(aid)
            if aid.startswith("u_"):
                group = "consumer"
            elif aid.startswith("c_"):
                group = "competitor"
            elif aid.startswith("a_"):
                group = "analyst"
            else:
                group = "other"
            group_counts[group] = group_counts.get(group, 0) + 1

        return cls(
            total_rounds=len(rounds_seen),
            per_round_sentiment=per_round,
            adoption_proxy=adoption,
            top_content=top,
            inflection_points=inflections,
            agent_group_summary=group_counts,
        )
