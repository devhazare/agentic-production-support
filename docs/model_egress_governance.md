# Model Egress Governance

This project treats LLM and embedding calls as a controlled data-egress boundary.
Raw incident data, logs, infrastructure metadata, project names, local file paths,
capacity values, secrets, and PII must not be sent to a model.

## Policy

All text sent to an LLM or embedding model must pass through the model egress
sanitization layer first.

The boundary applies to:

- LLM prompts.
- Bedrock RCA prompts.
- RAG document text before vector indexing.
- RAG retrieval queries before embedding.
- OpenSearch vector document content and query vectors.
- Prompt text recorded in observability.

The boundary must redact:

- PII such as emails and phone numbers.
- Secrets such as API keys, bearer tokens, passwords, JWTs, and connection
  strings.
- Infrastructure identifiers such as ARNs, AWS account IDs, instance IDs,
  resource IDs, S3 URIs, hostnames, IP addresses, Kubernetes resource names,
  environment-qualified resource names, and instance types.
- Project and runtime metadata such as local file paths and stack trace paths.
- Capacity details such as memory size, CPU/vCPU values, timeout values, and
  explicit capacity labels.

## Implementation

The central implementation is `services/model_egress.py`.

Use these functions only:

```python
from services.model_egress import sanitize_for_model, sanitize_for_embedding
```

Do not add one-off regex scrubbing inside individual agents. Agents, RAG, and
provider clients should delegate model-bound text to the central layer.

## Current Enforcement Points

- `services/llm/__init__.py`
  Sanitizes prompt text before calling the configured LLM provider. The sanitized
  prompt is also what observability records.

- `services/bedrock_rca.py`
  Sanitizes the complete Bedrock RCA prompt before invoking Bedrock Runtime.

- `rag/indexer/__init__.py`
  Sanitizes knowledge chunks before creating embeddings.

- `rag/retriever/__init__.py`
  Sanitizes retrieval queries before query embedding.

- `services/aws_knowledge.py`
  Sanitizes OpenSearch vector document content and incident search queries.

## Configuration

The settings are enabled by default:

```text
MODEL_EGRESS_SANITIZATION_ENABLED=true
MODEL_EGRESS_FAIL_CLOSED=true
MODEL_EGRESS_REDACTION_TOKEN=[MODEL_REDACTED]
```

`MODEL_EGRESS_FAIL_CLOSED=true` blocks the model call if high-risk secrets remain
after sanitization.

## Development Rules

- New LLM providers must be called through `LLMService` or must explicitly call
  `sanitize_for_model`.
- New embedding providers must call `sanitize_for_embedding` before encoding.
- New RAG ingestion paths must sanitize text before indexing.
- Tests must include examples for PII, secrets, infra identifiers, file paths,
  and capacity details.
- Documentation and GitHub issues must use sanitized examples only.

## Example

Input:

```text
arn:aws:lambda:us-east-1:123456789012:function:ai-ops-mvp-dev-api failed
at /Users/admin/project/services/bedrock_rca.py with memory_size=1024 MB.
Contact user@example.com. Authorization: Bearer abc.def.ghi
```

Sanitized model-bound text:

```text
[MODEL_REDACTED]:aws_arn failed at [MODEL_REDACTED]:file_path with
[MODEL_REDACTED]:capacity. Contact [MODEL_REDACTED].
[MODEL_REDACTED]:authorization_header
```
