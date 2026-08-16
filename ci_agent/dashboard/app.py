import streamlit as st
import httpx
from pyvis.network import Network
import streamlit.components.v1 as components
from datetime import datetime

st.set_page_config(
    page_title="Competitive Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------- Custom CSS for a more polished look ----------
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0;
    }
    .sub-header {
        color: #9CA3AF;
        font-size: 0.95rem;
        margin-top: -8px;
        margin-bottom: 24px;
    }
    .metric-card {
        background: #1a1d24;
        border: 1px solid #2d3139;
        border-radius: 10px;
        padding: 16px 20px;
        text-align: center;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
    }
    .metric-label {
        color: #9CA3AF;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .section-card {
        background: #1a1d24;
        border: 1px solid #2d3139;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 16px;
    }
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 8px;
    }
    div[data-testid="stExpander"] {
        border: none;
    }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8000"

# ---------- Header ----------
col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown('<p class="main-header">📊 Competitive Intelligence & Market Watch</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Weekly automated competitor tracking — pricing, hiring, and market moves</p>', unsafe_allow_html=True)

with col_status:
    try:
        ollama_status = httpx.get(f"{API_BASE}/health/ollama", timeout=5).json()
        if ollama_status.get("ollama_running"):
            st.success("🟢 System Online", icon="✅")
        else:
            st.warning("🟡 Ollama Offline")
    except Exception:
        st.error("🔴 Backend Unreachable")

st.divider()

# ---------- Control bar ----------
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 1, 2])
with ctrl_col1:
    run_clicked = st.button("▶️  Run Pipeline Now", type="primary", use_container_width=True)
with ctrl_col2:
    try:
        sched = httpx.get(f"{API_BASE}/scheduler/status", timeout=5).json()
        next_run = sched.get("jobs", [{}])[0].get("next_run", "N/A")
        st.caption(f"🕐 Next auto-run: {next_run}")
    except Exception:
        st.caption("🕐 Schedule unavailable")

brief = httpx.get(f"{API_BASE}/briefs/latest", timeout=10).json()

if run_clicked:
    with st.spinner("Researching competitors, verifying sources, building knowledge graph..."):
        brief = httpx.post(f"{API_BASE}/run-now", timeout=1800).json()
    st.success("Pipeline completed successfully!")

st.divider()

# ---------- Summary metrics ----------
if brief.get("sections"):
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{len(brief.get("sections", []))}</div><div class="metric-label">Report Sections</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{len(brief.get("whats_new", []))}</div><div class="metric-label">New This Week</div></div>', unsafe_allow_html=True)
    with m3:
        total_sources = sum(len(s.get("citations", [])) for s in brief.get("sections", []))
        st.markdown(f'<div class="metric-card"><div class="metric-value">{total_sources}</div><div class="metric-label">Cited Sources</div></div>', unsafe_allow_html=True)
    with m4:
        st.markdown(f'<div class="metric-card"><div class="metric-value">{brief.get("week_of", "—")}</div><div class="metric-label">Report Date</div></div>', unsafe_allow_html=True)

    st.write("")

# ---------- Report sections ----------
SECTION_ICONS = {
    "Pricing Moves": "💰",
    "Product Announcements": "📢",
    "Hiring Signals": "👥",
    "Notable Trends": "📈",
}

tab_labels = [f"{SECTION_ICONS.get(s['heading'], '📄')} {s['heading']}" for s in brief.get("sections", [])]
if tab_labels:
    tabs = st.tabs(tab_labels)
    for tab, section in zip(tabs, brief.get("sections", [])):
        with tab:
            st.markdown(f'<div class="section-card">{section["content"]}</div>', unsafe_allow_html=True)
            if section.get("citations"):
                with st.expander(f"📎 {len(section['citations'])} sources"):
                    for c in section["citations"]:
                        st.markdown(f"- [{c}]({c})")
else:
    st.info("No report generated yet. Click **Run Pipeline Now** to generate the first competitive brief.")

# ---------- What's New ----------
if brief.get("whats_new"):
    st.divider()
    st.markdown("### 🆕 What's New This Week")
    cols = st.columns(2)
    for i, item in enumerate(brief["whats_new"]):
        with cols[i % 2]:
            st.markdown(f"- {item}")

# ---------- Graph Explorer ----------
st.divider()
st.markdown("### 🕸️ Competitor Graph Explorer")
st.caption("Drag nodes to explore relationships between competitors, products, and announcements.")

if st.button("🔄 Load / Refresh Graph"):
    with st.spinner("Loading knowledge graph from Neo4j..."):
        graph_data = httpx.get(f"{API_BASE}/graph/data", timeout=30).json()
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

st.divider()
st.caption("Competitive Intelligence & Market Watch Agent · Powered by LangGraph, Neo4j, Qdrant & Groq")