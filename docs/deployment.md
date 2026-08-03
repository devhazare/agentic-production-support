# Deployment Notes

The repository includes a simple Docker path and experimental AWS reference
infrastructure. Treat these as starting points, not production-ready deployment
instructions.

## Local Docker

```bash
docker compose up --build
```

The compose file starts the FastAPI service on port `8000` and mounts `.local`
for local incident state. The Streamlit dashboard is run separately:

```bash
streamlit run ui/dashboard.py
```

## Direct Local Run

```bash
uvicorn api.main:app --reload --port 8000
```

## AWS Reference Path

The repository contains Terraform and packaging scripts for an AWS-oriented MVP:

- `scripts/package_lambda.sh`
- `scripts/package_magento_logs_lambda.sh`
- `infra/terraform/`

The code references Bedrock, S3, OpenSearch Serverless, DynamoDB, and Lambda
when `USE_AWS=true`.

## Production Requirements Before Deployment

- Add authentication and authorization.
- Replace mock remediation with reviewed, least-privilege executors.
- Add real approval identity and audit controls.
- Move secrets to a managed secret store.
- Review Terraform state handling and backend configuration.
- Add monitoring, alerting, rate limits, and request validation controls.
- Add CI/CD, dependency scanning, and secret scanning.
