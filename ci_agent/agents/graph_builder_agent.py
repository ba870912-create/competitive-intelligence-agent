import json, re
from ci_agent.llm.ollama_client import get_extraction_llm, invoke_with_timeout
from ci_agent.schemas.models import VerifiedClaim, GraphEdge

llm = get_extraction_llm()
VALID_RELATION = re.compile(r"^[A-Z][A-Z0-9_]*$")

async def graph_builder_node(state: dict) -> dict:
    """
    Converts each verified claim into Competitor -> Relation -> Object edges
    using the local model, validates the relation label's format, then
    writes into Neo4j via MERGE (idempotent).

    Additionally, "announcement" claims (free-text, semantic in nature) are
    embedded and stored in Qdrant -- this is the vector half of GraphRAG.
    Pricing/hiring claims stay structured-only in the graph, since they're
    precise facts better answered by exact Cypher traversal, not fuzzy
    semantic search.
    """
    neo4j = state["neo4j_client"]
    vectorstore = state.get("vectorstore")
    edges: list[GraphEdge] = []
    embedded_count = 0

    for claim in state["verified_claims"]:
        prompt = f"""
        Convert this claim into a graph triple. Respond with ONLY a JSON
        object: {{"subject": "...", "relation": "SCREAMING_SNAKE_CASE_VERB", "object": "..."}}
        The relation must be uppercase words joined by underscores, e.g.
        RAISED_PRICE_ON, LAUNCHED_FEATURE, POSTED_JOB_ROLE.

        Claim: "{claim.text}" about competitor {claim.competitor}.
        """
        triple = _extract_triple_with_fallback(prompt, claim)
        if triple is None:
            continue

        edge = GraphEdge(**triple, date=claim.observed_on, source_url=claim.source_url)
        edges.append(edge)
        await neo4j.upsert_edge(edge.subject, edge.relation, edge.object,
                                 edge.date, edge.source_url)

        # For pricing claims specifically, also record a timestamped price
        # point so we can detect real changes across runs over time.
        if claim.claim_type == "pricing":
            try:
                price_amount = _extract_price_amount(claim.text)
                await neo4j.add_price_point(
                    competitor=claim.competitor,
                    plan_name=_extract_plan_name(claim.text),
                    price_text=claim.text,
                    price_amount=price_amount,
                    date=claim.observed_on,
                    source_url=claim.source_url,
                )
            except Exception as e:
                print(f"  Price point recording failed for {claim.competitor}: {e}")

        # GraphRAG: embed free-text announcement claims into the vector
        # store so the Analyst Agent's semantic_search has real data to
        # retrieve, instead of querying an empty collection.
        if claim.claim_type == "announcement" and vectorstore is not None:
            try:
                vectorstore.upsert_claim(claim)
                embedded_count += 1
            except Exception as e:
                print(f"  Vector upsert failed for claim '{claim.text[:50]}...': {e}")

    print(f"Graph-Builder: wrote {len(edges)} edges, embedded {embedded_count} announcement claims into Qdrant")

    return {"graph_edges": edges}

def _extract_triple_with_fallback(prompt: str, claim: VerifiedClaim) -> dict | None:
    try:
        result = invoke_with_timeout(llm, prompt, timeout_seconds=60)
        triple = json.loads(result.content)
        if not VALID_RELATION.match(triple.get("relation", "")):
            triple["relation"] = re.sub(r"[^A-Za-z0-9]+", "_", triple["relation"]).upper().strip("_")
        return triple
    except (Exception, TimeoutError):
        return {"subject": claim.competitor, "relation": "MENTIONED_IN",
                "object": claim.text[:80]}


def _extract_price_amount(text: str) -> float | None:
    """Pull the first numeric price (e.g. from '$7 per user/month' -> 7.0,
    or '€9 seat/month' -> 9.0) out of a pricing claim's text, so price
    comparisons across runs use the actual number, not the full sentence."""
    match = re.search(r"[\$€£]\s?(\d+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1))
    # Handle "Free" / "$0" style claims explicitly as zero
    if re.search(r"\bfree\b", text, re.IGNORECASE):
        return 0.0
    return None


def _extract_plan_name(text: str) -> str:
    """Best-effort plan identifier so the same plan is tracked consistently
    across runs even if the surrounding sentence wording shifts slightly."""
    known_plans = ["Free", "Plus", "Business", "Enterprise", "Personal",
                   "Starter", "Advanced", "Basic", "Standard", "Pro",
                   "Unlimited", "Team"]
    for plan in known_plans:
        if re.search(rf"\b{plan}\b", text, re.IGNORECASE):
            return plan
    return text[:40]  # fallback: first 40 chars as a rough identifier