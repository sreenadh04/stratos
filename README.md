# StratOS — Autonomous Competitive Intelligence Agent

[![Live Demo](https://img.shields.io/badge/Live_Demo-View-3D8B82?style=for-the-badge&logo=render)](https://stratos-vtya.onrender.com)
[![GitHub](https://img.shields.io/badge/GitHub-View-181717?style=for-the-badge&logo=github)](https://github.com/sreenadh04/stratos)
[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python)](https://python.org)

---

## 📖 One-Line Summary

StratOS monitors competitor blogs, analyzes strategic signals using LLMs, and delivers weekly Slack briefings — with no human intervention.

**Monitored Competitors:** OpenAI · Anthropic · Cohere

---

## 🔗 Live Demo & Repository

- **Live Demo:** [stratos-vtya.onrender.com](https://stratos-vtya.onrender.com)
- **API Docs:** [stratos-vtya.onrender.com/docs](https://stratos-vtya.onrender.com/docs)
- **Source Code:** [github.com/sreenadh04/stratos](https://github.com/sreenadh04/stratos)

---

## 📸 Screenshots

*<!-- Add your dashboard screenshot here -->*
<img width="2876" height="1800" alt="image" src="https://github.com/user-attachments/assets/f6f6ceb9-d964-4e55-89d8-01a8faebbc1e" />


---

## 📚 Table of Contents

- [Problem Statement](#problem-statement)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## 🎯 Problem Statement

Founders, Product Managers, and GTM teams spend **3-5 hours every week** manually checking competitor blogs, changelogs, and announcements.

**Existing tools fail because:**
- Google Alerts can't distinguish strategic moves from routine noise
- RSS readers provide raw data, no analysis
- Manual checking is inconsistent and easy to skip

**StratOS solves this by:**
- Monitoring competitors automatically (24/7)
- Distinguishing meaningful strategic signals from noise
- Reasoning about implications for your product
- Delivering actionable intelligence via Slack
- Working without human intervention

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **4-Agent Pipeline** | Scout → Analyst → Strategist → Writer |
| 🧠 **LLM-Powered** | Groq (Llama 3.3 70B) for reasoning + Gemini for embeddings |
| 📊 **Vector Deduplication** | Qdrant with 0.98 similarity threshold |
| 🔄 **Real-Time Progress** | WebSocket + animated progress bar |
| 📈 **Live Dashboard** | Charts, competitor cards, signal feed |
| 📨 **Slack Integration** | Weekly briefings with actionable recommendations |
| ☁️ **Zero-Cost Infrastructure** | Neon, Qdrant Cloud, Render (all free tiers) |
| 🔐 **API Security** | API key authentication + rate limiting |
| 🧪 **Tested** | 13 passing tests |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Agent Framework** | LangGraph |
| **LLM (Reasoning)** | Groq (Llama 3.3 70B) |
| **Embeddings** | Google Gemini |
| **Vector Database** | Qdrant Cloud |
| **Database** | Neon PostgreSQL |
| **Web Scraping** | Firecrawl |
| **API** | FastAPI |
| **Dashboard** | HTML + CSS + Chart.js |
| **WebSocket** | FastAPI WebSocket |
| **Observability** | LangSmith |
| **Deployment** | Render |

---

## 🏗️ Architecture

### High-Level Flow

<img width="2246" height="8192" alt="architecture" src="https://github.com/user-attachments/assets/c78d6cc1-93d8-455e-b07e-ee9fd02a973f" />

### Agent Responsibilities

| Agent | Responsibility |
|-------|----------------|
| **Scout** | Scrapes competitor blogs, detects changes via SHA-256 hash |
| **Analyst** | Scores content with Groq LLM, deduplicates with Qdrant |
| **Strategist** | Reasons about strategy, generates hypotheses and recommendations |
| **Writer** | Formats and delivers briefings to Slack |

---

## 📁 Project Structure

```
stratos/
├── agents/                  # 4 specialized agents
│   ├── scout.py            # Data acquisition
│   ├── analyst.py          # LLM scoring + dedup
│   ├── strategist.py       # Strategic reasoning
│   ├── writer.py           # Slack delivery
│   └── orchestrator.py     # LangGraph pipeline
├── api/                    # FastAPI application
│   ├── main.py             # API endpoints
│   ├── auth.py             # Authentication
│   ├── dashboard.py        # Dashboard HTML
│   └── websocket.py        # Real-time WebSocket
├── db/                     # Database layer
│   ├── models.py           # SQLAlchemy models
│   ├── session.py          # Async session management
│   └── repositories.py     # Repository pattern
├── memory/                 # Vector memory
│   ├── embeddings.py       # Gemini embeddings
│   └── vector_store.py     # Qdrant client
├── tools/                  # Utilities
│   ├── scraper.py          # Firecrawl wrapper
│   └── diff.py             # SHA-256 hashing
├── scheduler/              # Weekly scheduling
│   └── job.py              # APScheduler config
├── eval/                   # Evaluation framework
│   └── metrics.py          # Precision/accuracy metrics
├── llm/                    # Provider-agnostic LLM
│   ├── factory.py          # LLM factory
│   └── providers.py        # Groq + Gemini
├── retry.py                # Retry + circuit breakers
├── logging_config.py       # Structured logging
└── config.py               # Pydantic settings
```

---

## 🚀 Installation & Setup

### Prerequisites

- Python 3.13+
- uv package manager

### Steps

```bash
# Clone the repository
git clone https://github.com/sreenadh04/stratos.git
cd stratos

# Install dependencies
uv sync

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python scripts/init_db.py

# Seed competitors
python scripts/seed_competitors.py

# Run the pipeline manually
python scripts/run_manual.py

# Start the API server
uvicorn stratos.api.main:app --reload
```

### Environment Variables

```bash
# Required
GEMINI_API_KEY=your_key
GROQ_API_KEY=your_key
FIRECRAWL_API_KEY=your_key
SLACK_WEBHOOK_URL=your_url
DATABASE_URL=your_url
QDRANT_URL=your_url
QDRANT_API_KEY=your_key
API_KEY=your_key

# Optional
LANGCHAIN_API_KEY=your_key
PRODUCT_CONTEXT="Your product description"
LLM_PROVIDER=groq
```

---

## 📖 Usage Guide

### Trigger a Run

**Via Dashboard:** Click "Run Now" button

**Via API:**
```bash
curl -H "X-API-Key: YOUR_API_KEY" -X POST http://localhost:8000/runs
```

### View Results

**Dashboard:** `http://localhost:8000`

**API:**
```bash
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/runs
```

### Check Slack

After each run, you'll receive a briefing in your Slack channel.

---

## 🔮 Future Improvements

| Improvement | Description |
|-------------|-------------|
| **GitHub Releases Monitoring** | Monitor competitor GitHub releases |
| **LinkedIn Monitoring** | Track company LinkedIn posts |
| **Human-in-the-Loop** | Approval flow for HIGH impact signals |
| **Email Digest** | Weekly email briefings |
| **Mobile App** | PWA for mobile access |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a PR

---

## 👤 Author

**Annaluru Sreenadh**

- GitHub: [@sreenadh04](https://github.com/sreenadh04)
- LinkedIn: [Annaluru Sreenadh](https://linkedin.com/in/annalurusreenadh)

---

## 🔗 Quick Links

- **Live Demo:** [stratos-vtya.onrender.com](https://stratos-vtya.onrender.com)
- **API Docs:** [stratos-vtya.onrender.com/docs](https://stratos-vtya.onrender.com/docs)
- **Source Code:** [github.com/sreenadh04/stratos](https://github.com/sreenadh04/stratos)

---

*Built with ❤️ using LangGraph, FastAPI, and Groq*
