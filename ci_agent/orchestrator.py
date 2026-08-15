from langgraph.graph import StateGraph, END
from typing import TypedDict, Any

class PipelineState(TypedDict):
    mcp_client: Any
    neo4j_client: Any
    vectorstore: Any
    raw_claims: list
    verified_claims: list
    graph_edges: list
    brief: Any
    alerts_sent: list

def build_graph():
    from ci_agent.agents.research_agent import research_agent_node
    from ci_agent.agents.fact_checker_agent import fact_checker_node
    from ci_agent.agents.graph_builder_agent import graph_builder_node
    from ci_agent.agents.alerting_agent import alerting_node
    from ci_agent.agents.analyst_agent import analyst_node
    from ci_agent.agents.changelog_agent import changelog_node

    g = StateGraph(PipelineState)
    g.add_node("research", research_agent_node)
    g.add_node("fact_check", fact_checker_node)
    g.add_node("build_graph", graph_builder_node)
    g.add_node("alert", alerting_node)
    g.add_node("analyze", analyst_node)
    g.add_node("changelog", changelog_node)

    g.set_entry_point("research")
    g.add_edge("research", "fact_check")

    # After fact-checking, run graph-building and alerting in parallel --
    # alerting doesn't need the graph to exist, it just scans verified
    # claims directly and pings Slack immediately for major events.
    g.add_edge("fact_check", "build_graph")
    g.add_edge("fact_check", "alert")

    # Both branches must complete before synthesis runs, since analyze
    # needs the graph data build_graph produced.
    g.add_edge("build_graph", "analyze")
    g.add_edge("alert", "analyze")

    g.add_edge("analyze", "changelog")
    g.add_edge("changelog", END)

    return g.compile()