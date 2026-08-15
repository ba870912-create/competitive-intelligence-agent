from ci_agent.llm.ollama_client import get_extraction_llm, invoke_with_timeout
import json
import re

llm = get_extraction_llm()

HIGH_IMPACT_TYPES = {"acquisition", "funding", "layoffs", "major_price_change"}


async def alerting_node(state: dict) -> dict:
    """
    Scans this week's verified claims for high-impact events (acquisitions,
    funding rounds, major layoffs, big price changes) and pings Slack
    immediately -- independent of the weekly digest cycle. This implements
    the "alert rather than wait for the weekly cycle" pattern from the spec.
    """
    mcp_client = state.get("mcp_client")
    alerts_sent = []

    for claim in state.get("verified_claims", []):
        if claim.claim_type != "announcement":
            continue

        impact = _classify_impact(claim.text)
        if impact["is_major"]:
            message = (
                f"\U0001F6A8 *Major move detected: {claim.competitor}*\n"
                f"{claim.text}\n"
                f"Type: {impact['category']}  |  Source: <{claim.source_url}|link>"
            )
            try:
                if mcp_client:
                    await mcp_client.call_tool("slack-notifier.post_digest", {
                        "channel": "#all-",
                        "markdown_text": message,
                    })
                alerts_sent.append(claim.text[:80])
                print(f"ALERT sent for {claim.competitor}: {impact['category']}")
            except Exception as e:
                print(f"Alert send failed for {claim.competitor}: {e}")

    return {"alerts_sent": alerts_sent}


def _classify_impact(text: str) -> dict:
    """Ask the model whether this announcement is a major competitive event
    worth an immediate alert, and if so, what category it falls under."""
    prompt = f"""Classify this competitor announcement. Respond with ONLY a JSON object:
{{"is_major": true/false, "category": "acquisition|funding|layoffs|major_price_change|other"}}

An announcement is "major" only if it represents a significant business event:
acquisitions/mergers, funding rounds, layoffs affecting a meaningful share of staff,
or a large pricing change. Routine product updates, minor blog mentions, or small
feature releases are NOT major.

Announcement: "{text}"
"""
    try:
        result = invoke_with_timeout(llm, prompt, timeout_seconds=30)
        raw = result.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return {
            "is_major": bool(data.get("is_major", False)),
            "category": data.get("category", "other"),
        }
    except Exception:
        return {"is_major": False, "category": "other"}