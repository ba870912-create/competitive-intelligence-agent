from fastmcp import FastMCP
import httpx

mcp = FastMCP("careers-scraper")

@mcp.tool()
async def fetch_careers_page(careers_url: str) -> str:
    """Fetch raw HTML/text of a competitor's public careers page."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(careers_url, timeout=15)
        return resp.text

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)