"""
ui/dashboard.py
---------------
Realtime operations dashboard for the Agentic Support Framework.

Run:
    streamlit run ui/dashboard.py

Start the API first:
    EMBED_MODEL=tfidf uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import streamlit as st


DEFAULT_API_BASE = "http://localhost:8000/api/v1"
AGENT_ORDER = [
    "IncidentDetectionAgent",
    "RCAAgent",
    "DecisionAgent",
    "RemediationAgent",
    "ValidationAgent",
    "CommunicationAgent",
]
LANGGRAPH_ORDER = [
    "incident_agent",
    "retrieval_agent",
    "rca_agent",
    "decision_agent",
    "approval_agent",
    "mock_remediation_agent",
    "communication_agent",
    "learning_agent",
]


st.set_page_config(
    page_title="Agentic Operations Dashboard",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
    div[data-testid="stMetric"] {
        background: #20211f;
        border: 1px solid #3c3d38;
        border-radius: 8px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] {color: #c8c7c0;}
    div[data-testid="stMetricValue"] {color: #f4f4f2;}
    .status-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid rgba(255,255,255,.18);
    }
    .ok {background:#e2f7cb;color:#246600;}
    .warn {background:#fff1d5;color:#8a4f00;}
    .bad {background:#ffe0e0;color:#9b2020;}
    .run {background:#eee8ff;color:#4930a8;}
    .idle {background:#ececec;color:#3f3f3f;}
    .panel {
        border: 1px solid #3c3d38;
        border-radius: 8px;
        padding: 14px 16px;
        background: #252623;
        margin-bottom: 12px;
    }
    .muted {color:#b8b6ae;}
    .mono {font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;}
    .graph-node {
        border: 1px solid #4b4c46;
        border-radius: 8px;
        padding: 10px;
        background: #252623;
        min-height: 78px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def call_api(api_base: str, method: str, path: str, payload: dict | None = None) -> Any:
    url = f"{api_base}{path}"
    try:
        if method == "GET":
            response = httpx.get(url, timeout=20)
        else:
            response = httpx.post(url, json=payload or {}, timeout=180)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API call failed: {method} {path} - {exc}")
        return None


def root_api_base(api_base: str) -> str:
    return api_base.removesuffix("/api/v1")


def safe_get(data: dict | None, *keys: str, default: Any = None) -> Any:
    current: Any = data or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def pill(status: str) -> str:
    value = (status or "unknown").lower()
    css = "idle"
    if value in {"ok", "ready", "healthy", "completed", "resolved", "tailing", "validated"}:
        css = "ok"
    elif value in {"running"}:
        css = "run"
    elif value in {"missing", "degraded", "human_approval", "escalated"}:
        css = "warn"
    elif value in {"failed", "critical", "not_ready"}:
        css = "bad"
    return f'<span class="status-pill {css}">{status or "unknown"}</span>'


def fmt_time(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone().strftime("%H:%M:%S")
    except Exception:
        return value


def read_tail(path: str, limit: int = 80) -> list[str]:
    if not path or path == "disabled":
        return []
    p = Path(path)
    if not p.exists():
        return []
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []


def log_level(line: str) -> str:
    upper = line.upper()
    if "CRITICAL" in upper or "FATAL" in upper or "EMERGENCY" in upper:
        return "CRITICAL"
    if "ERROR" in upper or " 500 " in upper or " 503 " in upper:
        return "ERROR"
    if "WARNING" in upper or "WARN" in upper or " 429 " in upper:
        return "WARN"
    return "INFO"


def render_pipeline(agents: list[dict]) -> None:
    states = {a.get("agent"): a for a in agents}
    columns = st.columns(len(AGENT_ORDER))
    for index, agent in enumerate(AGENT_ORDER):
        state = states.get(agent, {"status": "idle"})
        label = agent.replace("Agent", "")
        with columns[index]:
            st.markdown(
                f"""
                <div class="panel">
                  <strong>{label}</strong><br>
                  {pill(state.get("status", "idle"))}<br>
                  <span class="muted mono">{state.get("incident_id") or "-"}</span><br>
                  <span class="muted">{state.get("duration_ms") or 0} ms</span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_langgraph(data: dict) -> None:
    graph = data.get("langgraph", {})
    activity = data.get("agent_activity", [])
    latest_by_agent: dict[str, dict] = {}
    for row in activity:
        agent = row.get("agent")
        if agent in LANGGRAPH_ORDER and agent not in latest_by_agent:
            latest_by_agent[agent] = row

    columns = st.columns(4)
    for index, node in enumerate(graph.get("nodes", LANGGRAPH_ORDER)):
        latest = latest_by_agent.get(node, {})
        with columns[index % 4]:
            st.markdown(
                f"""
                <div class="graph-node">
                  <strong>{node}</strong><br>
                  {pill(latest.get("status", "idle"))}<br>
                  <span class="muted mono">{latest.get("incident_id") or "-"}</span><br>
                  <span class="muted">{latest.get("detail") or ""}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown("#### Conditional Edges")
    st.dataframe(graph.get("edges", []), use_container_width=True, hide_index=True)


def incident_table_rows(data: dict) -> list[dict]:
    rows = safe_get(data, "mongodb", "recent_incidents", default=[]) or []
    if rows:
        normalized = []
        for item in rows:
            normalized.append(
                {
                    "incident_id": item.get("incident_id"),
                    "service": item.get("service"),
                    "severity": item.get("severity"),
                    "status": item.get("status"),
                    "stage": item.get("lifecycle_stage"),
                    "decision": item.get("decision"),
                    "approval_status": item.get("approval_status"),
                    "validation": safe_get(item, "validation", "status"),
                    "updated": item.get("updated_at"),
                }
            )
        return normalized
    rows = safe_get(data, "incidents", default=[]) or []
    return rows


def pending_approval_rows(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if (
            (row.get("source") == "mvp" and row.get("decision") == "human_review")
            or row.get("decision") == "HUMAN_APPROVAL"
        )
        and row.get("approval_status") in {None, "PENDING_APPROVAL", "pending"}
    ]


def render_human_approval_queue(api_base: str, rows: list[dict], key_prefix: str) -> None:
    pending = pending_approval_rows(rows)
    if not pending:
        st.info("No incidents are waiting for human approval.")
        return

    for row in pending:
        with st.container(border=True):
            st.markdown(
                f"**{row.get('incident_id')}** | {row.get('service')} | "
                f"{row.get('severity')} | {row.get('stage')}"
            )
            if row.get("rca_summary"):
                st.caption(row.get("rca_summary"))
            approver = st.text_input(
                "Approver",
                value="oncall",
                key=f"{key_prefix}_approver_{row.get('incident_id')}",
            )
            comment = st.text_input(
                "Comment",
                value="Reviewed from dashboard",
                key=f"{key_prefix}_comment_{row.get('incident_id')}",
            )
            approve_col, more_col, reject_col = st.columns(3)
            if row.get("source") == "mvp":
                approval_base = root_api_base(api_base)
                approve_payload = {"approver": approver, "comment": comment}
            else:
                approval_base = api_base
                approve_payload = {"approved_by": approver, "comment": comment}

            if approve_col.button(
                "Approve",
                key=f"{key_prefix}_approve_{row.get('incident_id')}",
                type="primary",
                use_container_width=True,
            ):
                response = call_api(
                    approval_base,
                    "POST",
                    f"/incidents/{row.get('incident_id')}/approve",
                    approve_payload,
                )
                if response:
                    st.success(response.get("message") or "Approved")
                    st.rerun()
            if more_col.button(
                "Needs info",
                key=f"{key_prefix}_needs_info_{row.get('incident_id')}",
                use_container_width=True,
            ):
                if row.get("source") == "mvp":
                    response = call_api(
                        approval_base,
                        "POST",
                        f"/incidents/{row.get('incident_id')}/needs-more-info",
                        approve_payload,
                    )
                    if response:
                        st.warning("Marked as needs_more_info")
                        st.rerun()
                else:
                    st.warning("Needs-more-info is only implemented for MVP incidents.")
            if reject_col.button(
                "Reject",
                key=f"{key_prefix}_reject_{row.get('incident_id')}",
                use_container_width=True,
            ):
                response = call_api(
                    approval_base,
                    "POST",
                    f"/incidents/{row.get('incident_id')}/reject",
                    approve_payload,
                )
                if response:
                    st.warning(response.get("message") or "Rejected")
                    st.rerun()


with st.sidebar:
    st.title("Dashboard")
    api_base = st.text_input("API base URL", value=DEFAULT_API_BASE)
    refresh_seconds = st.slider("Refresh seconds", 2, 30, 5)
    auto_refresh = st.toggle("Auto refresh", value=True)

    health = call_api(api_base, "GET", "/health")
    if health:
        st.success("API online")
        st.caption(f"LLM: {health.get('llm_provider')} / {health.get('llm_status')}")
        st.caption(f"Vector: {health.get('vector_store')}")
    else:
        st.warning("API offline")
        st.code("EMBED_MODEL=tfidf uvicorn api.main:app --reload --port 8000", language="bash")

    st.divider()
    st.caption("Manual start")
    st.code(
        "EMBED_MODEL=tfidf uvicorn api.main:app --reload --port 8000\n"
        "streamlit run ui/dashboard.py",
        language="bash",
    )


data = call_api(api_base, "GET", "/dashboard/status") or {}
metrics = data.get("metrics", {})
system = data.get("system", {})

st.title("Agentic Operations Dashboard")
st.caption(
    f"Generated {fmt_time(data.get('generated_at'))} | "
    f"{system.get('environment', '-')}/{system.get('mode', '-')} | "
    f"{system.get('llm_provider', '-')}/{system.get('llm_model', '-')}"
)

tabs = st.tabs(
    [
        "Overview",
        "App logs",
        "Anomalies",
        "Agents",
        "Agent activity",
        "Human approval",
        "LangGraph",
        "RAG history",
        "KPI feeds",
    ]
)


with tabs[0]:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Incidents", metrics.get("incidents_total", 0), f"{metrics.get('incidents_open', 0)} open")
    c2.metric("Log anomalies (1h)", metrics.get("anomalies_1h", 0))
    c3.metric("LLM tokens", f"{metrics.get('llm_total_tokens', 0):,}", f"{metrics.get('llm_calls', 0)} calls")
    c4.metric("Auto-resolved", metrics.get("auto_resolved", 0), f"{metrics.get('human_approval', 0)} approvals")

    st.subheader("Live Agent Pipeline")
    render_pipeline(data.get("agents", []))

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Realtime Incident Flow")
        rows = incident_table_rows(data)
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("No incidents recorded in the API process or MongoDB yet.")

        pending = pending_approval_rows(rows)
        if pending:
            st.markdown("#### Human Approval Queue")
            render_human_approval_queue(api_base, pending, "overview")
    with right:
        st.subheader("Runtime Health")
        rag = data.get("rag", {})
        mongo = data.get("mongodb", {})
        st.markdown(f"RAG index: {pill(rag.get('status'))}", unsafe_allow_html=True)
        st.caption(f"Knowledge files: {rag.get('knowledge_files', 0)}")
        st.markdown(
            f"MongoDB: {pill('connected' if mongo.get('connected') else 'disabled/offline')}",
            unsafe_allow_html=True,
        )
        st.caption(f"{mongo.get('database', '-')}.{mongo.get('collection', '-')}")

    st.subheader("Run MVP Smoke Test")
    sample = {
        "incident_id": f"INC-DASH-{int(time.time())}",
        "service_name": "checkout-api",
        "severity": "High",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alert_type": "LatencySpike",
        "metric_name": "p99_latency_ms",
        "metric_value": 4200,
        "logs_summary": "Checkout API p99 latency breached threshold. Logs show database connection acquisition timeouts.",
    }
    col_a, col_b = st.columns([1, 4])
    with col_a:
        run = st.button("Run sample", type="primary", use_container_width=True)
    with col_b:
        st.code(json.dumps(sample, indent=2), language="json")
    if run:
        result = call_api(root_api_base(api_base), "POST", "/incidents/trigger", sample)
        if result:
            st.success(
                f"{result.get('incident_id')} | {safe_get(result, 'decision', 'route')} | "
                f"{result.get('status')}"
            )
            st.json(result)


with tabs[1]:
    st.subheader("Configured Log Sources")
    sources = data.get("log_sources", [])
    st.dataframe(sources, use_container_width=True, hide_index=True)

    enabled = [s for s in sources if s.get("configured")]
    labels = [
        f"{s.get('source')} / {s.get('name')} - {s.get('status')}"
        for s in enabled
    ]
    if labels:
        selected = st.selectbox("Tail log file", range(len(labels)), format_func=lambda i: labels[i])
        source = enabled[selected]
        lines = read_tail(source.get("path", ""), limit=100)
        level_filter = st.multiselect(
            "Levels", ["CRITICAL", "ERROR", "WARN", "INFO"],
            default=["CRITICAL", "ERROR", "WARN", "INFO"],
        )
        filtered = [line for line in lines if log_level(line) in level_filter]
        st.code("\n".join(filtered[-100:]) or "No readable lines.", language="text")
    else:
        st.info("No log paths are configured. Set Magento/AEM/Java/Python log paths in `.env`.")


with tabs[2]:
    st.subheader("Anomalies")
    anomalies = data.get("anomalies", [])
    if anomalies:
        st.dataframe(
            [
                {
                    "time": fmt_time(a.get("timestamp")),
                    "source": a.get("source"),
                    "service": a.get("service"),
                    "pattern": a.get("pattern"),
                    "occurrences": a.get("occurrences"),
                }
                for a in anomalies
            ],
            use_container_width=True,
            hide_index=True,
        )
        for item in anomalies[:10]:
            with st.expander(f"{fmt_time(item.get('timestamp'))} | {item.get('source')} | {item.get('pattern')}"):
                st.code(item.get("log_snippet", ""), language="text")
    else:
        st.info("No runtime anomalies captured yet.")


with tabs[3]:
    st.subheader("Agents")
    render_pipeline(data.get("agents", []))

    st.markdown("#### Current Agent State")
    agent_rows = data.get("agents", [])
    if agent_rows:
        st.dataframe(agent_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Agents are idle. Run an incident or let log monitoring trigger one.")

    st.markdown("#### LLM Token Usage")
    u1, u2, u3 = st.columns(3)
    u1.metric("Prompt tokens", f"{metrics.get('llm_prompt_tokens', 0):,}")
    u2.metric("Completion tokens", f"{metrics.get('llm_completion_tokens', 0):,}")
    u3.metric("Total tokens", f"{metrics.get('llm_total_tokens', 0):,}")
    usage = data.get("llm_usage", [])
    if usage:
        st.dataframe(usage[:50], use_container_width=True, hide_index=True)
    else:
        st.info("No LLM calls recorded in this API process yet.")


with tabs[4]:
    st.subheader("Agent Activity Timeline")
    activity = data.get("agent_activity", [])
    if activity:
        st.dataframe(
            [
                {
                    "time": fmt_time(a.get("timestamp")),
                    "incident_id": a.get("incident_id"),
                    "agent": a.get("agent"),
                    "status": a.get("status"),
                    "duration_ms": a.get("duration_ms"),
                    "error": a.get("error"),
                }
                for a in activity[:200]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No agent activity yet.")


with tabs[5]:
    st.subheader("Human Approval")
    render_human_approval_queue(api_base, incident_table_rows(data), "approval_tab")


with tabs[6]:
    st.subheader("LangGraph Workflow")
    render_langgraph(data)
    st.markdown("#### Recent Decision Paths")
    for path in safe_get(data, "langgraph", "recent_paths", default=[]):
        with st.expander(f"{path.get('incident_id')} | {path.get('status')}"):
            for step in path.get("decision_path", []):
                st.write(step)


with tabs[7]:
    st.subheader("RAG History and Vector Index")
    rag = data.get("rag", {})
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Status", rag.get("status", "-"))
    r2.metric("Vector store", rag.get("vector_store", "-"))
    r3.metric("Knowledge files", rag.get("knowledge_files", 0))
    r4.metric("Index ready", "yes" if rag.get("index_exists") else "no")

    query = st.text_input("Search knowledge base", value="Magento checkout SQLSTATE lock wait timeout")
    top_k = st.slider("Top K", 1, 20, 5)
    c_search, c_rebuild = st.columns([1, 1])
    if c_search.button("Search RAG", use_container_width=True):
        result = call_api(api_base, "POST", "/rag/search", {"query": query, "top_k": top_k})
        if result:
            for row in result.get("results", []):
                with st.expander(f"{row.get('source')} | score {row.get('score'):.4f}"):
                    st.write(row.get("text", ""))
    if c_rebuild.button("Rebuild Vector Index", use_container_width=True):
        result = call_api(api_base, "POST", "/rag/rebuild")
        if result:
            st.success(f"Rebuilt {result.get('chunk_count', 0)} chunks")
            st.json(result)


with tabs[8]:
    st.subheader("KPI Feeds")
    rows = incident_table_rows(data)
    decisions = safe_get(data, "distributions", "decisions", default={})
    severities = safe_get(data, "distributions", "severities", default={})
    anomaly_sources = safe_get(data, "distributions", "anomaly_sources", default={})

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### Decisions")
        st.json(decisions)
    with col2:
        st.markdown("#### Severities")
        st.json(severities)
    with col3:
        st.markdown("#### Anomaly Sources")
        st.json(anomaly_sources)

    service_counts: dict[str, int] = {}
    for row in rows:
        service = row.get("service") or "unknown"
        service_counts[service] = service_counts.get(service, 0) + 1
    st.markdown("#### Service Incident Counts")
    st.json(service_counts)


if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
