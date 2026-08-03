# AWS Production Movement Checklist

This project is now structured for an AWS MVP deployment path. It is not a full enterprise production platform, but the infrastructure is no longer just a placeholder.

## Ready

- API Gateway HTTP API fronts a Lambda-hosted FastAPI MVP app.
- EventBridge can invoke incident-ingestion Lambda for CloudWatch-style events.
- DynamoDB on-demand tables store incidents and audit logs with PITR enabled.
- S3 knowledge bucket has public access blocked, versioning, and SSE.
- OpenSearch Serverless vector collection has encryption, network, and data access policies.
- Bedrock Claude Sonnet is invoked through `bedrock-runtime`.
- Mock remediation is isolated to a Lambda dry-run handler.
- Lambda package script builds a smaller AWS artifact from `requirements-lambda.txt`.

## Deployment Commands

```bash
./scripts/package_lambda.sh
cd infra/terraform
terraform init
terraform plan
terraform apply
```

## Required AWS Account Setup

- Enable Bedrock access for `anthropic.claude-3-5-sonnet-20240620-v1:0` or override `bedrock_model_id`.
- Ensure the Terraform caller can create IAM roles, Lambda, API Gateway, DynamoDB, S3, EventBridge, CloudWatch Logs, and OpenSearch Serverless resources.
- For private OpenSearch, create VPC endpoints and pass their IDs through `opensearch_allowed_vpc_endpoint_ids`.

## Remaining Before Enterprise Production

- Add API authentication/authorization.
- Restrict API Gateway CORS.
- Add WAF/rate limits if public.
- Move Terraform state to an encrypted remote backend with locking.
- Add CI/CD packaging, scanning, and deployment approvals.
- Add alarms for Lambda errors/throttles, DynamoDB throttles, API Gateway 5xx, and Bedrock failures.
- Add OpenSearch index migration/versioning if schema evolves.
