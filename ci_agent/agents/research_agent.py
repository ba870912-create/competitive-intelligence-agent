from ci_agent.llm.ollama_client import get_extraction_llm, invoke_with_timeout
from ci_agent.schemas.models import RawClaim
from pydantic import ValidationError
from bs4 import BeautifulSoup
import json
import re

llm = get_extraction_llm()

COMPETITORS = {
    "Notion": {
        "pricing_url": "https://www.notion.so/pricing",
        "careers_url": "https://www.notion.so/careers",
    },
    "Asana": {
        "pricing_url": "https://asana.com/pricing",
        "careers_url": "https://asana.com/jobs",
    },
    "Monday.com": {
        "pricing_url": "https://monday.com/pricing",
        "careers_url": "https://monday.com/careers",
    },
    "ClickUp": {
        "pricing_url": "https://clickup.com/pricing",
        "careers_url": "https://clickup.com/careers",
    },
    "Airtable": {
        "pricing_url": "https://www.airtable.com/pricing",
        "careers_url": "https://www.airtable.com/careers",
    },
}


def clean_html_to_text(html: str, max_chars: int = 4000) -> str:
    """Strip scripts/styles/metadata from raw HTML and return readable text
    only. Raw HTML is mostly markup noise (scripts, CSS classes, cookie
    banners) -- the model can only extract real facts if we hand it the
    actual visible text, not the surrounding code."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "path", "meta", "link", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars]


async def research_agent_node(state: dict) -> dict:
    raw_claims: list[RawClaim] = []

    for competitor, urls in COMPETITORS.items():
        try:
            news = await state["mcp_client"].call_tool(
                "competitor-search.search_competitor_news", {"competitor": competitor}
            )
        except Exception as e:
            print(f"News fetch failed for {competitor}: {e}")
            news = []

        try:
            pricing_html = await state["mcp_client"].call_tool(
                "competitor-search.fetch_pricing_page", {"url": urls["pricing_url"]}
            )
        except Exception as e:
            print(f"Pricing fetch failed for {competitor}: {e}")
            pricing_html = ""

        try:
            careers_html = await state["mcp_client"].call_tool(
                "careers-scraper.fetch_careers_page", {"careers_url": urls["careers_url"]}
            )
        except Exception as e:
            print(f"Careers fetch failed for {competitor}: {e}")
            careers_html = ""

        careers_text = clean_html_to_text(careers_html, max_chars=4000)
        print(f"\n--- CLEANED CAREERS TEXT for {competitor} ---")
        print(careers_text[:500])
        print("--- END CLEANED CAREERS TEXT ---\n")

        pricing_text = clean_html_to_text(pricing_html, max_chars=4000)

        print(f"\n--- CLEANED TEXT for {competitor} ---")
        print(pricing_text[:500])
        print("--- END CLEANED TEXT ---\n")

        print(f"News result for {competitor}: {len(news) if isinstance(news, list) else 'N/A'} articles found")
        if isinstance(news, list) and news:
            print(f"  Sample: {news[0]}")

        if not pricing_text and not careers_text and not news:
            print(f"No usable data for {competitor}, skipping extraction.")
            continue

        extraction_prompt = f"""Extract factual claims about {competitor} (a SaaS
productivity/project-management company) as a JSON array.
Each item must have exactly these fields: claim_type ("pricing", "announcement", or "hiring"), text (string), source_url (string), source_name (string).
Respond with ONLY the JSON array, no other text, no markdown code fences.
If there is nothing extractable, respond with an empty array: []

Pricing page text: {pricing_text}

Recent news articles: {news[:5] if isinstance(news, list) else news}

Careers page text (job listings): {careers_text}

Only include claims that are explicitly supported by the text above.

IMPORTANT: The news search is keyword-based and can return irrelevant articles that
merely happen to contain the word "{competitor}" (e.g. an unrelated news story, a
person's name, a common English word). Before including a news article as an
"announcement" claim, verify the article is actually ABOUT the company {competitor}
as a SaaS/software business -- not just an article that mentions the word "{competitor}"
in passing or by coincidence. If an article is not clearly about the company, skip it
entirely rather than including it.

For "announcement" claims, use the article's own URL as source_url.
"""
        claims = _extract_claims_with_retry(competitor, extraction_prompt, urls)
        print(f"Extracted {len(claims)} claims for {competitor}")
        raw_claims.extend(claims)

    print(f"\n=== DEBUG: Extracted {len(raw_claims)} raw claims total ===")
    for c in raw_claims:
        print(f"  - [{c.claim_type}] {c.text[:100]} (source: {c.source_url})")
    print("=== END DEBUG ===\n")

    state["raw_claims"] = raw_claims
    return state


def _extract_claims_with_retry(competitor: str, prompt: str, urls: dict, max_retries: int = 2) -> list[RawClaim]:
    for attempt in range(max_retries + 1):
        try:
            result = invoke_with_timeout(llm, prompt, timeout_seconds=120)
            raw = result.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            candidate = match.group(0) if match else raw

            items = json.loads(candidate)
            claims = []
            for item in items:
                item.setdefault("source_name", competitor)
                claim_type = item.get("claim_type")
                if claim_type == "pricing":
                    item["source_url"] = urls["pricing_url"]
                elif claim_type == "hiring":
                    item["source_url"] = urls["careers_url"]

                try:
                    claims.append(RawClaim(competitor=competitor, **item))
                except ValidationError as ve:
                    print(f"  Skipping malformed claim for {competitor}: {ve}")
                    continue
            return claims
        except (json.JSONDecodeError, TypeError, TimeoutError) as e:
            print(f"  Extraction attempt {attempt + 1} failed for {competitor}: {e}")
            if attempt == max_retries:
                return []
            continue
    return []