from ci_agent.db.postgres_models import GraphSnapshot, BriefHistory, Session
from datetime import date, timedelta

async def changelog_node(state: dict) -> dict:
    """
    Loads last week's snapshot from Postgres, diffs it against this week's
    graph_edges, and appends a 'What's New' section. No LLM call needed here
    — it's a pure structural diff, which is exactly why it's kept
    deterministic and model-independent.
    """
    session = Session()
    last_week = date.today() - timedelta(days=7)
    prev = session.query(GraphSnapshot).filter(GraphSnapshot.week_of == last_week).first()

    prev_edges = set(
        (e["subject"], e["relation"], e["object"]) for e in (prev.edges_json if prev else [])
    )
    curr_edges = {(e.subject, e.relation, e.object) for e in state["graph_edges"]}
    new_edges = curr_edges - prev_edges

    state["brief"].whats_new = [f"{s} {r.replace('_',' ').lower()} {o}" for s, r, o in new_edges]

    session.add(GraphSnapshot(
        week_of=date.today(),
        edges_json=[e.model_dump(mode="json") for e in state["graph_edges"]],
    ))
    session.add(BriefHistory(week_of=date.today(), brief_json=state["brief"].model_dump(mode="json")))
    session.commit()
    return state