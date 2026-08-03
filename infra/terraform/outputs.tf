output "api_endpoint" {
  value = aws_apigatewayv2_stage.api.invoke_url
}

output "aws_region" {
  value = var.aws_region
}

output "knowledge_bucket" {
  value = aws_s3_bucket.knowledge.bucket
}

output "incidents_table" {
  value = aws_dynamodb_table.incidents.name
}

output "audit_table" {
  value = aws_dynamodb_table.audit.name
}

output "opensearch_collection_endpoint" {
  value = aws_opensearchserverless_collection.knowledge.collection_endpoint
}

output "opensearch_dashboard_endpoint" {
  value = aws_opensearchserverless_collection.knowledge.dashboard_endpoint
}

output "opensearch_dashboard_login_url" {
  value = "https://dashboards.${var.aws_region}.aoss.amazonaws.com/_login/?collectionId=${aws_opensearchserverless_collection.knowledge.id}"
}

output "eventbridge_rule" {
  value = aws_cloudwatch_event_rule.incident_trigger.name
}

output "api_lambda_name" {
  value = aws_lambda_function.api.function_name
}

output "incident_ingestion_lambda_name" {
  value = aws_lambda_function.incident_ingestion.function_name
}

output "mock_remediation_lambda_name" {
  value = aws_lambda_function.mock_remediation.function_name
}

output "magento_logs_generator_lambda_name" {
  value = aws_lambda_function.magento_logs_generator.function_name
}
