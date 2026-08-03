terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
  bedrock_model_arn             = "arn:${data.aws_partition.current.partition}:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}"
  opensearch_dashboard_user_arn = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:user/${var.opensearch_dashboard_iam_user_name}"
}

resource "aws_s3_bucket" "knowledge" {
  bucket_prefix = "${local.name_prefix}-knowledge-"
  force_destroy = false
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "knowledge" {
  bucket                  = aws_s3_bucket.knowledge.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "knowledge" {
  bucket = aws_s3_bucket.knowledge.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_dynamodb_table" "incidents" {
  name                        = "${local.name_prefix}-incidents"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "incident_id"
  deletion_protection_enabled = var.enable_deletion_protection

  attribute {
    name = "incident_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = local.common_tags
}

resource "aws_dynamodb_table" "audit" {
  name                        = "${local.name_prefix}-audit"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "audit_id"
  deletion_protection_enabled = var.enable_deletion_protection

  attribute {
    name = "audit_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = local.common_tags
}

resource "aws_opensearchserverless_security_policy" "knowledge_encryption" {
  name = "${local.name_prefix}-enc"
  type = "encryption"
  policy = jsonencode({
    Rules = [{
      ResourceType = "collection"
      Resource     = ["collection/${local.name_prefix}-knowledge"]
    }]
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_security_policy" "knowledge_network" {
  name = "${local.name_prefix}-net"
  type = "network"
  policy = jsonencode([
    merge(
      {
        Rules = [
          {
            ResourceType = "collection"
            Resource     = ["collection/${local.name_prefix}-knowledge"]
          },
          {
            ResourceType = "dashboard"
            Resource     = ["collection/${local.name_prefix}-knowledge"]
          }
        ]
        AllowFromPublic = var.opensearch_public_access
      },
      var.opensearch_public_access ? {} : {
        SourceVPCEs = var.opensearch_allowed_vpc_endpoint_ids
      }
    )
  ])
}

resource "aws_opensearchserverless_collection" "knowledge" {
  name       = "${local.name_prefix}-knowledge"
  type       = "VECTORSEARCH"
  depends_on = [aws_opensearchserverless_security_policy.knowledge_encryption]
  tags       = local.common_tags
}

resource "aws_iam_role" "lambda_role" {
  name = "${local.name_prefix}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role" "magento_logs_lambda_role" {
  name = "${local.name_prefix}-magento-logs-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = local.common_tags
}

resource "aws_opensearchserverless_access_policy" "knowledge" {
  name = "${local.name_prefix}-access"
  type = "data"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${aws_opensearchserverless_collection.knowledge.name}"]
          Permission   = ["aoss:DescribeCollectionItems", "aoss:CreateCollectionItems", "aoss:UpdateCollectionItems"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${aws_opensearchserverless_collection.knowledge.name}/*"]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex"
          ]
        }
      ]
      Principal = [
        aws_iam_role.lambda_role.arn,
      ]
    },
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${aws_opensearchserverless_collection.knowledge.name}"]
          Permission   = ["aoss:*"]
        },
        {
          ResourceType = "index"
          Resource     = ["index/${aws_opensearchserverless_collection.knowledge.name}/*"]
          Permission   = ["aoss:*"]
        }
      ]
      Principal = [
        local.opensearch_dashboard_user_arn
      ]
    }
  ])
}

resource "aws_iam_user_policy" "opensearch_dashboard_access" {
  name = "${local.name_prefix}-opensearch-dashboard-access"
  user = var.opensearch_dashboard_iam_user_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = aws_opensearchserverless_collection.knowledge.arn
      },
      {
        Effect = "Allow"
        Action = [
          "aoss:DashboardsAccessAll"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:aoss:${var.aws_region}:${data.aws_caller_identity.current.account_id}:dashboards/default"
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${local.name_prefix}-lambda-policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [
          "${aws_cloudwatch_log_group.api.arn}:*",
          "${aws_cloudwatch_log_group.incident_ingestion.arn}:*",
          "${aws_cloudwatch_log_group.mock_remediation.arn}:*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"]
        Resource = [aws_dynamodb_table.incidents.arn, aws_dynamodb_table.audit.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [aws_s3_bucket.knowledge.arn, "${aws_s3_bucket.knowledge.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = aws_opensearchserverless_collection.knowledge.arn
      },
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = aws_lambda_function.mock_remediation.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "magento_logs_lambda_policy" {
  name = "${local.name_prefix}-magento-logs-lambda-policy"
  role = aws_iam_role.magento_logs_lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [
          "${aws_cloudwatch_log_group.magento_logs_generator.arn}:*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"]
        Resource = [aws_dynamodb_table.incidents.arn, aws_dynamodb_table.audit.arn]
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "incident_ingestion" {
  name              = "/aws/lambda/${local.name_prefix}-incident-ingestion"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "mock_remediation" {
  name              = "/aws/lambda/${local.name_prefix}-mock-remediation"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "magento_logs_generator" {
  name              = "/aws/lambda/${local.name_prefix}-magento-logs-generator"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.lambda_role.arn
  handler          = "api.aws_lambda.handler"
  runtime          = "python3.11"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = 60
  memory_size      = 1024
  depends_on       = [aws_cloudwatch_log_group.api]
  tags             = local.common_tags

  environment {
    variables = {
      ENVIRONMENT              = "development"
      USE_AWS                  = "true"
      BEDROCK_MODEL_ID         = var.api_bedrock_model_id
      S3_BUCKET_NAME           = aws_s3_bucket.knowledge.bucket
      OPENSEARCH_ENDPOINT      = aws_opensearchserverless_collection.knowledge.collection_endpoint
      OPENSEARCH_INDEX         = var.opensearch_index_name
      DYNAMODB_INCIDENTS_TABLE = aws_dynamodb_table.incidents.name
      DYNAMODB_AUDIT_TABLE     = aws_dynamodb_table.audit.name
      REMEDIATION_LAMBDA_NAME  = aws_lambda_function.mock_remediation.function_name
    }
  }
}

resource "aws_lambda_function" "incident_ingestion" {
  function_name    = "${local.name_prefix}-incident-ingestion"
  role             = aws_iam_role.lambda_role.arn
  handler          = "api.v1.routers.ops_mvp.lambda_handler"
  runtime          = "python3.11"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = 60
  memory_size      = 1024
  depends_on       = [aws_cloudwatch_log_group.incident_ingestion]
  tags             = local.common_tags

  environment {
    variables = {
      ENVIRONMENT              = "development"
      USE_AWS                  = "true"
      BEDROCK_MODEL_ID         = var.incident_ingestion_bedrock_model_id
      S3_BUCKET_NAME           = aws_s3_bucket.knowledge.bucket
      OPENSEARCH_ENDPOINT      = aws_opensearchserverless_collection.knowledge.collection_endpoint
      OPENSEARCH_INDEX         = var.opensearch_index_name
      DYNAMODB_INCIDENTS_TABLE = aws_dynamodb_table.incidents.name
      DYNAMODB_AUDIT_TABLE     = aws_dynamodb_table.audit.name
      REMEDIATION_LAMBDA_NAME  = aws_lambda_function.mock_remediation.function_name
    }
  }
}

resource "aws_lambda_function" "mock_remediation" {
  function_name    = "${local.name_prefix}-mock-remediation"
  role             = aws_iam_role.lambda_role.arn
  handler          = "services.remediation_lambda.handler"
  runtime          = "python3.11"
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  timeout          = 30
  memory_size      = 256
  depends_on       = [aws_cloudwatch_log_group.mock_remediation]
  tags             = local.common_tags
}

resource "aws_lambda_function" "magento_logs_generator" {
  function_name    = "${local.name_prefix}-magento-logs-generator"
  role             = aws_iam_role.magento_logs_lambda_role.arn
  handler          = "services.magento_log_generator_lambda.handler"
  runtime          = "python3.11"
  filename         = var.magento_logs_lambda_zip_path
  source_code_hash = filebase64sha256(var.magento_logs_lambda_zip_path)
  timeout          = 60
  memory_size      = 1024
  depends_on       = [aws_cloudwatch_log_group.magento_logs_generator]
  tags             = local.common_tags

  environment {
    variables = {
      ENVIRONMENT              = "development"
      USE_AWS                  = "true"
      DYNAMODB_INCIDENTS_TABLE = aws_dynamodb_table.incidents.name
      DYNAMODB_AUDIT_TABLE     = aws_dynamodb_table.audit.name
    }
  }
}

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name_prefix}-http-api"
  protocol_type = "HTTP"
  cors_configuration {
    allow_headers = ["content-type", "authorization"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_origins = ["*"]
    max_age       = 300
  }
  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "magento_logs_generator" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.magento_logs_generator.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "magento_logs_generate" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /magento/logs/generate"
  target    = "integrations/${aws_apigatewayv2_integration.magento_logs_generator.id}"
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = var.api_stage_name
  auto_deploy = true
  tags        = local.common_tags

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 25
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "magento_logs_api_gateway" {
  statement_id  = "AllowExecutionFromHttpApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.magento_logs_generator.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_cloudwatch_event_rule" "incident_trigger" {
  name        = "${local.name_prefix}-incident-trigger"
  description = "Routes CloudWatch-style incident events into the MVP ingestion Lambda."
  event_pattern = jsonencode({
    source      = ["ai-ops.mvp", "aws.cloudwatch"]
    detail-type = ["CloudWatch Incident Alert", "CloudWatch Alarm State Change"]
  })
  tags = local.common_tags
}

resource "aws_cloudwatch_event_target" "ingestion" {
  rule = aws_cloudwatch_event_rule.incident_trigger.name
  arn  = aws_lambda_function.incident_ingestion.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.incident_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.incident_trigger.arn
}

resource "aws_budgets_budget" "monthly" {
  count = var.budget_alert_email == "" ? 0 : 1

  name         = "${local.name_prefix}-monthly-budget"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_limit_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
