# AWS Production Readiness

The repository contains optional AWS reference components, but they are not
production-ready as-is.

## Implemented or Referenced

- Bedrock Runtime wrapper for MVP RCA generation.
- S3-backed knowledge document loading/uploading when `USE_AWS=true`.
- OpenSearch Serverless search/index path when configured.
- DynamoDB incident and audit storage when `USE_AWS=true`.
- Lambda packaging scripts.
- Terraform reference files.

## Required Before Production

- Review IAM permissions for least privilege.
- Configure Terraform remote state and locking.
- Move secrets into AWS Secrets Manager or another managed secret store.
- Add authentication and authorization in front of the API.
- Add request validation, rate limits, and WAF/API Gateway controls.
- Add CloudWatch dashboards, alarms, traces, and audit retention.
- Add rollback and incident response procedures.
- Review Bedrock model choice, data retention, and prompt logging policy.
- Replace mock remediation with reviewed executors.

## Current Safety Position

Keep `USE_AWS=false` for local development and public demos unless the AWS
environment has been reviewed.
