import streamlit as st
import httpx
from pyvis.network import Network
import streamlit.components.v1 as components

st.set_page_config(page_title="Competitive Intelligence", layout="wide")
st.title("📊 Competitive Intelligence & Market Watch")

ollama_status = httpx.get("http://localhost:8000/health/ollama").json()
if not ollama_status.get("ollama_running"):
    st.warning("⚠️ Ollama doesn't appear to be running — start it with `ollama serve` before running the pipeline.")

brief = httpx.get("http://localhost:8000/briefs/latest").json()

if st.button("Run pipeline now"):
    with st.spinner("Researching, verifying, building graph (local model may take a while)..."):
        brief = httpx.post("http://localhost:8000/run-now", timeout=1800).json()

for section in brief.get("sections", []):
    st.subheader(section["heading"])
    st.write(section["content"])
    with st.expander("Sources"):
        for c in section["citations"]:
            st.markdown(f"- [{c}]({c})")

st.divider()
st.subheader("🆕 What's New This Week")
for item in brief.get("whats_new", []):
    st.markdown(f"- {item}")

st.divider()
st.subheader("🕸️ Competitor Graph Explorer")
st.caption("Drag nodes to explore relationships between competitors, products, and announcements.")

if st.button("Load / Refresh Graph"):
    with st.spinner("Loading knowledge graph from Neo4j..."):
        graph_data = httpx.get("http://localhost:8000/graph/data", timeout=30).json()
        edges = graph_data.get("edges", [])

        if not edges:
            st.info("No graph data yet — run the pipeline at least once first.")
        else:
            net = Network(height="600px", width="100%", bgcolor="#0e1117", font_color="white", directed=True)
            net.barnes_hut()

            seen_nodes = set()
            for edge in edges:
                source, relation, target = edge["source"], edge["relation"], edge["target"]
                for node in (source, target):
                    if node not in seen_nodes:
                        net.add_node(node, label=node, color="#4A90D9")
                        seen_nodes.add(node)
                net.add_edge(source, target, label=relation, color="#888888")

            net.save_graph("graph.html")
            with open("graph.html", "r", encoding="utf-8") as f:
                html_content = f.read()
            components.html(html_content, height=620, scrolling=True)