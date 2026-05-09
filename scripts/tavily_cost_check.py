#!/usr/bin/env python3
"""
Task 0.2: Tavily API Cost Validation
Runs 6 parallel search queries for the Apple EV scenario, measures cost.
Decision rule: <=$0.30/sim -> 6 pipelines, $0.31-$0.75 -> 4 pipelines, >$0.75 -> redesign.

Source: https://docs.tavily.com (pricing: $0.008/credit, basic=1 credit, advanced=2 credits)
"""

import os
import sys
import time
from pathlib import Path

from scripts._utils import load_dotenv

SCENARIO = "Apple launches an electric vehicle at $35,000"
GEOGRAPHY = "United States"
VERTICAL = "auto"

PIPELINE_QUERIES = [
    ("competitors", f"{SCENARIO} competitors market share 2025"),
    ("historical", "electric vehicle new entrant market disruption historical examples"),
    ("geographic", f"{GEOGRAPHY} {VERTICAL} consumer behavior EV adoption 2025"),
    ("regulatory", f"{GEOGRAPHY} {VERTICAL} regulatory environment subsidies mandates 2025"),
    ("kols", f"{VERTICAL} industry key opinion leaders analysts influencers {GEOGRAPHY}"),
    ("macro", f"{GEOGRAPHY} macroeconomic conditions interest rates consumer confidence 2025"),
]

CREDIT_COST = 0.008  # USD per credit


def theoretical_estimate():
    """Estimate cost from documented pricing without making API calls."""
    print("TAVILY_API_KEY not set. Using documented pricing for estimate.\n")
    print(f"Pricing: ${CREDIT_COST}/credit, basic search = 1 credit/query")
    print(f"Queries per simulation: {len(PIPELINE_QUERIES)}")
    print()

    basic_cost = len(PIPELINE_QUERIES) * 1 * CREDIT_COST
    advanced_cost = len(PIPELINE_QUERIES) * 2 * CREDIT_COST

    print(f"{'Depth':<12} {'Credits':<8} {'Cost/sim':<10}")
    print("-" * 30)
    print(f"{'basic':<12} {len(PIPELINE_QUERIES):<8} ${basic_cost:.4f}")
    print(f"{'advanced':<12} {len(PIPELINE_QUERIES) * 2:<8} ${advanced_cost:.4f}")
    print()

    print(f"Decision: ${basic_cost:.4f}-${advanced_cost:.4f}/sim <= $0.30 threshold")
    print("-> PROCEED WITH ALL 6 PIPELINES")
    print()
    print("NOTE: Verification requires TAVILY_API_KEY in .env.")
    print("      Free tier: 1,000 credits/month at https://tavily.com")
    return basic_cost


def run_live_test():
    """Run actual queries and measure cost via include_usage."""
    from tavily import TavilyClient

    api_key = os.environ["TAVILY_API_KEY"]
    client = TavilyClient(api_key=api_key)

    print(f"Running {len(PIPELINE_QUERIES)} queries against Tavily API...")
    print(f"Search depth: basic (1 credit each)\n")

    total_credits = 0
    total_time = 0.0
    results = {}

    for name, query in PIPELINE_QUERIES:
        t0 = time.monotonic()
        try:
            # NOTE: topic="news" + time_range="month" is appropriate for news-driven pipelines
            # (competitors, KOLs, macro). The regulatory pipeline may miss older policy docs.
            # Stage 0 implementation: regulatory pipeline should use topic="general" and no
            # time_range to surface multi-year regulatory documents. Cost is unaffected (1 credit).
            resp = client.search(
                query=query,
                search_depth="basic",
                max_results=3,
                include_usage=True,
                topic="news",
                time_range="month",
            )
            elapsed = time.monotonic() - t0
            credits = resp.get("usage", {}).get("credits", 1)
            result_count = len(resp.get("results", []))
            total_credits += credits
            total_time += elapsed
            results[name] = f"{credits} credit(s), {result_count} results, {elapsed:.1f}s"
            print(f"  [{name:>12}] {results[name]}")
        except Exception as e:
            elapsed = time.monotonic() - t0
            results[name] = f"ERROR: {e}"
            print(f"  [{name:>12}] ERROR: {e} ({elapsed:.1f}s)")

    cost = total_credits * CREDIT_COST
    print(f"\n{'='*50}")
    print(f"Total credits: {total_credits}")
    print(f"Total cost:    ${cost:.4f}")
    print(f"Total time:    {total_time:.1f}s")
    print(f"Per-sim cost:  ${cost:.4f}")
    print()

    if cost <= 0.30:
        print("DECISION: <= $0.30/sim -> PROCEED WITH ALL 6 PIPELINES")
    elif cost <= 0.75:
        print("DECISION: $0.31-$0.75/sim -> REDUCE TO 4 PIPELINES (drop geo + macro)")
    else:
        print("DECISION: > $0.75/sim -> REDESIGN STAGE 0")
    return cost


def main():
    load_dotenv()

    print("=" * 50)
    print("TAVILY API COST VALIDATION — Task 0.2")
    print(f"Scenario: {SCENARIO}")
    print(f"Geography: {GEOGRAPHY}, Vertical: {VERTICAL}")
    print("=" * 50)
    print()

    if os.environ.get("TAVILY_API_KEY"):
        run_live_test()
    else:
        theoretical_estimate()


if __name__ == "__main__":
    main()
