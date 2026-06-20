# StratOS — Autonomous Competitive Intelligence Agent

StratOS is a multi-agent AI system that autonomously monitors competitors (currently OpenAI, Anthropic, Cohere), reasons about strategic implications using LLM-powered analysis, and delivers weekly intelligence briefings to Slack with zero human intervention.

## Live Demo

- Public URL: https://stratos-vtya.onrender.com
- API Docs: https://stratos-vtya.onrender.com/docs
- GitHub: https://github.com/sreenadh04/stratos

## Architecture

The StratOS pipeline is built as a stateful graph orchestrated through LangGraph, with full execution traces captured in LangSmith.

Scout Agent (web scraping + change detection) -> Analyst Agent (LLM signal scoring + vector dedup) -> Strategist Agent (LLM strategic reasoning) -> Writer Agent (Slack delivery)

## Tech Stack

| Area | Technology |
| --- | --- |
| Agent Framework | LangGraph |
| LLM | Groq (Llama 3.3 70B) |
| Embeddings | Google Gemini |
| Vector Memory | Qdrant Cloud |
| Database | PostgreSQL (Neon) |
| Web Scraping | Firecrawl |
| API | FastAPI |
| Observability | LangSmith |
| Deployment | Render + Docker |

## Key Features

- Autonomous multi-agent reasoning pipeline (not a single LLM call)
- Semantic deduplication using vector similarity search to avoid alert fatigue
- Full observability with LangSmith execution traces
- Production deployment with cloud-native database and vector store
- REST API for triggering runs and inspecting signal history

## How It Works

- **Scout Agent:** Scrapes competitor data and detects meaningful changes to generate raw intelligence snapshots.
- **Analyst Agent:** Uses LLM scoring and vector similarity deduplication to convert snapshots into prioritized signals.
- **Strategist Agent:** Performs strategic reasoning over signals to surface actionable implications and trends.
- **Writer Agent:** Generates concise briefings and delivers them to Slack for team consumption.

## Local Development

1. Clone repo
2. uv sync
3. Copy `.env.example` to `.env` and fill in API keys
4. docker compose up -d
5. python scripts/init_db.py
6. python scripts/seed_competitors.py
7. python scripts/run_manual.py

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | /health | Check service health |
| GET | /runs | List all pipeline runs |
| POST | /runs | Trigger a new pipeline run |
| GET | /runs/{id}/signals | Retrieve signals for a run |
| POST | /signals/{id}/evaluate | Evaluate a signal |
| GET | / | Live dashboard (HTML status page) |

## License

MIT License
