"""SimulationStats: canonical aggregation of actions.jsonl after Track 1.

Consumed by Stage 3.5 Expert Panel and Stage 4 ReACT agent.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

_POSITIVE_WORDS = {
    "love", "great", "amazing", "excellent", "good", "fantastic", "wonderful",
    "game-changer", "bullish", "buy", "opportunity", "excited", "looking forward",
    "could be decent", "promising", "breakthrough", "innovative",
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
        adoption_counts = {"early": 0, "mainstream": 0, "laggards": 0, "total": 0}

        for rnd in sorted(rounds_seen):
            round_records = [r for r in records if r.get("round") == rnd]
            pos, neg, neu = 0, 0, 0

            for rec in round_records:
                action = rec.get("action", "")
                content = rec.get("content", "")

                # Sentiment classification
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
                        "agent_group": rec.get("agent_id", ""),
                        "round": rnd,
                    })
                elif action in ("LIKE_POST", "REPOST"):
                    # Non-post actions count as sentiment-aligned to the round
                    neu += 1

                # Adoption proxy
                if action in ("CREATE_POST", "LIKE_POST"):
                    adoption_counts["early"] += 1
                elif action == "REPOST":
                    adoption_counts["mainstream"] += 1
                elif action == "DO_NOTHING":
                    adoption_counts["laggards"] += 1
                adoption_counts["total"] += 1

            total_sent = pos + neg + neu
            per_round.append({
                "round": rnd,
                "positive_pct": round(pos / max(total_sent, 1) * 100, 1),
                "negative_pct": round(neg / max(total_sent, 1) * 100, 1),
                "neutral_pct": round(neu / max(total_sent, 1) * 100, 1),
                "by_agent_group": {},
            })

        # Inflection points: >20% shift in positive_pct between consecutive rounds
        inflections = []
        for i in range(1, len(per_round)):
            prev_pos = per_round[i - 1]["positive_pct"]
            curr_pos = per_round[i]["positive_pct"]
            prev_neg = per_round[i - 1]["negative_pct"]
            curr_neg = per_round[i]["negative_pct"]
            if abs(curr_pos - prev_pos) > 20 or abs(curr_neg - prev_neg) > 20:
                inflections.append({
                    "round": per_round[i]["round"],
                    "caused_by": "positive" if curr_pos > prev_pos else "negative",
                    "shift_pct": round(abs(curr_pos - prev_pos), 1),
                })

        # Top content by engagement
        top = sorted(posts, key=lambda p: p["likes"] + p["shares"], reverse=True)[:10]

        # Adoption proxy percentages
        total_act = max(adoption_counts["total"], 1)
        adoption = {
            "early_adopters_pct": round(adoption_counts["early"] / total_act * 100, 1),
            "mainstream_pct": round(adoption_counts["mainstream"] / total_act * 100, 1),
            "laggards_pct": round(adoption_counts["laggards"] / total_act * 100, 1),
            "by_price_sensitivity": {},
        }

        return cls(
            total_rounds=len(rounds_seen),
            per_round_sentiment=per_round,
            adoption_proxy=adoption,
            top_content=top,
            inflection_points=inflections,
            agent_group_summary={"consumer": adoption_counts["total"]},
        )
