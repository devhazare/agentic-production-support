# AWS Cost and Rollback Runbook

This is a planning guide for the optional AWS reference path.

## Cost Controls

- Keep `USE_AWS=false` for local development.
- Set low Bedrock token limits during experiments.
- Restrict load tests to reviewed environments.
- Monitor OpenSearch Serverless, DynamoDB, Lambda, S3, and Bedrock usage.
- Destroy temporary infrastructure when experiments are complete.

## Rollback Approach

For infrastructure experiments:

1. Review Terraform plan output.
2. Keep state in a secure remote backend before team use.
3. Apply changes only in a non-production account first.
4. Roll back by reverting Terraform changes and applying a reviewed plan.
5. Confirm no generated packages, credentials, or state files are committed.

## Repository Safety

Terraform state and generated Lambda packages should stay out of Git.
