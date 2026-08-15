from ci_agent.llm.ollama_client import get_extraction_llm, invoke_with_timeout
from ci_agent.schemas.models import RawClaim, VerifiedClaim
from collections import defaultdict
from urllib.parse import urlparse

llm = get_extraction_llm()

async def fact_checker_node(state: dict) -> dict:
    """
    Groups claims by (competitor, normalized claim), then verifies them:
    - pricing/hiring claims from the competitor's own official site are
      trusted automatically (first-party data, not a rumor that needs
      corroboration).
    - announcement claims need 2+ independent domains to be "confirmed";
      a single reputable news source is still kept but marked "unconfirmed"
      rather than dropped, since real news often only breaks in one outlet
      at first.
    """
    claims: list[RawClaim] = state["raw_claims"]
    grouped = defaultdict(list)

    for c in claims:
        key = _normalize_claim(c.competitor, c.text)
        grouped[key].append(c)

    verified: list[VerifiedClaim] = []
    for key, group in grouped.items():
        domains = {urlparse(c.source_url).netloc for c in group if c.source_url}
        primary = group[0]

        if primary.claim_type in ("pricing", "hiring"):
            confidence = "confirmed"
        else:
            confidence = "confirmed" if len(domains) >= 2 else "unconfirmed"

        sentiment = None
        if primary.claim_type == "announcement":
            sentiment = _score_sentiment(primary.text)
        if sentiment:
            print(f"  Sentiment scored for '{primary.text[:50]}...': {sentiment}")

        verified.append(VerifiedClaim(
            **primary.model_dump(),
            confidence=confidence,
            corroborating_sources=[c.source_url for c in group if c.source_url],
            sentiment=sentiment,
        ))

    state["verified_claims"] = [
        v for v in verified
        if v.confidence == "confirmed" or v.source_url
    ]
    return state


def _normalize_claim(competitor: str, text: str) -> str:
    """Ask the local model for a short canonical key so paraphrased claims
    from different outlets merge into the same group. Falls back to the raw
    text (still usable, just less likely to merge duplicates) if parsing fails."""
    prompt = f"""
    Produce a short (max 8 words) canonical English key summarizing this claim
    about {competitor}, so that paraphrases of the same fact produce the same
    key. Respond with ONLY the key text, no quotes, no JSON, no explanation.

    Claim: "{text}"
    """
    try:
        result = invoke_with_timeout(llm, prompt, timeout_seconds=60)
        key = result.content.strip().strip('"')
        return f"{competitor}::{key.lower()}" if key else f"{competitor}::{text.lower()}"
    except (Exception, TimeoutError):
        return f"{competitor}::{text.lower()}"

def _score_sentiment(text: str) -> str:
    """Classify an announcement as positive, negative, or neutral from a
    competitive standpoint (e.g. layoffs = negative, funding = positive)."""
    prompt = f"""
    Classify the sentiment of this competitor announcement from a business
    standpoint. Respond with ONLY one word: "positive", "negative", or "neutral".

    Announcement: "{text}"
    """
    try:
        result = invoke_with_timeout(llm, prompt, timeout_seconds=30)
        label = result.content.strip().lower().strip('"')
        return label if label in ("positive", "negative", "neutral") else "neutral"
    except Exception:
        return "neutral"