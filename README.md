# Agentic Market Simulator

A market intelligence platform that simulates how business scenarios propagate through markets using hundreds of AI agents. Type a scenario, and in minutes 200 culturally-calibrated agents simulate the cascade across social media, boardrooms, and analyst desks — producing a business impact report with McKinsey-level analytical depth.

**Core differentiator:** Emergent behavior simulation. Agent-agent interactions over time produce market dynamics that no survey or focus group can predict. This is a flight simulator, not a synthetic focus group.

## How It Works

```
Scenario Input → Reality Seeding → Knowledge Graph → Agent Factory
→ 3-Track Parallel Simulation (Social / Boardroom / Analyst Desk)
→ Expert Panel Analysis → ReACT Synthesizer → 10-Section Business Report
```

1. **Reality Seeding** — 6 parallel web search pipelines gather competitive intel, historical precedents, geographic context, regulatory environment, KOL networks, and macroeconomic signals
2. **Graph Building** — Zep Cloud GraphRAG constructs an entity graph from the enriched context
3. **Agent Factory** — 200+ AI agents with geo-calibrated personas (consumers, C-suite executives, analysts, KOLs)
4. **3-Track Simulation** — Public narrative (Twitter/Reddit) + Boardroom deliberation + Analyst desk run concurrently
5. **Expert Panel** — 5 specialist agents (competitive strategy, economics, consumer behavior, domain expert, regulatory) interpret simulation outputs
6. **ReACT Synthesizer** — Assembles everything into a 10-section business impact report

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite |
| Backend | FastAPI 0.110+ (asyncio) |
| Knowledge Graph | Zep Cloud GraphRAG |
| Multi-Agent Sim | CAMEL-AI OASIS 0.2.5 |
| LLMs | Claude Haiku (high-volume) + Sonnet (quality) |
| Search | Tavily API |
| Styling | Plain CSS + CSS Modules |

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Anthropic API key
- Tavily API key
- Zep Cloud API key

### Backend

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
pytest backend/tests/ -v
```

## Status

Phase 0 — Validation gates in progress. Phase 1 target: end-to-end pipeline with Apple EV reference scenario.

## License

MIT
