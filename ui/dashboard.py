"""
ui/dashboard.py
---------------
Enterprise AI Ops dashboard for the Agentic Support Framework.

Run:
    streamlit run ui/dashboard.py

Start the API first:
    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import html
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st


DEFAULT_API_BASE = "http://localhost:8000/api/v1"
WORKFLOW_STAGES = ["Sense", "Analyze", "Decide", "Approve", "Execute", "Learn"]
AGENT_ORDER = [
    "IncidentDetectionAgent",
    "RCAAgent",
    "DecisionAgent",
    "RemediationAgent",
    "ValidationAgent",
    "CommunicationAgent",
]


st.set_page_config(
    page_title="AI Ops Control Center",
    page_icon=":material/monitoring:",
    layout="wide",
    initial_sidebar_state="collapsed",
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
        st.toast(f"API call failed: {method} {path} - {exc}", icon=":material/error:")
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


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def display_text(value: Any) -> str:
    text = str(value if value is not None else "")
    replacements = {
        "Mock - ": "",
        "Mock-": "",
        "(Mock - RAG-augmented)": "(RAG-augmented)",
        "mock": "local",
        "MOCK": "LOCAL",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def display_status(value: Any) -> str:
    text = display_text(value)
    return "local" if text.lower() == "mock" else text


def fmt_time(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
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


def incident_rows(data: dict) -> list[dict]:
    rows = safe_get(data, "mongodb", "recent_incidents", default=[]) or []
    normalized: list[dict] = []
    for item in rows:
        normalized.append(
            {
                "incident_id": item.get("incident_id"),
                "service": item.get("service") or "unknown",
                "severity": item.get("severity") or "LOW",
                "status": item.get("status") or "OPEN",
                "decision": item.get("decision") or "-",
                "approval_status": item.get("approval_status") or "-",
                "validation": safe_get(item, "validation", "status", default="-"),
                "updated": item.get("updated_at") or item.get("timestamp"),
                "rca_summary": safe_get(item, "rca", "rca_text", default="No RCA summary available."),
            }
        )
    if normalized:
        return normalized
    return safe_get(data, "incidents", default=[]) or []


def pending_approval_rows(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("decision") in {"HUMAN_APPROVAL", "human_review"}
        and row.get("approval_status") in {None, "PENDING_APPROVAL", "pending"}
    ]


def severity_class(severity: str) -> str:
    value = (severity or "").lower()
    if value == "critical":
        return "sev-critical"
    if value == "high":
        return "sev-high"
    if value == "medium":
        return "sev-medium"
    if value == "low":
        return "sev-low"
    return "sev-muted"


def status_class(status: str) -> str:
    value = (status or "").lower()
    if value in {"ready", "online", "ok", "connected", "resolved", "validated", "tailing"}:
        return "status-good"
    if value in {"pending", "pending_approval", "human_approval", "awaiting_approval"}:
        return "status-warn"
    if value in {"failed", "offline", "critical", "not_ready"}:
        return "status-danger"
    return "status-neutral"


def icon(name: str, size: int = 18) -> str:
    paths = {
        "activity": '<path d="M22 12h-4l-3 8-6-16-3 8H2"/>',
        "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        "approve": '<path d="M20 6 9 17l-5-5"/>',
        "archive": '<path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/>',
        "bell": '<path d="M10.268 21a2 2 0 0 0 3.464 0"/><path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .738-1.674C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/>',
        "brain": '<path d="M12 5a3 3 0 1 0-5.997.125A4 4 0 0 0 5.5 13H6"/><path d="M12 5a3 3 0 1 1 5.997.125A4 4 0 0 1 18.5 13H18"/><path d="M15 13a4 4 0 0 1-3 3.87A4 4 0 0 1 9 13"/><path d="M12 5v12"/><path d="M7 9h10"/>',
        "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.657 4.03 3 9 3s9-1.343 9-3V5"/><path d="M3 12c0 1.657 4.03 3 9 3s9-1.343 9-3"/>',
        "lightning": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
        "logs": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>',
        "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
        "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.51a2 2 0 0 1 1-1.72l.15-.1a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
        "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.68-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
        "sparkles": '<path d="M12 3l1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
        "user": '<path d="M19 21a7 7 0 0 0-14 0"/><circle cx="12" cy="7" r="4"/>',
    }
    return (
        f'<svg class="lucide" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{paths.get(name, paths["activity"])}</svg>'
    )


def render_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {
            --primary:#2F80ED;
            --secondary:#56CCF2;
            --accent:#00B8D9;
            --success:#27AE60;
            --warning:#F2C94C;
            --danger:#EB5757;
            --bg:#F5F9FD;
            --card:#FFFFFF;
            --border:#E6EEF5;
            --text:#1F2937;
            --muted:#64748B;
            --purple:#7C3AED;
            --orange:#F2994A;
        }

        html, body, [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(86,204,242,.22), transparent 34rem),
                linear-gradient(180deg, #F7FBFF 0%, var(--bg) 100%);
            color: var(--text);
            font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .block-container {
            max-width: 1560px;
            padding: 1.25rem 2rem 2.5rem;
        }

        header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu {
            display: none;
            visibility: hidden;
        }

        [data-testid="stSidebar"] {
            background: rgba(255,255,255,.82);
            border-right: 1px solid var(--border);
            backdrop-filter: blur(20px);
        }

        h1, h2, h3, p {letter-spacing: 0;}
        div[data-testid="stVerticalBlock"] {gap: .9rem;}
        div[data-testid="stHorizontalBlock"] {gap: 1rem;}
        button, input, textarea, select {font-family: Inter, sans-serif;}

        div[data-testid="stButton"] > button {
            border-radius: 12px;
            border: 1px solid var(--border);
            box-shadow: 0 8px 18px rgba(47,128,237,.08);
            transition: all .18s ease;
        }
        div[data-testid="stButton"] > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 12px 24px rgba(47,128,237,.14);
        }
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: white;
            border: 0;
        }
        div[data-baseweb="tab-list"] {gap: .4rem; border-bottom: 1px solid var(--border);}
        button[data-baseweb="tab"] {
            border-radius: 12px 12px 0 0;
            padding: .65rem 1rem;
            font-weight: 650;
        }

        .top-nav {
            position: sticky;
            top: 0;
            z-index: 20;
            display: grid;
            grid-template-columns: 180px 190px 1fr auto;
            gap: 14px;
            align-items: center;
            padding: 13px 16px;
            margin: -8px 0 20px;
            background: rgba(255,255,255,.78);
            border: 1px solid rgba(230,238,245,.9);
            border-radius: 14px;
            backdrop-filter: blur(22px);
            box-shadow: 0 18px 46px rgba(31,41,55,.07);
        }
        .brand {
            display:flex;
            align-items:center;
            gap:10px;
            font-weight:800;
            color:var(--text);
        }
        .brand-mark {
            width:36px;
            height:36px;
            border-radius:12px;
            display:grid;
            place-items:center;
            color:white;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            box-shadow: 0 12px 26px rgba(47,128,237,.28);
        }
        .nav-select, .nav-search, .nav-action {
            min-height:38px;
            border:1px solid var(--border);
            border-radius:12px;
            background:rgba(255,255,255,.88);
            color:var(--muted);
            display:flex;
            align-items:center;
            gap:8px;
            padding:0 12px;
            font-size:13px;
            font-weight:600;
        }
        .nav-actions {display:flex; gap:10px; align-items:center;}
        .avatar {
            width:34px;
            height:34px;
            border-radius:999px;
            background:linear-gradient(135deg, #EEF6FF, #DDF7FF);
            border:1px solid var(--border);
            display:grid;
            place-items:center;
            color:var(--primary);
        }

        .hero {
            display:grid;
            grid-template-columns: minmax(0, 1fr) 520px;
            gap: 24px;
            align-items: stretch;
            margin-bottom: 20px;
        }
        .hero-card, .glass-card, .kpi-card, .panel-card {
            background: rgba(255,255,255,.88);
            border: 1px solid rgba(230,238,245,.92);
            border-radius: 14px;
            box-shadow: 0 18px 45px rgba(31,41,55,.07);
            backdrop-filter: blur(18px);
        }
        .hero-card {
            padding: 30px;
            overflow:hidden;
            position:relative;
        }
        .hero-card::after {
            content:"";
            position:absolute;
            right:-90px;
            top:-90px;
            width:260px;
            height:260px;
            background: radial-gradient(circle, rgba(86,204,242,.24), transparent 62%);
        }
        .eyebrow {
            color: var(--primary);
            font-weight: 800;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing:.06em;
            margin-bottom: 10px;
        }
        .hero-title {
            font-size: 46px;
            line-height: 1.04;
            font-weight: 820;
            color: var(--text);
            margin-bottom: 12px;
        }
        .hero-subtitle {
            font-size: 17px;
            line-height:1.65;
            color: var(--muted);
            max-width: 760px;
        }
        .status-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            padding: 16px;
        }
        .status-card {
            background: linear-gradient(180deg, rgba(255,255,255,.95), rgba(248,251,255,.88));
            border: 1px solid var(--border);
            border-radius:14px;
            padding: 14px;
            min-height:82px;
        }
        .status-top {display:flex; align-items:center; justify-content:space-between; gap:10px;}
        .status-label {font-size:12px; font-weight:750; color:var(--muted); text-transform:uppercase;}
        .status-value {font-size:18px; font-weight:800; color:var(--text); margin-top:8px;}
        .pill {
            display:inline-flex;
            align-items:center;
            gap:6px;
            border-radius:999px;
            padding:4px 9px;
            font-size:12px;
            font-weight:750;
            border:1px solid var(--border);
            background:#F8FAFC;
            color:var(--muted);
            white-space:nowrap;
        }
        .status-good {background:#EAF8F0;color:var(--success);border-color:#CDEEDB;}
        .status-warn {background:#FFF8DB;color:#9A6B00;border-color:#F8E7A5;}
        .status-danger {background:#FDECEC;color:var(--danger);border-color:#F7CACA;}
        .status-neutral {background:#F1F5F9;color:var(--muted);border-color:#E2E8F0;}

        .kpi-grid {
            display:grid;
            grid-template-columns: repeat(8, minmax(128px, 1fr));
            gap: 14px;
            margin-bottom: 20px;
        }
        .kpi-card {
            padding: 15px;
            min-height: 134px;
            transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
            animation: fadeUp .36s ease both;
        }
        .kpi-card:hover {
            transform: translateY(-4px);
            border-color: rgba(47,128,237,.32);
            box-shadow: 0 22px 54px rgba(47,128,237,.12);
        }
        .kpi-head {display:flex; justify-content:space-between; align-items:center; gap:10px;}
        .kpi-icon {
            width:34px;
            height:34px;
            border-radius:12px;
            display:grid;
            place-items:center;
            color:var(--primary);
            background:#EEF6FF;
        }
        .kpi-label {font-size:12px; color:var(--muted); font-weight:700;}
        .kpi-value {
            font-size:30px;
            font-weight:820;
            color:var(--text);
            margin-top:12px;
            animation: countPop .45s ease both;
        }
        .kpi-trend {font-size:12px; color:var(--success); font-weight:700; margin-top:2px;}

        .workflow {
            display:grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 10px;
            padding: 16px;
            position:relative;
        }
        .workflow-node {
            position:relative;
            display:flex;
            flex-direction:column;
            align-items:center;
            gap:8px;
            color:var(--muted);
            text-align:center;
        }
        .workflow-node:not(:last-child)::after {
            content:"";
            position:absolute;
            top:26px;
            left:calc(50% + 32px);
            width:calc(100% - 54px);
            height:2px;
            background:linear-gradient(90deg, var(--primary), var(--secondary));
            opacity:.45;
            animation: connectorFlow 1.7s infinite ease-in-out;
        }
        .workflow-icon {
            width:54px;
            height:54px;
            border-radius:999px;
            display:grid;
            place-items:center;
            background:linear-gradient(180deg, #F0F7FF, #E7F8FF);
            border:1px solid #D7EAFB;
            color:var(--primary);
            box-shadow: 0 12px 28px rgba(47,128,237,.12);
        }
        .workflow-node.active .workflow-icon {
            color:white;
            background:linear-gradient(135deg, var(--primary), var(--accent));
            animation: pulse 1.8s infinite;
        }
        .workflow-label {font-size:13px; font-weight:800; color:var(--text);}
        .workflow-caption {font-size:11px; color:var(--muted);}

        .workspace-grid {
            display:grid;
            grid-template-columns: minmax(240px, 25%) minmax(420px, 50%) minmax(260px, 25%);
            gap: 16px;
            align-items:start;
        }
        .panel-card {padding:16px; min-height: 120px;}
        .panel-header {
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
            margin-bottom: 12px;
        }
        .panel-title {font-size:16px; font-weight:820; color:var(--text);}
        .panel-subtitle {font-size:12px; color:var(--muted);}
        .feed-item {
            border:1px solid var(--border);
            background:#FFFFFF;
            border-radius:14px;
            padding:12px;
            margin-bottom:10px;
            transition:all .18s ease;
            cursor:pointer;
        }
        .feed-item:hover, .feed-item.selected {
            border-color:rgba(47,128,237,.4);
            box-shadow:0 16px 34px rgba(47,128,237,.10);
            transform: translateY(-2px);
        }
        .feed-top {display:flex; align-items:center; justify-content:space-between; gap:10px;}
        .feed-id {font-size:13px; font-weight:800; color:var(--text);}
        .feed-service {font-size:12px; color:var(--muted); margin-top:6px;}
        .chip {
            display:inline-flex;
            align-items:center;
            border-radius:999px;
            padding:4px 9px;
            font-size:11px;
            font-weight:800;
            border:1px solid transparent;
        }
        .sev-critical {background:#FDECEC;color:var(--danger);border-color:#F6C9C9;}
        .sev-high {background:#FFF1E5;color:var(--orange);border-color:#FFD9B8;}
        .sev-medium {background:#EAF3FF;color:var(--primary);border-color:#CFE3FF;}
        .sev-low {background:#EAF8F0;color:var(--success);border-color:#CDEEDB;}
        .sev-muted {background:#F1F5F9;color:var(--muted);border-color:#E2E8F0;}
        .ai-chip {background:#F3E8FF;color:var(--purple);border-color:#E5D4FF;}
        .approval-chip {background:#FFF8DB;color:#9A6B00;border-color:#F8E7A5;}
        .resolved-chip {background:#EEF2F7;color:#64748B;border-color:#E2E8F0;}

        .workspace-title {font-size:22px; font-weight:840; color:var(--text);}
        .timeline {
            display:flex;
            gap:8px;
            flex-wrap:wrap;
            margin: 10px 0 4px;
        }
        .timeline-step {
            display:flex;
            align-items:center;
            gap:6px;
            padding:7px 10px;
            border-radius:999px;
            border:1px solid var(--border);
            font-size:12px;
            color:var(--muted);
            background:#FAFCFF;
        }
        .timeline-step.done {color:var(--success); background:#EAF8F0; border-color:#CDEEDB;}
        .accordion-card {
            border:1px solid var(--border);
            border-radius:14px;
            background:#FFFFFF;
            padding:14px;
            margin-top:12px;
            animation: slideIn .25s ease both;
        }
        .summary-text {font-size:14px; line-height:1.65; color:var(--text);}
        .confidence {
            height:10px;
            border-radius:999px;
            background:#E8F1FA;
            overflow:hidden;
            margin-top:8px;
        }
        .confidence > span {
            display:block;
            height:100%;
            border-radius:999px;
            background:linear-gradient(90deg, var(--primary), var(--accent));
            animation: growBar .8s ease both;
        }
        .assistant-card {
            background:linear-gradient(180deg, rgba(255,255,255,.95), rgba(247,251,255,.94));
        }
        .chat-bubble {
            border-radius:14px;
            padding:12px;
            margin-bottom:10px;
            font-size:13px;
            line-height:1.55;
        }
        .chat-ai {background:#EEF6FF;color:var(--text); border:1px solid #D8EAFF;}
        .chat-user {background:#FFFFFF;color:var(--muted); border:1px solid var(--border);}
        .typing {display:inline-flex; gap:4px; align-items:center;}
        .typing span {
            width:6px;
            height:6px;
            border-radius:999px;
            background:var(--primary);
            animation: typing 1.2s infinite ease-in-out;
        }
        .typing span:nth-child(2) {animation-delay:.15s;}
        .typing span:nth-child(3) {animation-delay:.3s;}
        .article-item {
            border-top:1px solid var(--border);
            padding:10px 0;
            font-size:13px;
        }
        .article-item strong {color:var(--text);}
        .article-item span {color:var(--muted);}

        .chart-grid {
            display:grid;
            grid-template-columns: 1.4fr 1fr 1fr;
            gap:16px;
            margin: 18px 0;
        }
        @keyframes fadeUp {from {opacity:0; transform:translateY(8px);} to {opacity:1; transform:none;}}
        @keyframes countPop {from {opacity:.25; transform:scale(.96);} to {opacity:1; transform:scale(1);}}
        @keyframes pulse {0%,100% {box-shadow:0 0 0 0 rgba(47,128,237,.25);} 50% {box-shadow:0 0 0 10px rgba(47,128,237,0);}}
        @keyframes connectorFlow {0%,100% {opacity:.25;} 50% {opacity:.75;}}
        @keyframes growBar {from {width:0;} }
        @keyframes slideIn {from {opacity:0; transform:translateX(8px);} to {opacity:1; transform:none;}}
        @keyframes typing {0%,80%,100% {opacity:.25; transform:translateY(0);} 40% {opacity:1; transform:translateY(-2px);}}

        @media (max-width: 1180px) {
            .top-nav, .hero, .workspace-grid, .chart-grid {grid-template-columns:1fr;}
            .kpi-grid {grid-template-columns: repeat(4, minmax(0, 1fr));}
            .workflow {grid-template-columns: repeat(3, minmax(0, 1fr));}
            .workflow-node::after {display:none;}
        }
        @media (max-width: 720px) {
            .block-container {padding: 1rem;}
            .kpi-grid {grid-template-columns: repeat(2, minmax(0, 1fr));}
            .workflow {grid-template-columns: repeat(2, minmax(0, 1fr));}
            .hero-title {font-size:34px;}
            .status-grid {grid-template-columns:1fr;}
            .top-nav {gap:10px;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def pill_html(label: str, state: str | None = None, icon_name: str | None = None) -> str:
    css = status_class(state or label)
    icon_html = icon(icon_name, 14) if icon_name else ""
    return f'<span class="pill {css}">{icon_html}{esc(label)}</span>'


def kpi_card(title: str, value: Any, detail: str, icon_name: str, color: str) -> str:
    return (
        f'<div class="kpi-card" tabindex="0" aria-label="{esc(title)} {esc(value)}">'
        f'<div class="kpi-head">'
        f'<div class="kpi-label">{esc(title)}</div>'
        f'<div class="kpi-icon" style="color:{color};background:{color}14">{icon(icon_name, 18)}</div>'
        f'</div>'
        f'<div class="kpi-value">{esc(value)}</div>'
        f'<div class="kpi-trend">{esc(detail)}</div>'
        f'</div>'
    )


def render_top_nav() -> None:
    st.markdown(
        f"""
        <nav class="top-nav" aria-label="Primary navigation">
          <div class="brand">
            <div class="brand-mark">{icon("sparkles", 18)}</div>
            <span>AI Ops</span>
          </div>
          <div class="nav-select">{icon("shield", 16)} Production</div>
          <div class="nav-search">{icon("search", 16)} Search incidents, services, runbooks</div>
          <div class="nav-actions">
            <div class="nav-action">{icon("bell", 16)}</div>
            <div class="nav-action">{icon("activity", 16)} Light</div>
            <div class="avatar">{icon("user", 16)}</div>
            <div class="nav-action">Current User</div>
            <div class="nav-action">{icon("settings", 16)}</div>
          </div>
        </nav>
        """,
        unsafe_allow_html=True,
    )


def render_hero(health: dict | None, data: dict) -> None:
    rag = data.get("rag", {})
    mongo = data.get("mongodb", {})
    status_items = [
        ("API", "online" if health else "offline", "activity"),
        ("LLM", display_status(safe_get(health, "llm_status", default="unknown")), "brain"),
        ("RAG", rag.get("status", "unknown"), "sparkles"),
        ("Knowledge Base", f"{rag.get('knowledge_files', 0)} articles", "archive"),
        ("Database", "connected" if mongo.get("connected") else "local/offline", "database"),
        ("Automation", "policy gated", "shield"),
    ]
    cards = "".join(
        f"""
        <div class="status-card">
          <div class="status-top">
            <span class="status-label">{esc(label)}</span>
            {pill_html(status, status, icon_name)}
          </div>
          <div class="status-value">{esc(display_text(status))}</div>
        </div>
        """
        for label, status, icon_name in status_items
    )
    st.markdown(
        f"""
        <section class="hero">
          <div class="hero-card">
            <div class="eyebrow">Autonomous Incident Intelligence Platform</div>
            <div class="hero-title">AI Ops Control Center</div>
            <div class="hero-subtitle">
              Sense incidents across operational signals, analyze them with RAG-backed agents,
              route decisions through policy and approval, and continuously improve the knowledge base.
            </div>
          </div>
          <div class="glass-card status-grid" aria-label="Connection status">
            {cards}
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(metrics: dict, rows: list[dict], data: dict) -> None:
    critical = sum(1 for row in rows if str(row.get("severity", "")).upper() == "CRITICAL")
    pending = len(pending_approval_rows(rows))
    rag_articles = safe_get(data, "rag", "knowledge_files", default=0)
    values = [
        ("Total Incidents", metrics.get("incidents_total", len(rows)), "from live incident store", "activity", "#2F80ED"),
        ("Open Incidents", metrics.get("incidents_open", 0), "currently active", "alert", "#00B8D9"),
        ("Critical Incidents", critical, "computed from incident feed", "shield", "#EB5757"),
        ("Auto Resolved", metrics.get("auto_resolved", 0), "from pipeline results", "approve", "#27AE60"),
        ("Pending Approval", pending, "approval queue count", "bell", "#F2C94C"),
        ("Anomalies", metrics.get("anomalies_1h", 0), "captured in the last hour", "logs", "#56CCF2"),
        ("LLM Requests", metrics.get("llm_calls", 0), "recorded by API runtime", "brain", "#7C3AED"),
        ("Knowledge Articles", rag_articles, "indexed knowledge files", "archive", "#00B8D9"),
    ]
    columns = st.columns(8)
    for column, item in zip(columns, values):
        with column:
            st.markdown(kpi_card(*item), unsafe_allow_html=True)


def render_workflow(active_index: int = 2) -> None:
    captions = ["Signals", "RCA", "Policy", "Gate", "Runbook", "Memory"]
    icons = ["activity", "brain", "shield", "approve", "lightning", "database"]
    st.markdown(
        '<div class="panel-card" style="margin-bottom:10px"><div class="panel-header"><div>'
        '<div class="panel-title">Operator Workflow</div>'
        '<div class="panel-subtitle">Autonomous pipeline with approval-aware execution</div>'
        f'</div>{pill_html("Current stage: Decide", "running", "activity")}</div></div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(6)
    for index, (column, stage) in enumerate(zip(columns, WORKFLOW_STAGES)):
        active = " active" if index == active_index else ""
        with column:
            st.markdown(
                f'<div class="workflow-node{active}" tabindex="0">'
                f'<div class="workflow-icon">{icon(icons[index], 22)}</div>'
                f'<div class="workflow-label">{esc(stage)}</div>'
                f'<div class="workflow-caption">{esc(captions[index])}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def feed_item(row: dict, selected: bool) -> str:
    selected_class = " selected" if selected else ""
    severity = str(row.get("severity") or "LOW")
    return f"""
    <div class="feed-item{selected_class}">
      <div class="feed-top">
        <div class="feed-id">{esc(row.get("incident_id"))}</div>
        <span class="chip {severity_class(severity)}">{esc(severity)}</span>
      </div>
      <div class="feed-service">{esc(row.get("service"))} · {esc(fmt_time(row.get("updated")))}</div>
      <div style="margin-top:8px">{pill_html(row.get("status", "unknown"), row.get("status"))}</div>
    </div>
    """


def render_incident_feed(rows: list[dict], selected_id: str | None) -> None:
    feed = "".join(feed_item(row, row.get("incident_id") == selected_id) for row in rows[:5])
    if not feed:
        feed = '<div class="feed-item"><div class="feed-id">No incidents yet</div><div class="feed-service">Waiting for live incidents from the API.</div></div>'
    st.markdown(
        f"""
        <div class="panel-card">
          <div class="panel-header">
            <div>
              <div class="panel-title">Incident Feed</div>
              <div class="panel-subtitle">Newest signals across services</div>
            </div>
            {pill_html("Filter", "neutral", "search")}
          </div>
          <div class="nav-search" style="margin-bottom:12px">{icon("search", 15)} Search feed</div>
          {feed}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workspace(row: dict | None, rows: list[dict], api_base: str) -> None:
    incident_id = row.get("incident_id") if row else "No incident selected"
    severity = row.get("severity", "LOW") if row else "-"
    status = row.get("status", "-") if row else "-"
    decision = row.get("decision", "-") if row else "-"
    related = [item for item in rows if row and item.get("service") == row.get("service")][:4]
    related_html = "".join(
        f'<span class="chip {severity_class(str(item.get("severity")))}">{esc(item.get("incident_id"))}</span> '
        for item in related
    ) or '<span class="chip sev-muted">No related incidents</span>'
    summary = row.get("rca_summary") if row else "Select an incident to inspect the AI-generated operational context."
    if summary and len(summary) > 260:
        summary = summary[:260] + "..."
    summary = display_text(str(summary).replace("**", ""))

    st.markdown(
        f"""
        <div class="panel-card">
          <div class="panel-header">
            <div>
              <div class="workspace-title">{esc(incident_id)}</div>
              <div class="panel-subtitle">{esc(row.get("service", "unknown") if row else "-")} · {esc(decision)}</div>
            </div>
            <span class="chip {severity_class(str(severity))}">{esc(severity)}</span>
          </div>
          <div class="timeline">
            <span class="timeline-step done">{icon("activity", 14)} Sensed</span>
            <span class="timeline-step done">{icon("brain", 14)} Analyzed</span>
            <span class="timeline-step done">{icon("shield", 14)} Decided</span>
            <span class="timeline-step">{icon("approve", 14)} Approval</span>
            <span class="timeline-step">{icon("database", 14)} Learned</span>
          </div>
          <div class="accordion-card">
            <div class="panel-title">AI Summary</div>
            <p class="summary-text">{esc(summary)}</p>
            <span class="chip ai-chip">AI Generated</span>
            <span class="chip {status_class(status)}">{esc(status)}</span>
          </div>
          <div class="accordion-card">
            <div class="panel-title">Root Cause</div>
            <p class="summary-text">RAG context and incident evidence are available for review. Use approval controls only when the incident policy requires operator action.</p>
          </div>
          <div class="accordion-card">
            <div class="panel-title">Related Incidents</div>
            <div style="margin-top:10px">{related_html}</div>
          </div>
          <div class="accordion-card">
            <div class="panel-title">Metrics Preview</div>
            <p class="summary-text">p99 latency, error-rate trend, and log anomaly density are available from the incident payload and monitoring feeds.</p>
            <div class="confidence"><span style="width:82%"></span></div>
            <div class="panel-subtitle">Confidence score 82%</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        approve_col, reject_col, escalate_col = st.columns(3)
        approve_col.button("Approve", type="primary", use_container_width=True, disabled=not row)
        reject_col.button("Reject", use_container_width=True, disabled=not row)
        escalate_col.button("Escalate", use_container_width=True, disabled=not row)

def render_assistant(row: dict | None, data: dict) -> None:
    incident_id = row.get("incident_id") if row else "selected incident"
    rag_count = safe_get(data, "rag", "knowledge_files", default=0)
    articles = [(f"Knowledge source {index}", "Indexed by RAG context engine") for index in range(1, min(int(rag_count or 0), 3) + 1)]
    article_html = "".join(
        f'<div class="article-item"><strong>{esc(title)}</strong><br><span>{esc(meta)}</span></div>'
        for title, meta in articles
    ) or '<div class="article-item"><strong>No indexed articles reported</strong><br><span>RAG status endpoint has no article rows.</span></div>'
    decisions = safe_get(data, "distributions", "decisions", default={}) or {}
    decision_text = ", ".join(f"{key}: {value}" for key, value in decisions.items()) or "No recent decisions"
    st.markdown(
        f"""
        <div class="panel-card assistant-card">
          <div class="panel-header">
            <div>
              <div class="panel-title">AI Assistant</div>
              <div class="panel-subtitle">Operational copilot for incident response</div>
            </div>
            {pill_html("online", "online", "sparkles")}
          </div>
          <div class="chat-bubble chat-ai">
            I reviewed {esc(incident_id)} using the latest incident and knowledge data returned by the API.
          </div>
          <div class="chat-bubble chat-ai">
            Suggested action depends on the current decision and approval state. Review the workspace before taking action.
          </div>
          <div class="chat-bubble chat-ai">
            <span class="typing"><span></span><span></span><span></span></span>
          </div>
          <div class="panel-title" style="margin-top:12px">Runbook Recommendations</div>
          {article_html}
          <div class="panel-title" style="margin-top:12px">Recent Decisions</div>
          <p class="summary-text">{esc(decision_text)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_grid(rows: list[dict], selected_id: str | None, api_base: str, data: dict) -> None:
    selected = next((row for row in rows if row.get("incident_id") == selected_id), rows[0] if rows else None)
    left, center, right = st.columns([1, 2, 1])
    with left:
        render_incident_feed(rows, selected_id)
    with center:
        render_workspace(selected, rows, api_base)
    with right:
        render_assistant(selected, data)


def render_bottom_tabs(data: dict, rows: list[dict]) -> None:
    kb_tab, diagnostics_tab, audit_tab = st.tabs(["Knowledge Base", "Diagnostics", "Audit Trail"])
    with kb_tab:
        rag = data.get("rag", {})
        st.dataframe(pd.DataFrame([rag]) if rag else pd.DataFrame(), use_container_width=True, hide_index=True)
    with diagnostics_tab:
        st.dataframe(data.get("log_sources", []), use_container_width=True, hide_index=True)
    with audit_tab:
        audit_rows = [
            {
                "Time": fmt_time(row.get("updated")),
                "Incident": row.get("incident_id"),
                "Action": row.get("decision"),
                "Actor": "system",
                "Status": row.get("status"),
            }
            for row in rows[:50]
        ]
        st.dataframe(pd.DataFrame(audit_rows), use_container_width=True, hide_index=True)


render_css()

with st.sidebar:
    st.markdown("### Workspace")
    api_base = st.text_input("API base URL", value=DEFAULT_API_BASE)
    refresh_seconds = st.slider("Refresh interval", 2, 30, 5)
    auto_refresh = st.toggle("Auto refresh", value=True)
    st.selectbox("Environment", ["Production", "Staging", "Development"])
    st.toggle("Dark mode", value=False, help="Light theme remains optimized for presentation.")


health = call_api(api_base, "GET", "/health")
data = call_api(api_base, "GET", "/dashboard/status") or {}
metrics = data.get("metrics", {})
rows = incident_rows(data)
selected_options = [row.get("incident_id") for row in rows] or ["No incidents"]
selected_id = selected_options[0]

render_top_nav()
render_hero(health, data)
render_kpis(metrics, rows, data)
render_workflow(active_index=2)

render_workspace_grid(rows, selected_id, api_base, data)

render_bottom_tabs(data, rows)

if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
