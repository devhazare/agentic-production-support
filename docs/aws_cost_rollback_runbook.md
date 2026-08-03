# AWS Cost and Rollback Runbook

Last reviewed: 2026-06-28

## Two-day MVP cost expectation

For a short demo deployment, OpenSearch Serverless is the main cost driver because it bills for active OpenSearch Compute Units while the collection exists. The rest of the stack is mostly request-based.

Approximate two-day light-usage estimate:

| Area | Two-day estimate | Notes |
| --- | ---: | --- |
| OpenSearch Serverless vector collection | USD 23-35+ | Dominant idle cost. Depends on active OCUs, region, and collection configuration. |
| Bedrock Claude Sonnet | USD 0.10-5.00 | Depends on real token volume. Demo traffic should stay low. |
| Lambda | Usually under USD 1.00 | Charged by requests and duration. No meaningful idle charge. |
| API Gateway HTTP API | Usually under USD 1.00 | Charged by API calls and data transfer. |
| DynamoDB on-demand | Usually under USD 1.00 | Writes/reads plus tiny storage/PITR for sample data. |
| S3 | Usually cents | Small runbook/RCA sample files. |
| EventBridge | Usually cents | Charged when events are published. |
| CloudWatch Logs | Usually cents to a few USD | Depends on log volume and retention. |

Expected total for two days with OpenSearch Serverless enabled: roughly USD 25-45 for light MVP testing. Without OpenSearch Serverless, the same light demo should generally be under USD 5.

Always verify with AWS Pricing Calculator for the exact target region before leaving resources up.

## Budget guardrail

Create the stack with a budget alert email for short test runs:

```bash
terraform -chdir=infra/terraform apply \
  -var="aws_region=ap-south-1" \
  -var="budget_alert_email=you@example.com" \
  -var="monthly_budget_limit_usd=50" \
  -var="enable_deletion_protection=false"
```

The budget sends alerts at 50% actual spend and 80% forecasted spend.

## Rollback

Use the same variables that were used during apply.

For short-lived demo environments:

```bash
terraform -chdir=infra/terraform destroy \
  -var="aws_region=ap-south-1" \
  -var="enable_deletion_protection=false"
```

If the stack was created with DynamoDB deletion protection enabled:

```bash
terraform -chdir=infra/terraform apply \
  -var="aws_region=ap-south-1" \
  -var="enable_deletion_protection=false"

terraform -chdir=infra/terraform destroy \
  -var="aws_region=ap-south-1" \
  -var="enable_deletion_protection=false"
```

If cost is increasing unexpectedly, remove the OpenSearch Serverless collection first because it is the largest idle cost in this MVP:

```bash
terraform -chdir=infra/terraform destroy \
  -target=aws_opensearchserverless_collection.knowledge \
  -var="aws_region=ap-south-1" \
  -var="enable_deletion_protection=false"
```

Then run a full `terraform destroy` when the test is complete.

## Idle charge profile

No meaningful idle charge:

- Lambda functions
- API Gateway HTTP API, aside from requests/data transfer
- EventBridge rule, aside from events
- Bedrock, aside from model invocations

Low but nonzero idle/storage charge:

- DynamoDB table storage and PITR
- S3 storage and object requests
- CloudWatch log storage

Material idle charge:

- OpenSearch Serverless collection
- PrivateLink/VPC endpoints, if private OpenSearch access is enabled later

## Production movement path

1. Package Lambda:

   ```bash
   ./scripts/package_lambda.sh
   ```

2. Plan infrastructure:

   ```bash
   terraform -chdir=infra/terraform plan \
     -var="aws_region=ap-south-1" \
     -var="budget_alert_email=you@example.com" \
     -var="monthly_budget_limit_usd=50" \
     -var="enable_deletion_protection=false"
   ```

3. Apply to a dev AWS environment first.
4. Seed S3/OpenSearch knowledge with `scripts/ingest_knowledge.py`.
5. Smoke test `/health`, `/incidents/trigger`, `/incidents/{id}`, approval, and mock remediation.
6. Review CloudWatch logs, DynamoDB incident records, and audit records.
7. For staging/prod, add a remote Terraform backend, CI/CD approval, API authentication, restricted CORS, private OpenSearch network access, alarms, and environment-specific variables.

