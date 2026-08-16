from ci_agent.llm.ollama_client import get_synthesis_llm, invoke_with_timeout
from ci_agent.schemas.models import WeeklyBrief, BriefSection
from datetime import date as date_type
import json
import re

llm = get_synthesis_llm()

RELATIONAL_QUESTIONS = {
    "Who changed pricing more than once this quarter?": """
        MATCH (c:Entity)-[r:RAISED_PRICE_ON|LOWERED_PRICE_ON]->(p:Entity)
        WHERE r.date >= date() - duration('P90D')
        WITH c, count(r) AS changes
        WHERE changes > 1
        RETURN c.name AS competitor, changes
    """,
}


async def analyst_node(state: dict) -> dict:
    neo4j, vectorstore = state["neo4j_client"], state["vectorstore"]

    graph_answers = {}
    for question, cypher in RELATIONAL_QUESTIONS.items():
        try:
            graph_answers[question] = await neo4j.query(cypher)
        except Exception as e:
            graph_answers[question] = f"(query failed: {e})"

    # Compare the two most recent price observations for each competitor/plan
    # across separate pipeline runs -- this is the real "did pricing change
    # over time" signal, as opposed to a single-run snapshot.
    try:
        price_changes = await neo4j.get_price_changes()
        graph_answers["Pricing changes detected since last run"] = price_changes
        print(f"GraphRAG: detected {len(price_changes)} real price changes across runs")
    except Exception as e:
        graph_answers["Pricing changes detected since last run"] = f"(query failed: {e})"

    try:
        semantic_hits = vectorstore.semantic_search("AI features and product direction")
        semantic_payloads = [h.payload for h in semantic_hits]
    except Exception:
        semantic_payloads = []
    print(f"GraphRAG: semantic search returned {len(semantic_payloads)} hits")
    for p in semantic_payloads[:3]:
        print(f"  - {p.get('text', '')[:80]}")

    verified = [c.model_dump(mode="json") for c in state['verified_claims']]

    # Tally sentiment across this week's announcement claims so the final
    # brief can show a quick positive/negative/neutral snapshot up top.
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    for c in state['verified_claims']:
        if c.sentiment in sentiment_counts:
            sentiment_counts[c.sentiment] += 1
    print(f"Sentiment summary: {sentiment_counts}")

    sections = _synthesize_with_retry(graph_answers, semantic_payloads, verified, max_retries=2)
    state["brief"] = WeeklyBrief(week_of=date_type.today(), sections=sections)
    state["sentiment_counts"] = sentiment_counts
    return state


def _synthesize_with_retry(graph_answers, semantic_payloads, verified, max_retries=2):
    competitor_names = sorted({c.get("competitor") for c in verified if c.get("competitor")})

    base_prompt = f"""You are writing a weekly competitive intelligence brief for executives
covering these competitors: {", ".join(competitor_names)}.

Respond with ONLY valid JSON, no markdown code fences, no explanation text before or after.
The JSON must match exactly this shape:
{{"sections": [{{"heading": "string", "content": "string", "citations": ["url1", "url2"]}}]}}

Write these 4 sections: Pricing Moves, Product Announcements, Hiring Signals, Notable Trends.

CRITICAL: Every section must cover EVERY competitor listed above that has relevant data
in "All verified claims this week" below -- do not limit any section to just one or two
competitors.

FORMATTING RULE FOR ALL FOUR SECTIONS (Pricing Moves, Product Announcements, Hiring
Signals, Notable Trends): within each section's "content" string, organize by
competitor. For each competitor that has at least one claim relevant to that section,
write their name as its own bold line ("**CompetitorName**"), then list EVERY relevant
claim for that competitor as a separate bullet point using "\n- " on the line(s)
immediately after. Never merge multiple claims from the same competitor into a single
sentence or paragraph, and never combine claims from different competitors into one
bullet. Structure looks like:
"**CompetitorA**\n- claim one\n- claim two\n\n**CompetitorB**\n- claim one"

Group the claims by claim_type per section:
- "pricing" claims -> Pricing Moves
- "hiring" claims -> Hiring Signals
- "announcement" claims -> split across Product Announcements and Notable Trends based
  on whether it's a product-level update vs a broader business/market signal

Copy each claim's text VERBATIM (job titles, prices, dates, percentages) -- do not
paraphrase or shorten specific facts. A competitor with zero claims for a section is
simply omitted from that section, but never omit one that DOES have relevant claims.

When writing any section, always use the exact wording, numbers, dates, and names from
the claim text -- do not paraphrase or shorten specific facts (job titles, prices,
percentages, dollar amounts, dates). Summarizing the overall narrative is fine, but
individual data points must be copied exactly as they appear in the claims.

If a competitor has zero claims of a given type, simply omit them from that section --
but never omit a competitor that DOES have relevant claims just because another
competitor's claim came first in the data.

For "Pricing Moves": if "Pricing changes detected since last run" has entries, describe
each change explicitly (old price -> new price) in addition to the current-price summary
above. If that list is empty, START the section with the exact sentence "No pricing
changes detected since last run." before listing current prices per competitor.

Every citation must be a real source_url taken from the data below.

Structured relational findings (from knowledge graph traversal):
{graph_answers}

Semantically related announcements (from vector search):
{semantic_payloads}

All verified claims this week:
{verified}
"""

    last_raw = ""
    for attempt in range(max_retries + 1):
        prompt = base_prompt
        if attempt > 0:
            prompt += (
                f"\n\nYour previous response was not valid JSON. Here is what you sent:\n"
                f"{last_raw[:500]}\n\n"
                f"Respond again with ONLY the raw JSON object, starting with {{ and ending with }}. "
                f"No markdown fences, no commentary."
            )
        try:
            result = invoke_with_timeout(llm, prompt, timeout_seconds=180)
            last_raw = result.content
            parsed = _try_parse_sections(last_raw)
            if parsed is not None:
                return parsed
        except TimeoutError as e:
            print(f"Synthesis attempt {attempt + 1} timed out: {e}")
            last_raw = ""

    return [BriefSection(
        heading="Synthesis Error",
        content=(
            "The brief could not be generated in structured format this week "
            f"after {max_retries + 1} attempts. Raw model output has been logged for review."
        ),
        citations=[],
    )]


def _try_parse_sections(raw: str):
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    candidate = match.group(0) if match else text

    try:
        data = json.loads(candidate)
        sections = data.get("sections", [])
        if not sections:
            return None
        return [BriefSection(**s) for s in sections]
    except Exception:
        return None