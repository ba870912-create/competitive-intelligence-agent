# 📊 Competitive Intelligence & Market Watch Agent

A multi-agent system that autonomously tracks named SaaS competitors' pricing, product announcements, and hiring trends — cross-checks every claim across sources, models the results as a knowledge graph, and delivers a cited executive brief with a week-over-week change log.

Built with **LangGraph**, **FastMCP**, **Neo4j**, **Qdrant**, and **Streamlit**, running on either local models (**Ollama**) or hosted inference (**Groq**).

---

## 🎯 Problem

Companies need continuously updated, verified intelligence on competitors, but manual market research is slow, inconsistent, and often relies on stale reports pulled together once a quarter. Real-time, source-verified competitive intelligence lets leadership react to pricing moves, product launches, and market shifts within days instead of months.

## 🧠 How It Works

Five agents run in a sequential/parallel LangGraph pipeline, each with a single responsibility:

| Agent | Role |
|---|---|
| **Research Agent** | Pulls live pricing pages, careers pages, and news via MCP tool calls; renders JavaScript-heavy pages with Playwright and extracts structured claims with an LLM |
| **Fact-Checker Agent** | Cross-references claims across independent sources; first-party pricing/hiring data is trusted, announcements need 2+ corroborating domains |
| **Graph-Builder Agent** | Converts verified claims into `Competitor → Relation → Object` triples in Neo4j, and embeds free-text announcements into Qdrant for semantic search |
| **Alerting Agent** | Scans verified claims for high-impact events (acquisitions, funding, layoffs) and pings Slack immediately — independent of the weekly cycle |
| **Analyst/Synthesizer Agent** | Runs GraphRAG — combines Cypher graph traversal with vector semantic search — to write a structured, cited executive brief |
| **Change-Log Agent** | Diffs this run's graph state against the last stored snapshot and surfaces a "What's New" section |

```
Research → Fact-Check ─┬─→ Graph-Builder ─┐
                        └─→ Alerting       ├─→ Analyst → Change-Log → Slack
                                            ┘
```

## ✨ Key Features

- **🔍 Live multi-source research** via MCP servers (news search, pricing pages, careers pages)
- **🤖 JavaScript-aware scraping** — Playwright renders client-side job boards so hiring data isn't limited to static HTML
- **✅ Source verification** — claims need independent corroboration before entering the graph
- **🕸️ GraphRAG retrieval** — exact relational answers (Cypher) combined with fuzzy semantic search (vector embeddings)
- **📈 Real price-change detection** — numeric price comparison across runs (not brittle text diffing), so wording differences never trigger false "price changed" alerts
- **😊 Sentiment scoring** — every announcement is tagged positive / negative / neutral from a competitive standpoint
- **🚨 Real-time alerting** — major moves (acquisitions, layoffs, funding) trigger an immediate Slack ping, not a wait for the weekly digest
- **🕐 Weekly scheduling** — APScheduler runs the full pipeline automatically every Monday at 7am
- **🕸️ Interactive graph explorer** — drag-and-explore visualization of the competitor knowledge graph, built into the dashboard
- **💬 Slack integration** — formatted, cited digest posted automatically to a channel

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| Tool integration | [FastMCP](https://github.com/jlowin/fastmcp) (MCP servers for search, careers, Slack) |
| Backend API | [FastAPI](https://fastapi.tiangolo.com/) |
| LLM inference | [Groq](https://groq.com/) (`llama-3.3-70b-versatile`) or local [Ollama](https://ollama.com/) (`qwen2.5:14b`) |
| Knowledge graph | [Neo4j](https://neo4j.com/) |
| Vector store | [Qdrant](https://qdrant.tech/) |
| Relational store | [PostgreSQL](https://www.postgresql.org/) |
| Frontend | [Streamlit](https://streamlit.io/) |
| Browser rendering | [Playwright](https://playwright.dev/) |
| Scheduling | [APScheduler](https://apscheduler.readthedocs.io/) |
| Messaging | [Slack SDK](https://slack.dev/python-slack-sdk/) |

## 📁 Project Structure

```
ci_agent/
├── llm/                    # Centralized LLM client config (Groq/Ollama)
├── schemas/                # Pydantic data models shared across agents
├── mcp_servers/            # MCP tool servers: search, careers, Slack
├── agents/                 # The five pipeline agents
│   ├── research_agent.py
│   ├── fact_checker_agent.py
│   ├── graph_builder_agent.py
│   ├── alerting_agent.py
│   ├── analyst_agent.py
│   └── changelog_agent.py
├── graph/                  # Neo4j client
├── vectorstore/            # Qdrant client
├── db/                     # PostgreSQL models (brief history, snapshots)
├── orchestrator.py         # LangGraph pipeline definition
├── api/
│   └── main.py             # FastAPI app, MCP client, scheduler, endpoints
└── dashboard/
    └── app.py              # Streamlit dashboard + graph explorer
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Neo4j, Qdrant, PostgreSQL)
- A [Groq API key](https://console.groq.com/keys) (free tier available) **or** [Ollama](https://ollama.com/) installed locally
- A [NewsAPI](https://newsapi.org/register) key (free tier available)
- A [Slack app](https://api.slack.com/apps) with a bot token (optional, for digest delivery)

### 1. Clone and install dependencies

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
pip install -r requirements.txt
playwright install chromium
```

### 2. Start the infrastructure

```bash
docker compose up -d
```

This starts Neo4j (`:7474` / `:7687`), Qdrant (`:6333`), and PostgreSQL (`:5432`).

### 3. Configure environment variables

Copy the example file and fill in your own values:

```bash
cp .env.example .env
```

```ini
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here
POSTGRES_URL=postgresql://postgres:your_password_here@localhost:5432/ci_agent
NEWS_API_KEY=your_news_api_key
SLACK_BOT_TOKEN=your_slack_bot_token
GROQ_API_KEY=your_groq_api_key
```

### 4. Run the backend

```bash
python -m uvicorn ci_agent.api.main:app --reload --port 8000
```

### 5. Run the dashboard (in a separate terminal)

```bash
python -m streamlit run ci_agent/dashboard/app.py
```

Open `http://localhost:8501` and click **Run Pipeline Now**.

## ⚙️ Configuration

**Tracked competitors** are defined in `ci_agent/agents/research_agent.py`:

```python
COMPETITORS = {
    "Notion": {"pricing_url": "...", "careers_url": "..."},
    "Asana": {"pricing_url": "...", "careers_url": "..."},
    # ...
}
```

Add or remove competitors by editing this dictionary.

**Model choice** — switch between Groq and Ollama in `ci_agent/llm/ollama_client.py` by changing `get_extraction_llm()` / `get_synthesis_llm()`.

**Schedule** — change the cron trigger in `ci_agent/api/main.py`:

```python
scheduler.add_job(run_pipeline, "cron", day_of_week="mon", hour=7)
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/run-now` | `POST` | Trigger a manual pipeline run |
| `/briefs/latest` | `GET` | Retrieve the most recent brief |
| `/graph/data` | `GET` | Raw graph edges for visualization |
| `/scheduler/status` | `GET` | Check the weekly job schedule |
| `/health/ollama` | `GET` | Check local Ollama connectivity |

## 🧩 Agentic Concepts Demonstrated

- **Orchestration pattern:** sequential handoff with a parallel branch (graph-building and alerting run concurrently after fact-checking)
- **Memory:** long-term structured memory via the Neo4j knowledge graph, persisting across weekly runs
- **Retrieval:** GraphRAG — knowledge graph traversal combined with vector similarity search
- **Tool use:** MCP-based tool integration for search, scraping, and messaging
- **Verification loop:** claims are held to a corroboration standard before being trusted downstream

## 📝 License

This project was built as a learning exercise in agentic system design. Feel free to fork and adapt it.
