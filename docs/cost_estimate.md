# Cost Estimate Notes

No fixed cloud cost estimate is included because costs depend on region, usage,
model selection, request volume, vector index size, retention, and deployment
topology.

Potential cost areas for the optional AWS path:

- Bedrock model inference.
- OpenSearch Serverless collection usage.
- DynamoDB reads/writes and storage.
- S3 storage and requests.
- Lambda invocations and duration.
- CloudWatch logs and metrics.
- NAT gateways or VPC networking if introduced.

For local mock mode, cloud cost should be zero when `USE_AWS=false`.
