from dotenv import load_dotenv
load_dotenv()
import sys
import os
import asyncio
from contextlib import AsyncExitStack
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ci_agent.orchestrator import build_graph
from ci_agent.graph.neo4j_client import Neo4jClient
from ci_agent.vectorstore.qdrant_client import VectorStore

app = FastAPI(title="Competitive Intelligence Agent (Ollama)")
pipeline = build_graph()
scheduler = AsyncIOScheduler()


def _format_brief_as_markdown(brief, sentiment_counts=None) -> str:
    """Convert the WeeklyBrief object into a clean, human-readable Slack
    message instead of dumping the raw Python object repr."""
    lines = [f"*\U0001F4CA Competitive Intelligence Brief \u2014 {brief.week_of}*"]
    if sentiment_counts:
        badge_line = (
            f"\U0001F7E2 {sentiment_counts.get('positive', 0)} positive   "
            f"\U0001F534 {sentiment_counts.get('negative', 0)} negative   "
            f"\u26AA {sentiment_counts.get('neutral', 0)} neutral"
        )
        lines.append(badge_line)
    lines.append("")

    for section in brief.sections:
        lines.append(f"*{section.heading}*")
        lines.append(section.content)
        if section.citations:
            sources = "  ".join(f"<{url}|link>" for url in section.citations)
            lines.append(f"Sources: {sources}")
        lines.append("")
        lines.append("---")
        lines.append("")

    if brief.whats_new:
        lines.append(f"*\U0001F195 What's New This Week*")
        for item in brief.whats_new[:15]:
            lines.append(f"\u2022 {item}")
        if len(brief.whats_new) > 15:
            lines.append(f"_...and {len(brief.whats_new) - 15} more items._")

    return "\n".join(lines)


class MultiMCPClient:
    """Manages connections to multiple MCP servers (search, careers, slack)
    and dispatches tool calls to the right one based on a 'server.tool' name."""

    def __init__(self):
        self.sessions: dict[str, ClientSession] = {}
        self._stack = AsyncExitStack()

    async def connect_all(self):
        servers = {
            "competitor-search": "ci_agent/mcp_servers/search_server.py",
            "careers-scraper": "ci_agent/mcp_servers/careers_server.py",
            "slack-notifier": "ci_agent/mcp_servers/slack_server.py",
        }
        for name, script in servers.items():
            print(f"--- Connecting to MCP server: {name} ({script}) ---")
            params = StdioServerParameters(
                command=sys.executable,
                args=[script],
                env=os.environ.copy(),
            )
            try:
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.sessions[name] = session
                print(f"--- Connected successfully to {name} ---")
            except Exception as e:
                print(f"!!! FAILED to connect to {name}: {type(e).__name__}: {e} !!!")
                raise

    async def call_tool(self, dotted_name: str, arguments: dict):
        server_name, tool_name = dotted_name.split(".", 1)
        session = self.sessions[server_name]
        result = await session.call_tool(tool_name, arguments)
        # MCP tool results come back as content blocks; unwrap to plain data
        if result.content and hasattr(result.content[0], "text"):
            import json
            try:
                return json.loads(result.content[0].text)
            except json.JSONDecodeError:
                return result.content[0].text
        return result.content

    async def close(self):
        await self._stack.aclose()


async def run_pipeline():
    initial_state = {
        "mcp_client": app.state.mcp_client,
        "neo4j_client": Neo4jClient(),
        "vectorstore": VectorStore(),
        "raw_claims": [], "verified_claims": [], "graph_edges": [], "brief": None,
    }
    final_state = await pipeline.ainvoke(initial_state)
    try:
        formatted_message = _format_brief_as_markdown(
            final_state["brief"], final_state.get("sentiment_counts")
        )
        await app.state.mcp_client.call_tool("slack-notifier.post_digest", {
            "channel": "#all-",
            "markdown_text": formatted_message,
        })
    except Exception as e:
        print(f"Slack post failed (non-fatal): {e}")
    return final_state["brief"]


@app.on_event("startup")
async def startup():
    app.state.mcp_client = MultiMCPClient()
    await app.state.mcp_client.connect_all()
    scheduler.add_job(run_pipeline, "cron", day_of_week="mon", hour=7)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    await app.state.mcp_client.close()


@app.post("/run-now")
async def trigger_manual_run():
    brief = await run_pipeline()
    return brief.model_dump(mode="json")


@app.get("/briefs/latest")
async def latest_brief():
    from ci_agent.db.postgres_models import Session, BriefHistory
    session = Session()
    row = session.query(BriefHistory).order_by(BriefHistory.id.desc()).first()
    return row.brief_json if row else {}


@app.get("/health/ollama")
async def ollama_health():
    import httpx
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return {"ollama_running": resp.status_code == 200, "models": resp.json()}
    except Exception as e:
        return {"ollama_running": False, "error": str(e)}


@app.get("/scheduler/status")
async def scheduler_status():
    jobs = scheduler.get_jobs()
    return {
        "scheduler_running": scheduler.running,
        "jobs": [
            {"id": job.id, "next_run": str(job.next_run_time), "trigger": str(job.trigger)}
            for job in jobs
        ]
    }

@app.get("/graph/data")
async def graph_data():
    """Return all nodes and relationships from the knowledge graph so the
    dashboard can render an interactive visualization."""
    neo4j = Neo4jClient()
    cypher = """
    MATCH (s:Entity)-[r]->(o:Entity)
    RETURN s.name AS source, type(r) AS relation, o.name AS target
    LIMIT 300
    """
    try:
        rows = await neo4j.query(cypher)
        return {"edges": rows}
    except Exception as e:
        return {"edges": [], "error": str(e)}    