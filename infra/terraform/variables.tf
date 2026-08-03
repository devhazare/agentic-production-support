variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "ai-ops-mvp"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "lambda_zip_path" {
  type    = string
  default = "build/lambda.zip"
}

variable "magento_logs_lambda_zip_path" {
  type    = string
  default = "build/magento_logs_lambda.zip"
}

variable "bedrock_model_id" {
  type    = string
  default = "apac.anthropic.claude-3-5-sonnet-20240620-v1:0"
}

variable "api_bedrock_model_id" {
  type    = string
  default = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "incident_ingestion_bedrock_model_id" {
  type    = string
  default = "apac.anthropic.claude-3-5-sonnet-20240620-v1:0"
}

variable "opensearch_index_name" {
  type    = string
  default = "incident-knowledge"
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "api_stage_name" {
  type    = string
  default = "$default"
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection on DynamoDB tables. Keep true for shared environments; set false for short-lived demo environments that need easy terraform destroy."
  type        = bool
  default     = true
}

variable "monthly_budget_limit_usd" {
  description = "Monthly AWS Budget limit in USD. Used only when budget_alert_email is set."
  type        = string
  default     = "50"
}

variable "budget_alert_email" {
  description = "Email address for AWS Budget alerts. Leave empty to skip creating an AWS Budget."
  type        = string
  default     = ""
}

variable "opensearch_public_access" {
  type    = bool
  default = true
}

variable "opensearch_allowed_vpc_endpoint_ids" {
  type    = list(string)
  default = []
}

variable "opensearch_dashboard_iam_user_name" {
  description = "IAM user that can open the OpenSearch Serverless Dashboards URL in a browser."
  type        = string
  default     = "devendrah"
}
