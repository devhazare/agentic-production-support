# Deployment

## Local

Use Docker Compose:

```bash
docker compose up --build
```

The API starts on `http://localhost:8000`.

For local non-Docker installs, create the virtual environment with Python 3.11:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## AWS Deployment

Prerequisites:

- AWS credentials configured for the target account.
- Bedrock model access enabled for Claude Sonnet in the selected region.
- Terraform `>= 1.5`.
- Python 3.11 available as `python3.11`.

Package the Lambda zip before `terraform apply`:

```bash
./scripts/package_lambda.sh
cd infra/terraform
terraform init
terraform plan
terraform apply
```

The Terraform is pay-as-used oriented:

- Lambda for API, EventBridge ingestion, and mock remediation.
- API Gateway HTTP API for MVP endpoints.
- EventBridge rule for incident events.
- DynamoDB on-demand tables with point-in-time recovery.
- S3 bucket for knowledge files.
- OpenSearch Serverless vector collection, encryption policy, network policy, and data access policy.
- CloudWatch Logs retention.

Outputs include `api_endpoint`, table names, bucket name, Lambda names, and OpenSearch endpoints.

Smoke test after apply:

```bash
API_ENDPOINT="$(terraform output -raw api_endpoint)"
curl "$API_ENDPOINT/health"
curl -X POST "$API_ENDPOINT/incidents/trigger" \
  -H 'content-type: application/json' \
  -d @../../sample_data/incidents/checkout_latency.json
```

Seed sample knowledge after apply:

```bash
export USE_AWS=true
export AWS_REGION="$(terraform output -raw aws_region 2>/dev/null || echo us-east-1)"
export S3_BUCKET_NAME="$(terraform output -raw knowledge_bucket)"
export OPENSEARCH_ENDPOINT="$(terraform output -raw opensearch_collection_endpoint)"
export OPENSEARCH_INDEX=incident-knowledge
python ../../scripts/ingest_knowledge.py
```

Production hardening switches:

- Set `opensearch_public_access=false`.
- Provide `opensearch_allowed_vpc_endpoint_ids`.
- Replace permissive API CORS with your allowed dashboard/domain origins.
- Add auth in front of API Gateway before exposing outside an internal network.
- Use a remote Terraform backend with state locking.
- Run Lambda packaging in CI and publish immutable artifacts.
