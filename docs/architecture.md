# Architecture

The MVP follows the incident lifecycle shown in the provided reference diagram:

1. Sense: EventBridge-compatible CloudWatch alert enters `POST /incidents/trigger` or `lambda_handler`.
2. Analyze: retrieval reads S3/OpenSearch-style knowledge and returns top five grounded documents with citations.
3. Decide: Bedrock Claude Sonnet generates an RCA JSON object. LangGraph routes by severity, risk, and confidence.
4. Act: human approval is represented by a Slack payload mock. Approved incidents run dry-run remediation only.
5. Learn: incident, RCA, citations, approval, remediation, communications, and audit trail are stored.

## Agents

- `incident_agent`: validates schema, deduplicates by incident ID, creates state, scrubs unsafe text.
- `retrieval_agent`: retrieves top documents from OpenSearch or local knowledge files.
- `rca_agent`: calls the Bedrock wrapper and records model-call audit events.
- `decision_agent`: enforces confidence and severity policy.
- `approval_agent`: creates Slack-style approval payload.
- `mock_remediation_agent`: executes one of the allowed dry-run actions only.
- `communication_agent`: creates Jira-style ticket and stakeholder update.
- `learning_agent`: stores final incident history.

## Data Stores

- S3: source runbooks and RCA documents.
- OpenSearch: vector/search index for retrieval.
- DynamoDB incidents table: idempotency and incident history.
- DynamoDB audit table or local JSONL: CloudTrail-style audit trail.

No SageMaker, fine-tuning, LoRA, A2A, ECS/EKS production remediation, or multi-model routing is included.

