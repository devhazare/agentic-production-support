from __future__ import annotations

import time
from typing import Callable

from agents.ops_nodes import (
    approval_agent,
    communication_agent,
    decision_agent,
    incident_agent,
    learning_agent,
    mock_remediation_agent,
    rca_agent,
    retrieval_agent,
)
from agents.ops_nodes import set_runtime_services
from core.config.settings import get_settings
from models import ApprovalStatus, IncidentEvent, IncidentState
from services.audit_log import AuditService
from services.bedrock_rca import BedrockRCAClient
from services.aws_knowledge import KnowledgeService
from services.ops_store import IncidentStore


class _FallbackGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Callable[[IncidentState], IncidentState]] = {}

    def add_node(self, name: str, fn: Callable[[IncidentState], IncidentState]) -> None:
        self.nodes[name] = fn

    def invoke(self, state: IncidentState) -> IncidentState:
        for name in ["incident_agent", "retrieval_agent", "rca_agent", "decision_agent"]:
            state = self.nodes[name](state)
            if state.status in {"duplicate", "error"}:
                return self.nodes["learning_agent"](state)
        if state.decision and state.decision.route == "human_review":
            for name in ["approval_agent", "communication_agent", "learning_agent"]:
                state = self.nodes[name](state)
            return state
        for name in ["approval_agent", "mock_remediation_agent", "communication_agent", "learning_agent"]:
            state = self.nodes[name](state)
        return state


class IncidentWorkflow:
    def __init__(self, store: IncidentStore) -> None:
        self.store = store
        settings = store.settings if hasattr(store, "settings") else get_settings()
        audit = AuditService(settings)
        set_runtime_services(store, audit, KnowledgeService(settings), BedrockRCAClient(settings, audit))
        self.graph = self._build_graph()

    def run(self, event: IncidentEvent) -> IncidentState:
        state = IncidentState(incident_id=event.incident_id, event=event)
        try:
            result = self.graph.invoke(state, config={"configurable": {"thread_id": event.incident_id}})
        except TypeError:
            result = self.graph.invoke(state)
        return result if isinstance(result, IncidentState) else IncidentState.model_validate(result)

    def approve(self, incident_id: str, approver: str, comment: str = "") -> IncidentState:
        state = self._require_state(incident_id)
        if not state.approval:
            raise ValueError("Incident has no approval request")
        state.approval.status = ApprovalStatus.APPROVED
        state.approval.approver = approver
        state.approval.comment = comment
        state.decision_path.append("human_approval: approved")
        if state.decision:
            state.decision.allowed_action = state.rca.recommended_action_type if state.rca else None
        for node in [mock_remediation_agent, communication_agent, learning_agent]:
            state = node(state)
        return state

    def reject(self, incident_id: str, approver: str, comment: str = "") -> IncidentState:
        state = self._require_state(incident_id)
        if not state.approval:
            raise ValueError("Incident has no approval request")
        state.approval.status = ApprovalStatus.REJECTED
        state.approval.approver = approver
        state.approval.comment = comment
        state.status = "rejected"
        state.decision_path.append("human_approval: rejected")
        for node in [mock_remediation_agent, communication_agent, learning_agent]:
            state = node(state)
        return state

    def needs_more_info(self, incident_id: str, approver: str, comment: str = "") -> IncidentState:
        state = self._require_state(incident_id)
        if not state.approval:
            raise ValueError("Incident has no approval request")
        state.approval.status = ApprovalStatus.NEEDS_MORE_INFO
        state.approval.approver = approver
        state.approval.comment = comment
        state.status = "needs_more_info"
        state.decision_path.append("human_approval: needs_more_info")
        return learning_agent(communication_agent(state))

    def _require_state(self, incident_id: str) -> IncidentState:
        state = self.store.get(incident_id)
        if not state:
            raise KeyError(f"Incident {incident_id} not found")
        return state

    def _build_graph(self):
        try:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.graph import END, StateGraph

            builder = StateGraph(IncidentState)
            builder.add_node("incident_agent", self._retry_node("incident_agent", incident_agent))
            builder.add_node("retrieval_agent", self._retry_node("retrieval_agent", retrieval_agent))
            builder.add_node("rca_agent", self._retry_node("rca_agent", rca_agent))
            builder.add_node("decision_agent", self._retry_node("decision_agent", decision_agent))
            builder.add_node("approval_agent", self._retry_node("approval_agent", approval_agent))
            builder.add_node(
                "mock_remediation_agent",
                self._retry_node("mock_remediation_agent", mock_remediation_agent),
            )
            builder.add_node("communication_agent", self._retry_node("communication_agent", communication_agent))
            builder.add_node("learning_agent", self._retry_node("learning_agent", learning_agent))
            builder.set_entry_point("incident_agent")
            builder.add_conditional_edges(
                "incident_agent",
                lambda s: "stop" if s.status in {"duplicate", "error"} else "continue",
                {"stop": "learning_agent", "continue": "retrieval_agent"},
            )
            builder.add_edge("retrieval_agent", "rca_agent")
            builder.add_edge("rca_agent", "decision_agent")
            builder.add_conditional_edges(
                "decision_agent",
                lambda s: "approval" if s.decision and s.decision.route == "human_review" else "remediate",
                {"approval": "approval_agent", "remediate": "approval_agent"},
            )
            builder.add_conditional_edges(
                "approval_agent",
                lambda s: "wait" if s.status == "awaiting_approval" else "remediate",
                {"wait": "communication_agent", "remediate": "mock_remediation_agent"},
            )
            builder.add_edge("mock_remediation_agent", "communication_agent")
            builder.add_edge("communication_agent", "learning_agent")
            builder.add_edge("learning_agent", END)
            return builder.compile(checkpointer=MemorySaver())
        except Exception:
            graph = _FallbackGraph()
            for name, fn in {
                "incident_agent": incident_agent,
                "retrieval_agent": retrieval_agent,
                "rca_agent": rca_agent,
                "decision_agent": decision_agent,
                "approval_agent": approval_agent,
                "mock_remediation_agent": mock_remediation_agent,
                "communication_agent": communication_agent,
                "learning_agent": learning_agent,
            }.items():
                graph.add_node(name, self._retry_node(name, fn))
            return graph

    @staticmethod
    def _retry_node(
        name: str,
        fn: Callable[[IncidentState], IncidentState],
        attempts: int = 3,
        delay_seconds: float = 0.1,
    ) -> Callable[[IncidentState], IncidentState]:
        def wrapped(state: IncidentState) -> IncidentState:
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(state)
                except Exception as exc:  # noqa: BLE001 - convert node failures into workflow state
                    last_error = exc
                    state.decision_path.append(f"{name}: retry {attempt}/{attempts} failed: {exc}")
                    if attempt < attempts:
                        time.sleep(delay_seconds * attempt)
            state.status = "error"
            state.error = f"{name} failed after {attempts} attempts: {last_error}"
            return state

        return wrapped
