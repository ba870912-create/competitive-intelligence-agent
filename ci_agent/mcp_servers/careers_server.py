from fastmcp import FastMCP
import httpx
from playwright.async_api import async_playwright

mcp = FastMCP("careers-scraper")

@mcp.tool()
async def fetch_careers_page(careers_url: str) -> str:
    """Fetch a competitor's public careers page, rendering JavaScript first
    so dynamically-loaded job listings (common on modern careers pages)
    are actually present in the returned text -- a plain HTTP GET would
    only capture the initial HTML shell before the job list loads."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(careers_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Some careers pages only populate the job list after a visible
            # "See all open positions" / "View jobs" button is clicked --
            # try common variants before giving up.
            button_texts = ["See all open positions", "View open positions",
                             "View jobs", "See open roles", "View all jobs"]
            for text in button_texts:
                try:
                    button = page.get_by_text(text, exact=False).first
                    if await button.is_visible(timeout=2000):
                        await button.click(timeout=3000)
                        await page.wait_for_timeout(3000)
                        break
                except Exception:
                    continue

            # Scroll to trigger any lazy-loaded content further down the page
            try:
                for _ in range(3):
                    await page.mouse.wheel(0, 2000)
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            content = await page.content()
            await browser.close()
            return content
    except Exception as e:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(careers_url, timeout=15)
                return resp.text
        except Exception:
            return f"(fetch failed: {e})"

if __name__ == "__main__":
    mcp.run(transport="stdio", show_banner=False)