from fastmcp import FastMCP
import httpx, os

mcp = FastMCP("competitor-search")

@mcp.tool()
async def search_competitor_news(competitor: str, days_back: int = 7) -> list[dict]:
    """Search recent news/press mentions of a named competitor."""
    api_key = os.environ["NEWS_API_KEY"]
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": f'"{competitor}"',
                "sortBy": "relevancy",
                "language": "en",
                "apiKey": api_key,
            },
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])

        # NewsAPI's free-tier search is loose and can return unrelated
        # results even with an exact-phrase query. Double-check the
        # competitor name actually appears in the title or description
        # before we trust the article as relevant.
        filtered = [
            a for a in articles
            if competitor.lower() in (a.get("title") or "").lower()
            or competitor.lower() in (a.get("description") or "").lower()
        ]

        return [
            {"title": a["title"], "url": a["url"], "source": a["source"]["name"],
             "published_at": a["publishedAt"], "content": a.get("description", "")}
            for a in filtered[:10]
        ]

@mcp.tool()
async def fetch_pricing_page(url: str) -> str:
    """Fetch raw HTML/text of a competitor's public pricing page."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=15)
        return resp.text

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)