# Draft only: existing CloudFormation resources must be imported or otherwise
# migrated deliberately before applying. Budget notifications do not cap spend.
provider "aws" {
  alias  = "ai"
  region = "us-east-1"
}

variable "ai_image_uri" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.us-east-1\\.amazonaws\\.com/spry-ai:[a-f0-9]{40}$", var.ai_image_uri))
    error_message = "Must be a us-east-1 spry-ai ECR image with a 40-character lowercase hexadecimal tag."
  }
}

variable "ai_cognito_issuer" {
  type = string
  validation {
    condition     = can(regex("^https://cognito-idp\\.eu-north-1\\.amazonaws\\.com/eu-north-1_[A-Za-z0-9]+$", var.ai_cognito_issuer))
    error_message = "Must be a Cognito issuer URL in eu-north-1."
  }
}

variable "ai_cognito_client_id" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]{1,128}$", var.ai_cognito_client_id))
    error_message = "Must be a lowercase alphanumeric Cognito client ID."
  }
}

variable "ai_site_origin" {
  type = string
  validation {
    condition     = can(regex("^https://[a-z0-9]+\\.cloudfront\\.net$", var.ai_site_origin))
    error_message = "Must be an HTTPS CloudFront origin."
  }
}

variable "ai_parser_model" {
  type        = string
  default     = "us.amazon.nova-micro-v1:0"
  description = "US cross-region inference profile ID; availability and quotas require separate verification."
  validation {
    condition     = can(regex("^us\\.(amazon\\.nova-[a-z0-9.:-]+|anthropic\\.claude-[a-z0-9.:-]+)$", var.ai_parser_model))
    error_message = "Must be a supported US Nova or Claude inference profile ID."
  }
}

variable "ai_parser_input_price_per_million" {
  type        = number
  default     = 0.035
  description = "USD per million input tokens; update when changing model."
  validation {
    condition     = var.ai_parser_input_price_per_million >= 0
    error_message = "Price must be nonnegative."
  }
}

variable "ai_parser_output_price_per_million" {
  type        = number
  default     = 0.14
  description = "USD per million output tokens; estimates do not enforce billing limits."
  validation {
    condition     = var.ai_parser_output_price_per_million >= 0
    error_message = "Price must be nonnegative."
  }
}

data "aws_caller_identity" "ai" {
  provider = aws.ai
}

data "aws_partition" "ai" {
  provider = aws.ai
}

locals {
  ai_inference_profile_arn = "arn:${data.aws_partition.ai.partition}:bedrock:us-east-1:${data.aws_caller_identity.ai.account_id}:inference-profile/${var.ai_parser_model}"
  ai_foundation_model      = trimprefix(var.ai_parser_model, "us.")
}

resource "aws_cloudwatch_log_group" "ai_parser_logs" {
  provider          = aws.ai
  name              = "/aws/lambda/spry-agenda-parser"
  retention_in_days = 14
  tags              = { Project = "spry" }
}

resource "aws_iam_role" "ai_parser_role" {
  provider = aws.ai
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "spry" }
}

resource "aws_iam_role_policy_attachment" "ai_parser_basic_execution" {
  provider   = aws.ai
  role       = aws_iam_role.ai_parser_role.name
  policy_arn = "arn:${data.aws_partition.ai.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ai_parser_invoke_profile" {
  provider = aws.ai
  name     = "InvokeSelectedInferenceProfile"
  role     = aws_iam_role.ai_parser_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = local.ai_inference_profile_arn
      },
      {
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = "arn:${data.aws_partition.ai.partition}:bedrock:us-*::foundation-model/${local.ai_foundation_model}"
        Condition = {
          StringEquals = { "bedrock:InferenceProfileArn" = local.ai_inference_profile_arn }
        }
      }
    ]
  })
}

resource "aws_lambda_function" "ai_parser" {
  provider                       = aws.ai
  function_name                  = "spry-agenda-parser"
  package_type                   = "Image"
  image_uri                      = var.ai_image_uri
  architectures                  = ["arm64"]
  role                           = aws_iam_role.ai_parser_role.arn
  timeout                        = 30
  memory_size                    = 512
  reserved_concurrent_executions = 2

  image_config {
    command = ["app.ai.agenda_lambda.handler"]
  }

  environment {
    variables = {
      PARSER_MODEL                    = var.ai_parser_model
      PARSER_INPUT_PRICE_PER_MILLION  = tostring(var.ai_parser_input_price_per_million)
      PARSER_OUTPUT_PRICE_PER_MILLION = tostring(var.ai_parser_output_price_per_million)
      COGNITO_ISSUER                  = var.ai_cognito_issuer
      COGNITO_CLIENT_ID               = var.ai_cognito_client_id
    }
  }

  tags       = { Project = "spry" }
  depends_on = [aws_cloudwatch_log_group.ai_parser_logs]
}

resource "aws_lambda_function_url" "ai_parser_url" {
  provider           = aws.ai
  function_name      = aws_lambda_function.ai_parser.function_name
  authorization_type = "NONE"
  cors {
    allow_origins = [var.ai_site_origin]
    allow_methods = ["POST"]
    allow_headers = ["Authorization", "Content-Type"]
    max_age       = 300
  }
}

resource "aws_lambda_permission" "ai_parser_url_permission" {
  provider               = aws.ai
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.ai_parser.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "ai_parser_invoke_permission" {
  provider                 = aws.ai
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.ai_parser.function_name
  principal                = "*"
  invoked_via_function_url = true
}

# Account-wide intentionally: tags cannot reliably attribute shared Bedrock costs.
resource "aws_budgets_budget" "ai_monthly" {
  provider     = aws.ai
  name         = "spry-ai-monthly-alert"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["mandzyuk.pn@ucu.edu.ua"]
  }
}

output "ai_parser_url" {
  value = aws_lambda_function_url.ai_parser_url.function_url
}

output "ai_parser_function_name" {
  value = aws_lambda_function.ai_parser.function_name
}
