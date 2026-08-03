from __future__ import annotations

from core.config.settings import get_settings
from models import ApprovalRequest, ApprovalStatus, DecisionOutput, IncidentState
from services.audit_log import AuditService
from services.bedrock_rca import BedrockRCAClient
from services.mock_integrations import JiraMock, MockRemediationService, SlackApprovalMock
from services.aws_knowledge import KnowledgeService
from services.ops_store import IncidentStore
from utils.security import has_prompt_injection, scrub_sensitive_text

_RUNTIME_SERVICES: tuple[IncidentStore, AuditService, KnowledgeService, BedrockRCAClient] | None = None


def set_runtime_services(
    store: IncidentStore,
    audit: AuditService,
    knowledge: KnowledgeService,
    bedrock: BedrockRCAClient,
) -> None:
    global _RUNTIME_SERVICES
    _RUNTIME_SERVICES = (store, audit, knowledge, bedrock)


def services() -> tuple[IncidentStore, AuditService, KnowledgeService, BedrockRCAClient]:
    if _RUNTIME_SERVICES:
        return _RUNTIME_SERVICES
    settings = get_settings()
    audit = AuditService(settings)
    return IncidentStore(settings), audit, KnowledgeService(settings), BedrockRCAClient(settings, audit)


def incident_agent(state: IncidentState) -> IncidentState:
    store, audit, _, _ = services()
    if not state.event:
        state.status = "error"
        state.error = "Missing incident event"
        return state
    if has_prompt_injection(state.event.logs_summary):
        audit.record("prompt_injection_detected", state.incident_id)
        state.event.logs_summary = scrub_sensitive_text(state.event.logs_summary)
        state.decision_path.append("incident_agent: prompt injection pattern detected and scrubbed")
    if store.exists(state.incident_id):
        state.duplicate = True
        state.status = "duplicate"
        state.decision_path.append("incident_agent: duplicate incident_id")
    else:
        state.status = "context_collection"
        state.decision_path.append("incident_agent: schema valid, incident initialized")
    state.audit_trail.append(audit.record("incident_validated", state.incident_id, duplicate=state.duplicate))
    return state


def retrieval_agent(state: IncidentState) -> IncidentState:
    _, audit, knowledge, _ = services()
    if state.event and not state.duplicate:
        state.retrieved_documents = knowledge.search(state.event)
        state.decision_path.append(f"retrieval_agent: retrieved {len(state.retrieved_documents)} docs")
        state.audit_trail.append(
            audit.record("rag_retrieval_completed", state.incident_id, sources=[d.source_uri for d in state.retrieved_documents])
        )
    return state


def rca_agent(state: IncidentState) -> IncidentState:
    _, audit, _, bedrock = services()
    if state.event and not state.duplicate:
        state.rca = bedrock.generate_rca(state.event, state.retrieved_documents)
        state.rca_summary = state.rca.probable_root_cause
        state.decision_path.append("rca_agent: generated RCA with Bedrock wrapper")
        state.audit_trail.append(audit.record("rca_generated", state.incident_id, confidence=state.rca.confidence_score))
    return state


def decision_agent(state: IncidentState) -> IncidentState:
    settings = get_settings()
    _, audit, _, _ = services()
    if not state.event or not state.rca:
        state.decision = DecisionOutput(route="error", reason="Missing event or RCA", requires_human=True)
        state.status = "error"
        return state
    confidence = state.rca.confidence_score
    severity = state.event.severity.value
    if confidence < settings.confidence_review_threshold:
        decision = DecisionOutput(route="human_review", reason="Confidence below threshold", requires_human=True)
    elif severity in {"High", "Critical"}:
        decision = DecisionOutput(route="human_review", reason=f"{severity} severity requires human approval", requires_human=True)
    elif state.rca.risk_level == "low" and confidence >= settings.auto_mock_confidence_threshold:
        decision = DecisionOutput(
            route="auto_mock_remediation",
            reason="Low risk and high confidence; mock remediation allowed",
            requires_human=False,
            allowed_action=state.rca.recommended_action_type,
        )
    elif confidence >= settings.auto_mock_confidence_threshold:
        decision = DecisionOutput(
            route="auto_mock_remediation",
            reason="Confidence permits mock remediation only",
            requires_human=False,
            allowed_action=state.rca.recommended_action_type,
        )
    else:
        decision = DecisionOutput(route="human_review", reason="Manual review required by policy", requires_human=True)
    state.decision = decision
    state.status = decision.route
    state.decision_path.append(f"decision_agent: {decision.route} - {decision.reason}")
    state.audit_trail.append(audit.record("decision_recorded", state.incident_id, **decision.model_dump()))
    return state


def approval_agent(state: IncidentState) -> IncidentState:
    _, audit, _, _ = services()
    slack = SlackApprovalMock()
    if state.decision and state.decision.requires_human:
        state.approval = ApprovalRequest(incident_id=state.incident_id, payload=slack.create_payload(state))
        state.status = "awaiting_approval"
        state.decision_path.append("approval_agent: Slack approval mock created")
        state.audit_trail.append(audit.record("approval_requested", state.incident_id, payload=state.approval.payload))
    else:
        state.approval = ApprovalRequest(incident_id=state.incident_id, status=ApprovalStatus.NOT_REQUIRED)
        state.decision_path.append("approval_agent: approval not required")
    return state


def mock_remediation_agent(state: IncidentState) -> IncidentState:
    _, audit, _, _ = services()
    settings = get_settings()
    action = state.decision.allowed_action if state.decision else None
    if state.approval and state.approval.status == ApprovalStatus.REJECTED:
        state.remediation_result = MockRemediationService(settings).execute(state.incident_id, None)
        state.status = "rejected"
    else:
        state.remediation_result = MockRemediationService(settings).execute(state.incident_id, action)
        state.status = "remediated" if state.remediation_result.status == "success" else "remediation_skipped"
    state.decision_path.append(f"mock_remediation_agent: {state.remediation_result.status}")
    remediation_details = state.remediation_result.model_dump(exclude={"incident_id"})
    state.audit_trail.append(audit.record("mock_remediation_completed", state.incident_id, **remediation_details))
    return state


def communication_agent(state: IncidentState) -> IncidentState:
    _, audit, _, _ = services()
    state.jira_update = JiraMock().build_update(state)
    state.stakeholder_update = (
        f"Incident {state.incident_id}: {state.rca_summary}. "
        f"Status: {state.status}. Remediation: "
        f"{state.remediation_result.message if state.remediation_result else 'pending approval'}"
    )
    state.decision_path.append("communication_agent: Jira and stakeholder updates generated")
    state.audit_trail.append(audit.record("communications_generated", state.incident_id, jira=state.jira_update))
    return state


def learning_agent(state: IncidentState) -> IncidentState:
    store, audit, _, _ = services()
    state.decision_path.append("learning_agent: final record stored")
    state.audit_trail.append(audit.record("incident_history_stored", state.incident_id, status=state.status))
    store.save(state)
    return state
