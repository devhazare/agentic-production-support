# Cost Estimate

The MVP is designed for pay-as-used operation.

Likely monthly costs in low-volume demo usage:

- Lambda: near free tier for ingestion and mock remediation.
- DynamoDB on-demand: small cents to a few dollars for incident and audit records.
- S3: cents for runbooks and RCA documents.
- CloudWatch Logs: cents to low dollars depending on log volume and retention.
- Bedrock Claude Sonnet: variable by input/output tokens; keep retrieved context small and top-k at 5.
- OpenSearch Serverless: can be the largest fixed-ish cost. For the cheapest demo, use local retrieval or provision only for short evaluation windows.

Cost controls:

- Keep `rag_top_k=5`.
- Scrub and truncate logs before model calls.
- Use DynamoDB PAY_PER_REQUEST.
- Use Lambda instead of always-on ECS/EKS.
- Avoid SageMaker endpoints, fine-tuning jobs, and production remediation infrastructure in MVP.

