# Incident Handling Scenarios

This document explains important failure scenarios, how the MVP handles them, the root-cause reasoning, and code snippets to discuss in interviews.

## Scenario 1: Bedrock Returns Unexpected JSON Shape

### Situation

Bedrock returns valid JSON, but one field has the wrong shape.

Example failure:

```text
recommended_action expected string, got list
```

### Risk

The RCA agent fails schema validation after the Bedrock call. The incident can move to `error`, the workflow retries, and the user may see a failed RCA even though the model response had useful content.

### How We Have Handled It

The parser normalizes Bedrock output before validating it with `RCAOutput`.

Fields that should be lists are coerced to lists:

- `supporting_evidence`
- `similar_incident_references`
- `citations`

Fields that should be strings are coerced to strings:

- `probable_root_cause`
- `recommended_action`

### How We Fixed It

Implemented in code.

The fix was to normalize scalar RCA fields before strict Pydantic validation. If Bedrock returns `recommended_action` or `probable_root_cause` as a list, the parser joins the list into one string. If Bedrock returns another non-string type, the parser converts it to a string.

This keeps the workflow resilient to safe LLM shape drift while still validating the final object with `RCAOutput`.

Regression coverage was added in:

```text
tests/unit/test_bedrock_rca_parser.py
```

### Code Snippet

From `services/bedrock_rca.py`:

```python
for key in ("probable_root_cause", "recommended_action"):
    value = payload.get(key, "")
    if isinstance(value, list):
        payload[key] = " ".join(
            json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
            for item in value
        )
    elif not isinstance(value, str):
        payload[key] = str(value)

return RCAOutput.model_validate(payload)
```

### 5 Whys

1. Why did the incident fail?
   Bedrock returned `recommended_action` as a list, but the schema expected a string.

2. Why did that break the workflow?
   Pydantic validation rejected the response before the decision agent could continue.

3. Why did Bedrock return a list?
   The model interpreted "recommended action" as a set of action steps instead of a scalar field.

4. Why was this not caught earlier?
   The parser normalized known list fields but did not normalize scalar fields.

5. Why is parser normalization needed?
   LLM output is probabilistic; production code must validate and repair safe shape mismatches before failing the workflow.

### Interview Line

“We treat LLM output as untrusted external input. Bedrock can return valid JSON with the wrong shape, so we normalize low-risk schema mismatches before strict validation.”

## Scenario 2: Duplicate Alarm

### Situation

CloudWatch sends the same alarm twice.

### Risk

Two Lambda executions start two RCA flows for the same operational event.

Impact:

- Bedrock cost doubles.
- RAG/OpenSearch calls duplicate.
- Slack/Jira approval messages can duplicate.
- Engineers may approve/remediate the same incident twice.

### MVP Handling

The MVP deduplicates by `incident_id` before retrieval and RCA.

Flow:

1. API or EventBridge Lambda receives an `IncidentEvent`.
2. `IncidentWorkflow.run()` starts at `incident_agent`.
3. `incident_agent` calls `store.exists(state.incident_id)`.
4. If the record exists, the state becomes `duplicate`.
5. The graph routes duplicate incidents to `learning_agent` and exits before expensive RCA.

### How We Fixed It

Partially implemented in the MVP.

The current fix is early duplicate detection inside `incident_agent`. This check runs before retrieval, Bedrock RCA, decision, approval, and remediation. If an incident with the same `incident_id` already exists, the workflow marks the state as `duplicate` and exits through `learning_agent`.

Implemented behavior:

```text
duplicate incident_id -> status=duplicate -> skip RAG/Bedrock/approval/remediation
```

Production hardening still needed:

```text
replace read-then-save dedupe with DynamoDB conditional put
```

The production fix is to create a `PROCESSING` record atomically before any Bedrock call. If the conditional write fails, the duplicate Lambda exits immediately.

### Code Snippet

From `agents/ops_nodes.py`:

```python
def incident_agent(state: IncidentState) -> IncidentState:
    store, audit, _, _ = services()
    if not state.event:
        state.status = "error"
        state.error = "Missing incident event"
        return state

    if store.exists(state.incident_id):
        state.duplicate = True
        state.status = "duplicate"
        state.decision_path.append("incident_agent: duplicate incident_id")
    else:
        state.status = "context_collection"
        state.decision_path.append("incident_agent: schema valid, incident initialized")

    state.audit_trail.append(
        audit.record("incident_validated", state.incident_id, duplicate=state.duplicate)
    )
    return state
```

From `orchestration/langgraph_workflow.py`:

```python
builder.add_conditional_edges(
    "incident_agent",
    lambda s: "stop" if s.status in {"duplicate", "error"} else "continue",
    {"stop": "learning_agent", "continue": "retrieval_agent"},
)
```

### Deterministic Incident ID

For CloudWatch/EventBridge alarms, the incident ID should be deterministic.

Example:

```python
incident_id = hash(
    account_id
    + region
    + alarm_name
    + resource_id
    + state
    + time_bucket
)
```

A practical format:

```python
import hashlib


def cloudwatch_incident_id(
    account_id: str,
    region: str,
    alarm_name: str,
    resource_id: str,
    state: str,
    time_bucket: str,
) -> str:
    raw = "|".join([account_id, region, alarm_name, resource_id, state, time_bucket])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()
    return f"INC-CW-{digest}"
```

### Production-Grade Dedupe

The strongest implementation is an atomic conditional insert before any AI call.

For DynamoDB:

```python
table.put_item(
    Item={
        "incident_id": incident_id,
        "status": "PROCESSING",
        "created_at": now,
    },
    ConditionExpression="attribute_not_exists(incident_id)",
)
```

If DynamoDB raises `ConditionalCheckFailedException`, another Lambda already owns the incident, so the function exits before Bedrock.

### Current MVP Limitation

The current MVP checks `exists()` before RCA, which avoids duplicate Bedrock calls when the first incident has already been saved.

However, `exists()` followed later by `save()` is not a fully atomic lock. If two Lambda invocations start at the exact same time and neither has saved yet, both could pass the `exists()` check.

For production, replace the read-then-save pattern with a conditional write such as:

```text
create PROCESSING record if incident_id does not exist
```

Then only the Lambda that successfully creates the record continues to RAG/Bedrock/RCA.

### Failure Mode

If dedupe happens after the Bedrock call:

- Cost doubles.
- RCA latency doubles.
- Slack/Jira can receive duplicate approval messages.
- Human operators lose trust in automation.

### 5 Whys

1. Why did two RCA flows run?
   CloudWatch delivered the same alarm twice.

2. Why did both Lambda executions process it?
   They were treated as separate events instead of the same incident.

3. Why were they not recognized as the same incident?
   The incident ID was not deterministic, or dedupe was not checked before RCA.

4. Why must dedupe happen before RCA?
   RCA calls Bedrock and external systems, which are expensive and create user-visible side effects.

5. Why is an atomic write needed?
   Concurrent Lambda executions can race; a read-then-write check is not enough under parallel delivery.

### Interview Line

“Deduplication must happen before expensive AI execution, not after RCA generation. In production I would use a deterministic incident ID plus a DynamoDB conditional write to create a PROCESSING record atomically.”

## Scenario 3: Bedrock Latency Increase

### Situation

Claude usually responds in 4 seconds.

Today it responds in 35 seconds.

### Impact

- Lambda duration increases.
- Lambda cost increases.
- Concurrent executions stay open longer.
- User sees slow Slack approval.
- API Gateway or client may timeout before the Lambda finishes.
- If the Lambda timeout is lower than Bedrock response time, the execution fails and may be retried.

### Observe

| AWS Service | What to Check |
|---|---|
| Lambda | Duration increases |
| CloudWatch | Lambda Duration graph |
| Bedrock | Invocation latency |
| API Gateway | Integration latency |
| DynamoDB | Write delayed |

### Root Cause

Likely causes:

- Large prompt
- Large RAG context
- Bedrock service load
- Model throttling

### MVP Handling

The MVP has three relevant controls today:

1. Lambda timeout is set in Terraform.
2. Workflow nodes are wrapped with retry logic.
3. Bedrock usage is measured and recorded through observability.

### How We Fixed It

Partially implemented in the MVP.

Current controls already in place:

- Lambda timeout is set to 60 seconds for API and incident-ingestion Lambdas.
- Workflow nodes have retry handling.
- Bedrock call duration is recorded through observability.
- If a node fails after retries, the state moves to `error` instead of silently succeeding.

Production fix still recommended:

- Configure explicit boto3 Bedrock client timeouts.
- Keep Bedrock read timeout below Lambda timeout.
- Limit retries to avoid multiplying latency.
- Route timeout cases to manual review with a fallback message:

```text
RCA generation delayed. Incident captured. Manual review required.
```

This prevents a slow model call from becoming an uncontrolled serverless concurrency and cost problem.

### Fix

Reduce:

- Prompt size
- Retrieved chunks
- Max tokens

Practical changes:

```python
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 600,
    "temperature": self.settings.bedrock_temperature,
    "system": "You are an SRE RCA assistant. Return only valid JSON.",
    "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
}
```

Limit RAG context before prompt construction:

```python
MAX_CONTEXT_DOCS = 3
MAX_DOC_CHARS = 1200

context = "\n\n".join(
    f"Source: {doc.source_uri}\nTitle: {doc.title}\n{scrub_sensitive_text(doc.text)[:MAX_DOC_CHARS]}"
    for doc in docs[:MAX_CONTEXT_DOCS]
)
```

From `infra/terraform/main.tf`:

```hcl
resource "aws_lambda_function" "api" {
  timeout     = 60
  memory_size = 1024
}

resource "aws_lambda_function" "incident_ingestion" {
  timeout     = 60
  memory_size = 1024
}
```

From `orchestration/langgraph_workflow.py`:

```python
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
            except Exception as exc:
                last_error = exc
                state.decision_path.append(
                    f"{name}: retry {attempt}/{attempts} failed: {exc}"
                )
                if attempt < attempts:
                    time.sleep(delay_seconds * attempt)
        state.status = "error"
        state.error = f"{name} failed after {attempts} attempts: {last_error}"
        return state

    return wrapped
```

From `services/bedrock_rca.py`:

```python
started = time.perf_counter()
response = self._client.invoke_model(
    modelId=self.settings.bedrock_model_id,
    body=json.dumps(body),
    accept="application/json",
    contentType="application/json",
)
duration_ms = int((time.perf_counter() - started) * 1000)
get_observability().record_llm_usage(
    provider="bedrock",
    model=self.settings.bedrock_model_id,
    prompt=prompt,
    response=response_text,
    duration_ms=duration_ms,
    status="success",
)
```

### Production Control

The production-grade control should include:

- Lambda timeout greater than expected Bedrock timeout.
- Explicit Bedrock client read/connect timeout.
- Small retry count for transient Bedrock failures.
- Fallback RCA state if Bedrock is slow or unavailable.
- Manual-review route instead of failing the incident.

Example:

```python
from botocore.config import Config

client = boto3.client(
    "bedrock-runtime",
    region_name=settings.aws_region,
    config=Config(
        connect_timeout=3,
        read_timeout=30,
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)
```

Fallback message:

```text
RCA generation delayed. Incident captured. Manual review required.
```

Fallback behavior:

```python
try:
    state.rca = bedrock.generate_rca(state.event, state.retrieved_documents)
except TimeoutError:
    state.status = "awaiting_approval"
    state.rca_summary = "RCA generation delayed. Incident captured. Manual review required."
    state.decision_path.append("rca_agent: Bedrock timeout, routed to manual review")
```

### Failure Mode

If the Lambda timeout is 30 seconds and Bedrock takes 45 seconds:

1. Lambda is killed before Bedrock returns.
2. The workflow does not persist the RCA result.
3. EventBridge/API retry may start another execution.
4. Multiple executions can increase cost and concurrency pressure.
5. The user receives no timely Slack approval or receives it much later.

### 5 Whys

1. Why did the incident response become slow?
   Bedrock response latency increased from 4 seconds to 35 seconds.

2. Why did Lambda cost increase?
   Lambda billing includes the time spent waiting for the Bedrock response.

3. Why did concurrency increase?
   Each Lambda execution stayed active while waiting for the model call to finish.

4. Why did Bedrock take longer?
   Prompt size, retrieved RAG context, max token budget, service load, or throttling increased the model response time.

5. Why is reducing prompt/context size a fix?
   Smaller prompts and fewer output tokens reduce model processing time and lower the chance that Lambda or API Gateway waits too long.

### Interview Line

“AI latency directly affects serverless concurrency because each Lambda stays active while waiting for the model response. I set explicit model timeouts, align Lambda timeout above that budget, limit retries, and route slow RCA to manual review with a fallback message.”

## Scenario 4: RAG Returns Wrong Context

### Situation

OpenSearch retrieves an old or irrelevant runbook.

Example:

```text
Incident: checkout latency after deployment
Retrieved context: old database runbook v1 from before the current architecture
```

### Impact

Bedrock may generate a confident but wrong RCA because it trusts the retrieved context.

Impact:

- RCA points to the wrong component.
- Recommended action can be stale.
- Human approver sees a polished answer and may approve it.
- Slack/Jira updates can spread incorrect operational guidance.
- Remediation may waste time or make the incident worse.

### MVP Handling

The MVP keeps retrieved documents on the incident state and passes source information into the Bedrock prompt.

Current stored evidence includes:

- `document_id`
- `title`
- `source_uri`
- `text`
- `score`
- `doc_type`

Current RCA output includes:

- `confidence_score`
- `citations`
- `supporting_evidence`
- `similar_incident_references`

### How We Fixed It

Partially implemented in the MVP.

Current implemented controls:

- Retrieved documents are stored on `IncidentState.retrieved_documents`.
- Each retrieved document includes `document_id`, `source_uri`, `text`, `score`, and `doc_type`.
- Bedrock prompt includes source URI and title.
- RCA output includes confidence and citations.
- Approval payload includes the RCA object, so the evidence can be surfaced to reviewers.

Production fix still recommended:

- Add source freshness fields such as `version`, `last_updated`, `valid_from`, and `valid_until`.
- Enforce a minimum retrieval score threshold before Bedrock.
- Route stale or low-score context to manual review.
- Show source score, snippet, and freshness in Slack approval.

Target behavior:

```text
low score or stale source -> do not trust RCA blindly -> require manual review
```

From `models/ops_schemas.py`:

```python
class KnowledgeDocument(BaseModel):
    document_id: str
    title: str
    source_uri: str
    text: str
    score: float = 0.0
    doc_type: Literal["runbook", "rca", "unknown"] = "unknown"


class RCAOutput(BaseModel):
    probable_root_cause: str
    supporting_evidence: list[str] = Field(default_factory=list)
    similar_incident_references: list[str] = Field(default_factory=list)
    recommended_action: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"]
    citations: list[str] = Field(default_factory=list)
```

From `services/aws_knowledge.py`:

```python
return [
    KnowledgeDocument.model_validate({**hit["_source"], "score": hit["_score"]})
    for hit in result["hits"]["hits"]
]
```

From `services/bedrock_rca.py`:

```python
context = "\n\n".join(
    f"Source: {doc.source_uri}\nTitle: {doc.title}\n{scrub_sensitive_text(doc.text)}"
    for doc in docs
)
```

### Control

RAG evidence should be exposed before approval.

Recommended evidence fields:

- Source document ID
- Source URI
- Runbook version
- Last updated timestamp
- Retrieval score
- Snippet used by the model
- RCA confidence
- Recent deployment metadata
- CloudWatch log group/source

Example Slack approval content:

```text
RCA confidence: 72%
Evidence:
- Runbook: magento-checkout-timeout-v3
- Source: s3://ai-ops-knowledge/runbook/magento-checkout-timeout-v3.md
- Retrieval score: 0.81
- CloudWatch log group: /aws/lambda/checkout-api
- Last deployment: checkout-api:2026-06-28T09:42:00Z
```

Use a minimum retrieval threshold:

```python
MIN_RAG_SCORE = 0.75

trusted_docs = [doc for doc in retrieved_docs if doc.score >= MIN_RAG_SCORE]
if not trusted_docs:
    state.status = "awaiting_approval"
    state.rca_summary = (
        "RAG evidence confidence is low. Incident captured. Manual review required."
    )
```

Use freshness checks:

```python
if runbook.last_updated < last_deployment_time:
    mark_context_as_stale()
    require_human_review()
```

### Current MVP Limitation

The MVP stores source URI, score, retrieved text, citations, and RCA confidence.

However, the current OpenSearch knowledge path does not yet enforce a minimum retrieval score threshold before calling Bedrock, and `KnowledgeDocument` does not yet include explicit `last_updated` or `version` fields.

For production, add:

- `version`
- `last_updated`
- `owner`
- `valid_from`
- `valid_until`
- `service_name`
- score threshold enforcement
- stale-context manual-review routing

### Failure Mode

If the wrong context is retrieved and hidden from the approver:

1. Bedrock may produce a confident but wrong RCA.
2. Decision logic may accept the confidence score.
3. Slack approval may show only the recommendation, not the evidence.
4. Human approver may approve the wrong remediation.
5. Incident resolution is delayed or worsened.

### 5 Whys

1. Why was the RCA wrong?
   Bedrock used an old or irrelevant runbook as context.

2. Why did Bedrock trust the wrong context?
   RAG supplied the context as grounding evidence, and the model followed it.

3. Why did RAG retrieve the old runbook?
   Vector similarity matched keywords, but did not account for freshness, version, or deployment context.

4. Why did the human approve the wrong recommendation?
   The approval message did not expose enough evidence, score, or source freshness to challenge the RCA.

5. Why must evidence be shown before approval?
   RAG improves grounding but does not guarantee correctness; humans need confidence, citations, freshness, and snippets to make a safe decision.

### Interview Line

“RAG does not guarantee correctness. I expose evidence, confidence, retrieval score, and source freshness before approval, and I route low-score or stale context to manual review instead of trusting the model blindly.”

## Scenario 5: Slack Approval Delayed

### Situation

Human approval is requested, but no one approves for 30 minutes.

### Impact

- Incident remains pending.
- Remediation does not run.
- Jira ticket/stakeholder update shows pending approval.
- Critical issue can wait too long if escalation is not configured.
- MTTR increases even if RCA is correct.

### MVP Behavior

The MVP intentionally does not auto-remediate high-risk or high-severity incidents.

Flow:

1. `decision_agent` classifies high severity or low confidence as `human_review`.
2. `approval_agent` creates a Slack-style approval payload.
3. State becomes `awaiting_approval`.
4. `communication_agent` creates Jira-style ticket data and stakeholder update.
5. `learning_agent` stores the incident state.
6. Remediation does not run until approval is received.

### How We Fixed It

Implemented as an MVP safety control.

The current fix is to block remediation while human approval is pending. High-severity incidents and low-confidence RCA results are routed to `human_review`. The approval agent creates a Slack-style approval payload, the communication agent creates Jira-style status, and the incident is stored as `awaiting_approval`.

Implemented behavior:

```text
human_review -> Slack approval payload -> Jira/stakeholder update -> no remediation until approval
```

Production hardening still needed:

- Add approval timeout policy.
- Escalate pending approvals to on-call after a threshold.
- Auto-remediate only low-risk allowlisted actions.
- Keep high-risk actions manual.

Target behavior:

```text
low risk + approval delayed -> auto remediate within guardrails
high risk + approval delayed -> escalate to on-call
```

From `agents/ops_nodes.py`:

```python
elif severity in {"High", "Critical"}:
    decision = DecisionOutput(
        route="human_review",
        reason=f"{severity} severity requires human approval",
        requires_human=True,
    )
```

From `agents/ops_nodes.py`:

```python
def approval_agent(state: IncidentState) -> IncidentState:
    _, audit, _, _ = services()
    slack = SlackApprovalMock()
    if state.decision and state.decision.requires_human:
        state.approval = ApprovalRequest(
            incident_id=state.incident_id,
            payload=slack.create_payload(state),
        )
        state.status = "awaiting_approval"
        state.decision_path.append("approval_agent: Slack approval mock created")
        state.audit_trail.append(
            audit.record("approval_requested", state.incident_id, payload=state.approval.payload)
        )
    return state
```

From `services/mock_integrations.py`:

```python
class SlackApprovalMock:
    def create_payload(self, state: IncidentState) -> dict[str, object]:
        return {
            "channel": "#incident-approvals",
            "incident_id": state.incident_id,
            "text": f"Approval requested for {state.event.service_name if state.event else state.incident_id}",
            "actions": ["approved", "rejected", "needs_more_info"],
            "decision": state.decision.model_dump() if state.decision else {},
            "rca": state.rca.model_dump() if state.rca else {},
        }
```

From `agents/ops_nodes.py`:

```python
state.jira_update = JiraMock().build_update(state)
state.stakeholder_update = (
    f"Incident {state.incident_id}: {state.rca_summary}. "
    f"Status: {state.status}. Remediation: "
    f"{state.remediation_result.message if state.remediation_result else 'pending approval'}"
)
```

### Control

The MVP prioritizes safety:

- High-severity incidents require human approval.
- Low-confidence RCA requires human approval.
- Remediation is dry-run/mock only.
- No production-changing action runs while approval is pending.
- Jira/stakeholder output records the pending approval state.

Expected state:

```text
status = awaiting_approval
approval.status = pending
remediation_result = None
stakeholder_update includes "pending approval"
```

### Failure Mode

If the incident is critical and approval is delayed:

1. RCA is complete but action is blocked.
2. No remediation happens.
3. The system remains degraded.
4. MTTR grows while waiting for a human.
5. The automation is safe, but too slow for time-sensitive incidents.

### Production Evolution

Production should separate low-risk and high-risk actions.

Low-risk actions can auto-remediate:

- restart a stateless worker
- scale read replicas
- clear a safe cache
- increase queue consumers within a guardrail

High-risk actions stay manual:

- rollback deployment
- modify database schema
- purge customer-impacting data
- change payment/checkout configuration

Production controls:

- approval timeout policy
- escalation after 10 or 15 minutes
- PagerDuty/on-call escalation
- auto-remediate only low-risk allowlisted actions
- require approval for high-risk actions
- audit every timeout and override

Example:

```python
if approval_age_minutes > 15 and action_risk == "low":
    run_auto_remediation()
elif approval_age_minutes > 15 and action_risk == "high":
    escalate_to_oncall()
```

### 5 Whys

1. Why did the incident stay unresolved?
   Human approval was requested but no one approved for 30 minutes.

2. Why did remediation not run automatically?
   The incident was high severity or required manual review, so the MVP blocked remediation.

3. Why does the MVP block remediation?
   The remediation system is not trusted enough yet to make production-changing decisions without approval.

4. Why did this become a problem?
   Safety controls prevented action, but there was no timeout-based escalation or low-risk auto-remediation path.

5. Why is production evolution needed?
   Mature incident automation must balance safety and speed by auto-remediating low-risk actions while keeping high-risk actions manual.

### Interview Line

“MVP prioritizes safety over speed. Human approval is intentional because remediation is not yet trusted. In production, I would auto-remediate low-risk allowlisted actions and escalate delayed high-risk approvals.”

## Scenario 7: Cost Explosion

### Situation

10,000 alarms invoke the incident workflow and each flow can call Bedrock.

### Risk

AI cost spikes quickly.

Impact:

- Bedrock invocation cost increases.
- Lambda duration/concurrency increases.
- OpenSearch/RAG query volume increases.
- Slack/Jira noise increases.
- On-call engineers lose signal in alert noise.

### MVP Behavior

The MVP has some cost controls, but not all production controls.

Current controls:

- API Gateway throttling is configured.
- Duplicate incident IDs are skipped before RAG/Bedrock.
- High/Critical incidents route to human review instead of automatic remediation.
- Low-risk actions are mock/dry-run only.
- The dedicated Magento generator Lambda does not call Bedrock.

From `infra/terraform/main.tf`:

```hcl
default_route_settings {
  throttling_burst_limit = 50
  throttling_rate_limit  = 25
}
```

From `agents/ops_nodes.py`:

```python
if store.exists(state.incident_id):
    state.duplicate = True
    state.status = "duplicate"
    state.decision_path.append("incident_agent: duplicate incident_id")
```

Current limitation:

```text
RCA generation currently happens before final severity-based decision routing.
```

That means severity filtering should be moved earlier in the production path if the goal is to avoid Bedrock cost.

### How We Fixed It

Partially implemented in the MVP.

Implemented controls:

- API Gateway throttling limits request rate into the HTTP API.
- Duplicate incidents skip expensive RCA once an incident record already exists.
- Magento log generation has its own Lambda and does not call Bedrock.
- The workflow stores decision path/audit data so cost-heavy paths can be reviewed.

Production hardening still needed:

- Lambda reserved concurrency on Bedrock-calling Lambdas.
- EventBridge filtering before Lambda invocation.
- Pre-RCA severity filtering.
- Group similar alarms into one incident.
- Call Bedrock only for Sev1/Sev2 or approved categories.
- Budget alarms and per-service usage dashboards.

Target behavior:

```text
low severity -> skip Bedrock -> monitor only
duplicates -> skip Bedrock -> return existing incident
similar alarms -> group -> one RCA
Sev1/Sev2 -> call Bedrock
```

### Production Controls

Use Lambda reserved concurrency:

```hcl
resource "aws_lambda_function" "incident_ingestion" {
  function_name                  = "${local.name_prefix}-incident-ingestion"
  reserved_concurrent_executions = 10
}
```

Use EventBridge filtering:

```json
{
  "source": ["aws.cloudwatch"],
  "detail-type": ["CloudWatch Alarm State Change"],
  "detail": {
    "state": {
      "value": ["ALARM"]
    },
    "severity": ["Sev1", "Sev2"]
  }
}
```

Skip low-severity alarms before Bedrock:

```python
if event.severity in {"Low", "Medium"}:
    state.status = "monitor_only"
    state.decision_path.append("pre_filter: skipped Bedrock for low severity")
    store.save(state)
    return state
```

Group similar alarms:

```python
group_key = hash(service_name + alarm_type + resource_group + time_bucket)
```

Only the first alarm in the group calls Bedrock. Later alarms attach to the existing incident.

### Failure Mode

If every alarm calls Bedrock:

1. Alert storm creates thousands of Lambda executions.
2. Every execution waits on Bedrock.
3. Bedrock cost and Lambda duration cost spike.
4. Slack/Jira get flooded.
5. Engineers spend time triaging duplicate AI-generated incidents instead of fixing the outage.

### 5 Whys

1. Why did cost spike?
   10,000 alarms each triggered an AI RCA call.

2. Why did every alarm call Bedrock?
   Filtering, grouping, and severity-based routing did not happen before RCA.

3. Why did concurrency increase?
   Each Lambda stayed active while waiting for Bedrock to respond.

4. Why did Slack/Jira noise increase?
   Each incident created its own downstream communication and approval path.

5. Why should filtering happen before AI?
   Bedrock is the expensive step; avoiding unnecessary model calls is the strongest cost control.

### Interview Line

“The cheapest AI call is the one we avoid through filtering, grouping, and severity-based routing. I put dedupe, severity checks, grouping, and concurrency limits before Bedrock.”

## Scenario Experiment Catalog

The following scenarios are useful for demos, interviews, load tests, and chaos testing. They are intentionally written as observable experiments.

## Scenario 12: Slow RAG

### Situation

OpenSearch becomes slow.

Usually:

```text
Search = 50 ms
```

Today:

```text
Search = 2.5 sec
```

### Observe

```text
CloudWatch -> Lambda Duration
```

Also compare:

- Bedrock invocation latency
- OpenSearch search latency
- Total Lambda duration

### Question

Which increased?

- Bedrock?
- RAG?

### Expected Learning

Do not assume the model is slow. Split timings by retrieval, Bedrock, persistence, and notification.

## Scenario 13: Large Prompt

### Situation

Upload 100 runbooks.

Instead of:

```text
Top K = 3
```

Use:

```text
Top K = 15
```

### Observe

- Prompt tokens
- Latency
- Cost

### Question

Is bigger context always better?

Answer:

```text
No.
```

### Expected Learning

More context can increase token cost, slow responses, and introduce irrelevant or conflicting evidence.

## Scenario 14: Lambda Cold Start

### Situation

Do not invoke Lambda for 20 minutes. Then run one incident.

### Observe

- Init Duration
- Total Duration
- First request latency vs second request latency

### Question

How much latency came from cold start?

### Expected Learning

Cold start latency is separate from Bedrock/RAG latency and should be measured independently.

## Scenario 15: Slack Delay

### Situation

Artificially add:

```python
sleep(10)
```

before Slack notification.

### Observe

- Lambda Duration
- Approval delay
- End-to-end incident latency

### Question

Should Slack block the entire Lambda?

### Expected Learning

Downstream notification calls should often be asynchronous or isolated so Slack latency does not block incident processing.

## Category 2: Concurrency

### Scenario 16: 100 Incidents

Generate 100 unique incident IDs and run them simultaneously.

Observe:

- CloudWatch Concurrent Executions
- Lambda Invocations
- Bedrock calls
- DynamoDB writes

Question:

```text
How many Lambdas ran together?
```

### Scenario 17: 500 Incidents

Generate 500 requests.

Observe:

- Throttles
- Errors
- ConcurrentExecutions
- API Gateway 429s
- Lambda throttles

Question:

```text
Did Lambda throttle?
```

### Scenario 18: Bedrock Concurrency

Suppose 500 Lambdas call Claude.

Observe:

- `429`
- `ThrottlingException`
- Bedrock latency
- Lambda duration

Question:

```text
Who became the bottleneck: Lambda or Bedrock?
```

### Scenario 19: Duplicate Alarm Storm

Send the same incident 100 times.

Observe:

- Bedrock calls
- DynamoDB writes
- Slack messages
- Duplicate incident states

Question:

```text
Without dedupe, how much money was wasted?
```

### Scenario 20: Mixed Severity

Generate 100 incidents:

```text
80 Low
15 Medium
5 Critical
```

Question:

```text
Should every incident call Claude?
```

Expected answer:

```text
No. Low and medium severity should be filtered, grouped, or handled with deterministic logic before Bedrock.
```

## Category 3: Throughput

### Scenario 21: Incidents Completed Per Minute

Measure for 1 minute.

How many incidents completed?

```text
20?
100?
500?
```

Observe:

```text
Lambda -> Invocations
```

Also observe:

- Duration
- Errors
- Throttles
- Bedrock invocation count

### Scenario 22: Prompt Size vs Throughput

Increase prompt size.

Observe:

```text
Throughput decrease
```

Expected learning:

```text
Larger prompts increase model latency, Lambda duration, and cost, reducing throughput.
```

## Category 4: Reliability

### Scenario 23: Bedrock Permission Removed

Kill Bedrock permission.

Observe:

```text
AccessDenied
```

Question:

```text
Is the incident lost?
```

Expected learning:

```text
The incident should still be captured and routed to manual review.
```

### Scenario 24: OpenSearch Unavailable

Make OpenSearch unavailable.

Question:

```text
Can AI continue?
```

Expected learning:

```text
The system should fall back to no-context or cached-context RCA, clearly mark evidence as unavailable, and require manual review.
```

### Scenario 25: DynamoDB Throttling

Create DynamoDB write pressure.

Observe:

```text
PutItem failed
```

Question:

```text
Was the incident persisted?
```

Expected learning:

```text
Persistence failure must be visible, retried safely, and never hidden behind a successful AI response.
```

## Category 5: Fault Tolerance

### Scenario 26: Lambda Timeout

Force Lambda timeout.

Observe:

```text
Task timed out
```

Question:

```text
Retry? Duplicate?
```

Expected learning:

```text
Timeouts need idempotency keys, deterministic incident IDs, and safe retry behavior.
```

### Scenario 27: Slack API Failure

Make Slack API fail.

Question:

```text
Incident complete? Approval pending?
```

Expected learning:

```text
Slack failure should not lose the incident. Approval should remain pending and an alternate escalation path should be used.
```

### Scenario 28: Jira API 500

Make Jira return HTTP 500.

Question:

```text
Rollback? Continue?
```

Expected learning:

```text
Jira update failure should not roll back RCA or incident persistence. It should be retried or queued.
```

## Category 6: Cost

### Scenario 29: 1000 Incidents

Generate 1000 incidents.

Observe:

- Bedrock tokens
- Claude cost
- Lambda cost
- OpenSearch cost
- DynamoDB cost

Question:

```text
Which service costs most?
```

Expected learning:

```text
Bedrock token volume and Lambda wait time usually dominate variable cost during AI-heavy incident storms.
```

### Scenario 30: Increase Top K

Increase:

```text
Top K: 3 -> 10
```

Observe:

- Token count
- Latency
- Cost

Expected learning:

```text
More retrieved context is not free. Top K must be tuned for quality, latency, and cost.
```

## Category 7: Human Approval

### Scenario 31: Never Approve

Never approve the incident.

Observe:

```text
Pending
```

Question:

```text
Need reminder?
```

Expected learning:

```text
Approval workflows need reminders, escalation, and timeout policies.
```

### Scenario 32: Reject RCA

Reject the RCA.

Question:

```text
What next? Regenerate? Escalate?
```

Expected learning:

```text
Rejected RCA should trigger feedback capture, possible RCA regeneration, and escalation to human investigation.
```

## Category 8: AI Quality

### Scenario 33: Wrong Runbook

Upload a wrong runbook.

Observe:

```text
Wrong RCA
```

Expected learning:

```text
RAG needs source quality controls, freshness, ownership, and review before trusting recommendations.
```

### Scenario 34: No Runbook

Upload no runbook or remove all relevant context.

Observe:

```text
Hallucination
```

Expected learning:

```text
No evidence should lower confidence and route to manual review.
```

### Scenario 35: Conflicting Runbooks

Upload conflicting runbooks.

Observe:

```text
Different RCA
```

Expected learning:

```text
Conflicting evidence should be shown explicitly, and the model should not hide disagreement.
```

## Category 9: Chaos Engineering

| Experiment | Expected Learning |
|---|---|
| Stop Bedrock access | AI dependency failure |
| Increase prompt 10x | Token cost and latency |
| 100 duplicate incidents | Need for idempotency |
| 1000 concurrent requests | Lambda scaling limits |
| Remove OpenSearch | RAG fallback behavior |
| Slow Slack | Downstream latency impact |
| DynamoDB write failure | Persistence resilience |
| Invalid prompt template | Prompt validation |
| Wrong Claude model | Model compatibility |
| CloudWatch alarm storm | Event burst handling |

## Detailed Scenario Controls: 12-35

The earlier catalog is a quick test list. This section expands each scenario using the interview-ready structure.

## Scenario 12: Slow RAG

### Situation

OpenSearch search normally takes 50 ms, but today it takes 2.5 seconds.

### Impact

Lambda duration increases even if Bedrock is healthy. API latency increases, incident processing slows, and the team may incorrectly blame Claude instead of retrieval.

### MVP Behavior

The MVP separates retrieval from RCA in the LangGraph flow. `retrieval_agent` runs before `rca_agent`, and the decision path records that retrieval completed.

### How We Fixed It

Partially implemented. The workflow separation makes it clear whether delay is in retrieval or Bedrock. Production should add explicit timing metrics around `KnowledgeService.search()`.

### Control

Measure RAG latency separately from Bedrock latency. Add timeout and fallback: if OpenSearch is slow, continue with no-context RCA or route to manual review.

### Code Snippet

```python
started = time.perf_counter()
state.retrieved_documents = knowledge.search(state.event)
rag_duration_ms = int((time.perf_counter() - started) * 1000)
state.decision_path.append(f"retrieval_agent: rag_duration_ms={rag_duration_ms}")
```

### 5 Whys

1. Why did incident processing slow down? RAG search took 2.5 seconds.
2. Why was this confusing? Total Lambda duration increased, which can look like Bedrock latency.
3. Why did RAG slow down? OpenSearch load, query shape, index health, or network latency changed.
4. Why do we need separate metrics? Without split timing, we cannot isolate the bottleneck.
5. Why is fallback needed? Incident capture should continue even when retrieval is degraded.

### Interview Line

“I separate RAG latency from Bedrock latency. If retrieval is slow, I degrade gracefully instead of blocking the whole incident.”

## Scenario 13: Large Prompt

### Situation

100 runbooks are uploaded. Instead of `top_k=3`, the system uses `top_k=15`.

### Impact

Prompt tokens increase, Bedrock latency increases, cost increases, and irrelevant context can reduce RCA quality.

### MVP Behavior

The MVP supports `rag_top_k` in settings and passes retrieved documents into the Bedrock prompt.

### How We Fixed It

Partially implemented. `rag_top_k` is configurable. Production should enforce a maximum context budget by document count and character/token size.

### Control

Keep Top K small, truncate snippets, enforce token budgets, and prefer high-score fresh documents over large context.

### Code Snippet

```python
MAX_CONTEXT_DOCS = 3
MAX_DOC_CHARS = 1200

context = "\n\n".join(
    f"Source: {doc.source_uri}\nTitle: {doc.title}\n{doc.text[:MAX_DOC_CHARS]}"
    for doc in docs[:MAX_CONTEXT_DOCS]
)
```

### 5 Whys

1. Why did cost increase? More retrieved chunks increased prompt tokens.
2. Why did latency increase? Larger prompts take longer to process.
3. Why did RCA quality drop? Irrelevant context diluted the useful evidence.
4. Why is Top K not always better? More context can add noise and contradictions.
5. Why enforce a token budget? It controls latency, cost, and RCA focus.

### Interview Line

“Bigger context is not always better. I cap Top K and token budget so RAG improves grounding without exploding cost.”

## Scenario 14: Lambda Cold Start

### Situation

Lambda is not invoked for 20 minutes. The next incident takes longer.

### Impact

First request latency increases due to runtime initialization, package import, boto3 client setup, and framework startup.

### MVP Behavior

The MVP uses Python Lambda packages and imports FastAPI/Mangum for the API Lambda. Cold start can appear as extra latency before the workflow runs.

### How We Fixed It

Partially implemented. Lambda timeout allows cold start overhead. Production should track `Init Duration` and consider provisioned concurrency only if required.

### Control

Monitor `Init Duration`, compare first vs warm invocation, and keep package size small.

### Code Snippet

```text
CloudWatch Logs REPORT line:
Init Duration: 850.00 ms
Duration: 5200.00 ms
```

### 5 Whys

1. Why was the first incident slow? Lambda cold start added initialization time.
2. Why did cold start happen? The function was idle long enough for the environment to recycle.
3. Why is this separate from Bedrock latency? Cold start happens before the model call.
4. Why measure `Init Duration`? It isolates platform startup from application work.
5. Why optimize package size? Smaller packages generally reduce import/startup overhead.

### Interview Line

“I separate cold start from application latency by checking Lambda Init Duration.”

## Scenario 15: Slack Delay

### Situation

Slack notification is artificially delayed by `sleep(10)`.

### Impact

Lambda duration increases and approval is delayed. If Slack blocks the workflow, incident completion waits on a downstream notification dependency.

### MVP Behavior

The MVP uses `SlackApprovalMock`, so no real Slack network call blocks today.

### How We Fixed It

Implemented for MVP by mocking Slack. Production should make Slack notification asynchronous or retryable outside the critical path.

### Control

Do not let Slack block incident persistence. Persist the incident first, then send approval notification asynchronously.

### Code Snippet

```python
store.save(state)
enqueue_slack_approval(state.incident_id)
return state
```

### 5 Whys

1. Why did Lambda duration increase? Slack call was slow.
2. Why did approval delay? Notification was part of the synchronous path.
3. Why is this risky? Slack outage can block incident workflow.
4. Why persist first? The incident must not be lost if Slack fails.
5. Why async notification? It isolates downstream latency from core incident processing.

### Interview Line

“Slack should not block the entire Lambda. I persist the incident first and send approval asynchronously.”

## Scenario 16: 100 Incidents

### Situation

100 unique incident IDs are submitted simultaneously.

### Impact

Lambda concurrent executions increase. Bedrock, OpenSearch, and DynamoDB receive parallel load.

### MVP Behavior

API Gateway throttling is configured. Lambda can scale unless account/function concurrency limits are reached.

### How We Fixed It

Partially implemented through API Gateway throttling. Production should add reserved concurrency on Bedrock-calling Lambdas.

### Control

Measure concurrent executions and throttle before dependencies overload.

### Code Snippet

```hcl
default_route_settings {
  throttling_burst_limit = 50
  throttling_rate_limit  = 25
}
```

### 5 Whys

1. Why did concurrency rise? 100 requests arrived together.
2. Why does this matter? Each Lambda can call Bedrock and OpenSearch.
3. Why can dependencies fail? They may have lower concurrency limits than Lambda.
4. Why throttle? It protects downstream systems.
5. Why reserve concurrency? It caps blast radius per function.

### Interview Line

“Lambda scales fast, so I cap concurrency before downstream AI and data services become bottlenecks.”

## Scenario 17: 500 Incidents

### Situation

500 incidents are sent at once.

### Impact

Throttles, errors, increased duration, and dependency saturation can occur.

### MVP Behavior

API Gateway has rate/burst throttling. Lambda does not currently define reserved concurrency in Terraform.

### How We Fixed It

Partially implemented at API Gateway. Production should add reserved concurrency and queue-based buffering.

### Control

Watch Lambda `Throttles`, `Errors`, `ConcurrentExecutions`, and API Gateway 429 responses.

### Code Snippet

```hcl
resource "aws_lambda_function" "incident_ingestion" {
  reserved_concurrent_executions = 25
}
```

### 5 Whys

1. Why did errors appear? 500 requests exceeded safe throughput.
2. Why did throttles happen? Service concurrency or API limits were reached.
3. Why is this expected? Serverless scales, but not infinitely.
4. Why add buffering? Queues smooth bursts.
5. Why monitor throttles? They show the first hard scaling limit.

### Interview Line

“For bursty incidents, I use throttling and queues to trade immediate concurrency for controlled throughput.”

## Scenario 18: Bedrock Concurrency

### Situation

500 Lambdas call Claude at the same time.

### Impact

Bedrock can return `429` or `ThrottlingException`. Lambda duration increases while executions wait or retry.

### MVP Behavior

Bedrock is called synchronously inside `rca_agent`.

### How We Fixed It

Partially implemented with workflow retry. Production needs Bedrock-specific retry limits, backoff, and concurrency caps.

### Control

Limit concurrent Bedrock calls and route throttled incidents to manual review or retry queue.

### Code Snippet

```python
config=Config(
    connect_timeout=3,
    read_timeout=30,
    retries={"max_attempts": 2, "mode": "standard"},
)
```

### 5 Whys

1. Why did Bedrock throttle? Too many concurrent model requests.
2. Why did Lambda duration rise? Functions waited on model response/retry.
3. Why did cost rise? Waiting time is billed.
4. Why cap Bedrock concurrency? Bedrock is the scarce dependency.
5. Why fallback? Critical incidents must still be captured.

### Interview Line

“When many Lambdas call Claude, Bedrock can become the bottleneck. I cap AI concurrency and fail over to manual review.”

## Scenario 19: Duplicate Alarm Storm

### Situation

The same incident is sent 100 times.

### Impact

Without dedupe, Bedrock calls, DynamoDB writes, and Slack messages duplicate.

### MVP Behavior

`incident_agent` checks `store.exists(incident_id)` before RAG and Bedrock.

### How We Fixed It

Partially implemented with pre-RCA duplicate check. Production should use DynamoDB conditional writes for atomic dedupe.

### Control

Use deterministic incident IDs and conditional insert before AI execution.

### Code Snippet

```python
table.put_item(
    Item={"incident_id": incident_id, "status": "PROCESSING"},
    ConditionExpression="attribute_not_exists(incident_id)",
)
```

### 5 Whys

1. Why was money wasted? Duplicate alarms called Bedrock repeatedly.
2. Why did duplicates run? No atomic idempotency gate.
3. Why before Bedrock? Bedrock is the expensive step.
4. Why deterministic ID? Same alarm must map to same incident.
5. Why conditional write? It prevents concurrent races.

### Interview Line

“Duplicate storm protection must happen before Bedrock, using deterministic IDs and atomic writes.”

## Scenario 20: Mixed Severity

### Situation

100 incidents arrive: 80 Low, 15 Medium, 5 Critical.

### Impact

Calling Claude for every incident wastes cost and increases latency.

### MVP Behavior

Decision routing uses severity, but current RCA happens before final decision.

### How We Fixed It

Partially implemented with severity-aware decision. Production should add pre-RCA severity filtering.

### Control

Only call Bedrock for Sev1/Sev2 or incidents that pass escalation rules.

### Code Snippet

```python
if event.severity in {"Low", "Medium"}:
    state.status = "monitor_only"
    store.save(state)
    return state
```

### 5 Whys

1. Why did cost increase? Low incidents called Claude.
2. Why unnecessary? Low severity often needs monitoring, not RCA.
3. Why pre-filter? Filtering after RCA is too late.
4. Why keep Critical? High impact needs deeper analysis.
5. Why severity routing? It aligns cost with risk.

### Interview Line

“Not every incident deserves AI. I reserve Bedrock for high-impact or ambiguous cases.”

## Scenario 21: Throughput Per Minute

### Situation

Measure how many incidents complete in one minute.

### Impact

Throughput reveals system capacity and bottlenecks.

### MVP Behavior

Lambda invocations, duration, and errors are visible in CloudWatch.

### How We Fixed It

Partially implemented through CloudWatch metrics. Production should add custom metrics per workflow stage.

### Control

Track completed incidents per minute, Bedrock calls per minute, and failure rate.

### Code Snippet

```python
get_observability().record_pipeline_result(result)
```

### 5 Whys

1. Why measure throughput? It shows real capacity.
2. Why can throughput drop? Latency, throttling, or errors increase.
3. Why stage metrics? They locate the bottleneck.
4. Why per minute? Incidents arrive in bursts.
5. Why compare with cost? More throughput can increase spend.

### Interview Line

“I measure incident throughput by stage, not just total Lambda invocations.”

## Scenario 22: Prompt Size Reduces Throughput

### Situation

Prompt size increases.

### Impact

Bedrock latency increases, Lambda duration increases, and fewer incidents complete per minute.

### MVP Behavior

Prompt contains incident JSON plus retrieved context.

### How We Fixed It

Partially implemented through configurable RAG Top K and max tokens. Production should enforce prompt budgets.

### Control

Cap context size and max output tokens.

### Code Snippet

```python
"max_tokens": self.settings.bedrock_max_tokens
```

### 5 Whys

1. Why did throughput drop? Each incident took longer.
2. Why longer? Prompt size increased model processing time.
3. Why does Lambda care? Lambda waits synchronously.
4. Why cap prompt? It controls latency and cost.
5. Why monitor tokens? Tokens are the unit of model cost and latency.

### Interview Line

“Prompt size is a throughput control, not just a model-quality choice.”

## Scenario 23: Bedrock Permission Removed

### Situation

Bedrock permission is removed.

### Impact

RCA generation fails with `AccessDenied`.

### MVP Behavior

Workflow retry catches node failures and marks final state as `error` after retries.

### How We Fixed It

Partially implemented with retry and error state. Production should preserve incident and route to manual review.

### Control

Never lose the incident when AI dependency fails.

### Code Snippet

```python
state.status = "error"
state.error = f"{name} failed after {attempts} attempts: {last_error}"
```

### 5 Whys

1. Why did RCA fail? Bedrock access was denied.
2. Why was permission missing? IAM policy changed.
3. Why retry? Access errors may be deployment drift but often need visibility.
4. Why not lose incident? Alert capture is more important than AI output.
5. Why route to manual? Humans can continue without RCA.

### Interview Line

“AI failure should degrade the RCA, not drop the incident.”

## Scenario 24: OpenSearch Unavailable

### Situation

OpenSearch is unavailable.

### Impact

RAG context is missing, and Bedrock may produce lower-quality RCA.

### MVP Behavior

`KnowledgeService.search()` currently performs OpenSearch search when configured.

### How We Fixed It

Partially implemented with local search fallback in non-AWS mode. Production should catch OpenSearch failures and continue with no-context/manual review.

### Control

Mark evidence unavailable and reduce confidence.

### Code Snippet

```python
try:
    docs = knowledge.search(event)
except Exception:
    docs = []
    state.decision_path.append("retrieval_agent: OpenSearch unavailable")
```

### 5 Whys

1. Why did context disappear? OpenSearch was unavailable.
2. Why did RCA quality drop? Bedrock lacked grounding.
3. Why is fallback needed? Incident handling must continue.
4. Why reduce confidence? No evidence means less trust.
5. Why manual review? Human validation is needed without RAG.

### Interview Line

“When RAG is unavailable, I continue incident capture but lower confidence and require review.”

## Scenario 25: DynamoDB Throttling

### Situation

DynamoDB `PutItem` fails due to throttling.

### Impact

Incident state may not persist.

### MVP Behavior

`IncidentStore.save()` writes final state to DynamoDB in AWS mode.

### How We Fixed It

Partially implemented through DynamoDB on-demand billing. Production should add retry/backoff and dead-letter handling.

### Control

Persistence failure must be visible and retried safely.

### Code Snippet

```python
self._table.put_item(Item=json.loads(state.model_dump_json(), parse_float=Decimal))
```

### 5 Whys

1. Why was incident not saved? DynamoDB write failed.
2. Why did write fail? Throttling or transient service issue.
3. Why is this serious? RCA without persistence is lost work.
4. Why retry? Writes are often recoverable.
5. Why DLQ? Non-recoverable writes need operator visibility.

### Interview Line

“Persistence is the source of truth; AI success means nothing if the incident state is not saved.”

## Scenario 26: Lambda Timeout

### Situation

Lambda times out.

### Impact

Execution stops mid-flow and retry can create duplicates.

### MVP Behavior

Lambda timeout is set to 60 seconds for API and incident-ingestion functions.

### How We Fixed It

Partially implemented with explicit Lambda timeout and duplicate checks. Production needs idempotent stage persistence.

### Control

Use deterministic incident IDs, save progress by stage, and make retries idempotent.

### Code Snippet

```hcl
timeout = 60
```

### 5 Whys

1. Why did task stop? Lambda exceeded timeout.
2. Why did it exceed timeout? Bedrock/RAG/downstream call was slow.
3. Why duplicate risk? Retry may rerun same incident.
4. Why idempotency? Retry must not repeat side effects.
5. Why stage persistence? Resume safely after partial progress.

### Interview Line

“Timeout handling requires idempotency, because retrying a half-completed workflow can duplicate work.”

## Scenario 27: Slack API Failure

### Situation

Slack API fails.

### Impact

Approval request may not reach humans.

### MVP Behavior

Slack is mocked, so real API failure is not present in the MVP.

### How We Fixed It

Implemented in MVP by isolating Slack as a mock payload. Production should queue notification and keep approval pending.

### Control

Incident remains persisted; approval stays pending; alternate escalation is used.

### Code Snippet

```python
state.approval = ApprovalRequest(incident_id=state.incident_id, payload=slack.create_payload(state))
state.status = "awaiting_approval"
```

### 5 Whys

1. Why was approval delayed? Slack failed.
2. Why did workflow continue? Incident was already captured.
3. Why pending? Human has not approved.
4. Why alternate channel? Approval path must be reliable.
5. Why not auto-remediate? Safety requires approval for high risk.

### Interview Line

“Slack failure should not lose the incident; it should leave approval pending and escalate through another channel.”

## Scenario 28: Jira API 500

### Situation

Jira returns HTTP 500.

### Impact

Ticket update fails, but RCA and incident state may still be valid.

### MVP Behavior

Jira is mocked as `JiraMock`, so no real Jira API failure exists in MVP.

### How We Fixed It

Implemented in MVP through a mock. Production should treat Jira as non-critical communication and retry asynchronously.

### Control

Do not roll back RCA because Jira failed.

### Code Snippet

```python
state.jira_update = JiraMock().build_update(state)
```

### 5 Whys

1. Why did ticket update fail? Jira returned 500.
2. Why should incident continue? Jira is downstream communication.
3. Why retry? Ticket sync can succeed later.
4. Why not rollback? RCA/persistence are independent.
5. Why audit failure? Operators need visibility.

### Interview Line

“Jira failure should not roll back incident handling; it should be retried and audited.”

## Scenario 29: 1000 Incidents Cost Test

### Situation

1000 incidents are generated.

### Impact

Bedrock tokens, Lambda duration, OpenSearch queries, and DynamoDB writes increase.

### MVP Behavior

Bedrock usage is recorded through observability. AWS Budget is configured when `budget_alert_email` is set.

### How We Fixed It

Partially implemented with usage recording and budget support. Production should add per-incident cost attribution.

### Control

Measure cost by service and avoid unnecessary Bedrock calls.

### Code Snippet

```python
get_observability().record_llm_usage(
    provider="bedrock",
    model=self.settings.bedrock_model_id,
    duration_ms=duration_ms,
    status="success",
)
```

### 5 Whys

1. Why did cost spike? 1000 workflows invoked AI and Lambda.
2. Why is Bedrock expensive? Token-based model calls dominate variable cost.
3. Why Lambda cost rises? It waits during AI calls.
4. Why attribute cost? Teams need to know which route/service caused spend.
5. Why filter? Avoided calls cost zero.

### Interview Line

“I measure AI cost per incident and reduce spend by avoiding low-value model calls.”

## Scenario 30: Top K 3 to 10

### Situation

RAG Top K increases from 3 to 10.

### Impact

Token count, latency, and cost increase.

### MVP Behavior

`rag_top_k` controls retrieval count.

### How We Fixed It

Partially implemented through configurable Top K. Production should enforce max token budget and score threshold.

### Control

Tune Top K based on accuracy, cost, and latency.

### Code Snippet

```python
top_k = top_k or self.settings.rag_top_k
```

### 5 Whys

1. Why did tokens increase? More documents entered the prompt.
2. Why did latency increase? Larger prompt took longer.
3. Why did cost increase? More input tokens were billed.
4. Why can accuracy drop? More documents can add noise.
5. Why tune Top K? It balances quality and cost.

### Interview Line

“Top K is a cost and quality lever, not just a retrieval setting.”

## Scenario 31: Never Approve

### Situation

Human never approves.

### Impact

Incident remains pending and remediation never runs.

### MVP Behavior

State remains `awaiting_approval`.

### How We Fixed It

Implemented as MVP safety behavior. Production needs reminders and escalation.

### Control

Approval timeout, reminder, escalation, and audit trail.

### Code Snippet

```python
state.status = "awaiting_approval"
```

### 5 Whys

1. Why pending? No approval response.
2. Why no remediation? Human approval is required.
3. Why safety first? Remediation is not fully trusted.
4. Why escalation? Critical incidents cannot wait forever.
5. Why reminders? Humans miss notifications.

### Interview Line

“Pending approval is safe but incomplete; production needs reminders and escalation.”

## Scenario 32: Reject RCA

### Situation

Human rejects the RCA.

### Impact

Remediation does not run and investigation must continue.

### MVP Behavior

Reject endpoint sets approval status to rejected and skips remediation.

### How We Fixed It

Implemented in MVP through reject flow.

### Control

Capture rejection reason, escalate, and optionally regenerate RCA with feedback.

### Code Snippet

```python
state.approval.status = ApprovalStatus.REJECTED
state.status = "rejected"
```

### 5 Whys

1. Why was RCA rejected? Human found it unsafe or wrong.
2. Why stop remediation? Recommendation is not trusted.
3. Why capture reason? Feedback improves next RCA.
4. Why escalate? Incident still exists.
5. Why regenerate? New evidence may produce better RCA.

### Interview Line

“Rejecting RCA should stop remediation and turn human feedback into the next investigation step.”

## Scenario 33: Wrong Runbook

### Situation

A wrong runbook is uploaded.

### Impact

RAG retrieves bad context and Bedrock may produce wrong RCA.

### MVP Behavior

RCA stores citations and retrieved documents, so bad evidence can be inspected.

### How We Fixed It

Partially implemented through citations/evidence. Production needs source review and freshness controls.

### Control

Require document ownership, versioning, review, and confidence display.

### Code Snippet

```python
citations = [doc.source_uri for doc in docs[:5]]
```

### 5 Whys

1. Why was RCA wrong? Wrong runbook was used.
2. Why was it retrieved? Vector search matched text.
3. Why did model trust it? RAG context is treated as evidence.
4. Why show citations? Humans can verify source quality.
5. Why document governance? Bad knowledge creates bad RCA.

### Interview Line

“RAG quality is only as good as the knowledge base, so I expose citations and govern source documents.”

## Scenario 34: No Runbook

### Situation

No relevant runbook exists.

### Impact

Bedrock may hallucinate or return low-confidence generic RCA.

### MVP Behavior

Mock RCA lowers confidence when no documents exist. Bedrock prompt requires citations from retrieved context.

### How We Fixed It

Partially implemented through confidence and citations. Production should require manual review when evidence is missing.

### Control

If no evidence, lower confidence and block auto-remediation.

### Code Snippet

```python
confidence_score=confidence if docs else 0.55
```

### 5 Whys

1. Why hallucination risk? No grounding context.
2. Why low confidence? Evidence is missing.
3. Why block remediation? Recommendation is unsupported.
4. Why manual review? Humans need to investigate.
5. Why add runbooks? Knowledge gaps reduce automation quality.

### Interview Line

“No runbook means no strong evidence; I lower confidence and require human review.”

## Scenario 35: Conflicting Runbooks

### Situation

Two runbooks conflict.

### Impact

Bedrock may choose one silently and produce inconsistent RCA.

### MVP Behavior

Retrieved documents and citations are stored, so conflicts can be inspected after the fact.

### How We Fixed It

Partially implemented through stored evidence and citations. Production should detect conflicting sources and route to manual review.

### Control

Expose conflicting evidence in approval and avoid hiding disagreement.

### Code Snippet

```python
similar_incident_references=[doc.title for doc in docs if doc.doc_type == "rca"][:3]
```

### 5 Whys

1. Why did RCA vary? Runbooks conflicted.
2. Why did model choose one? Prompt did not force conflict reporting.
3. Why is that risky? Human sees a single confident answer.
4. Why expose conflicts? Approval needs full evidence.
5. Why manual review? Conflicting guidance needs human judgment.

### Interview Line

“When evidence conflicts, the system should show disagreement instead of pretending the RCA is certain.”
