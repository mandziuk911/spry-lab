# Draft translation of reports.yaml. Do not apply alongside the CloudFormation
# stack: existing resources require an explicit migration/import plan.
# DATABASE_URL is resolved at apply time and is stored in Terraform state; secure
# the state and re-apply after rotating the secret, as with CFN dynamic references.

variable "reports_project_name" {
  type    = string
  default = "spry"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,25}$", var.reports_project_name))
    error_message = "Use 1-26 lowercase letters, digits or hyphens, starting with a letter."
  }
}
variable "reports_image_uri" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9][a-z0-9._/-]*:[0-9a-f]{40}$", var.reports_image_uri))
    error_message = "Image URI must contain a full 40-character commit SHA tag."
  }
}
variable "reports_vpc_id" { type = string }
variable "reports_private_subnet_ids" { type = list(string) }
variable "reports_private_route_table_id" {
  type = string
  validation {
    condition     = can(regex("^rtb-[0-9a-f]+$", var.reports_private_route_table_id))
    error_message = "Expected a route table ID."
  }
}
variable "reports_database_security_group_id" {
  type = string
  validation {
    condition     = can(regex("^sg-[0-9a-f]+$", var.reports_database_security_group_id))
    error_message = "Expected a security group ID."
  }
}
variable "reports_database_url_secret_arn" {
  type = string
  validation {
    condition     = can(regex("^arn:aws:secretsmanager:eu-north-1:673478369996:secret:.+$", var.reports_database_url_secret_arn))
    error_message = "Expected a Secrets Manager ARN in the configured account and region."
  }
}
variable "reports_report_email" {
  type      = string
  sensitive = true
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.reports_report_email))
    error_message = "Expected an email address."
  }
}
variable "reports_cognito_issuer" { type = string }
variable "reports_cognito_client_id" { type = string }

data "aws_caller_identity" "reports" {}
data "aws_region" "reports" {}
data "aws_partition" "reports" {}
data "aws_secretsmanager_secret_version" "reports_database_url" {
  secret_id = var.reports_database_url_secret_arn
}

locals {
  reports_bucket_name = "${var.reports_project_name}-reports-${data.aws_caller_identity.reports.account_id}"
  reports_bucket_arn  = "arn:${data.aws_partition.reports.partition}:s3:::${local.reports_bucket_name}"
  reports_ecr_arn     = "arn:${data.aws_partition.reports.partition}:ecr:${data.aws_region.reports.region}:${data.aws_caller_identity.reports.account_id}:repository/${var.reports_project_name}-reports"
  reports_tags        = { Project = var.reports_project_name }
  reports_lambda_assume_role = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_ses_email_identity" "reports" {
  email = var.reports_report_email
}
resource "aws_s3_bucket" "reports" {
  bucket = local.reports_bucket_name
  tags   = local.reports_tags
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    id     = "ExpireReportsAfter90Days"
    status = "Enabled"
    filter { prefix = "reports/" }
    expiration { days = 90 }
  }
}
resource "aws_sqs_queue" "reports_dlq" {
  name                      = "${var.reports_project_name}-report-requests-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = local.reports_tags
}
resource "aws_sqs_queue" "reports" {
  name                       = "${var.reports_project_name}-report-requests"
  visibility_timeout_seconds = 360
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.reports_dlq.arn
    maxReceiveCount     = 3
  })
  tags = local.reports_tags
}
resource "aws_vpc_endpoint" "reports_s3" {
  vpc_id            = var.reports_vpc_id
  vpc_endpoint_type = "Gateway"
  service_name      = "com.amazonaws.${data.aws_region.reports.region}.s3"
  route_table_ids   = [var.reports_private_route_table_id]
  tags              = local.reports_tags
}
resource "aws_security_group" "reports_builder" {
  description = "Outbound-only report builder access to PostgreSQL and S3 gateway endpoint"
  vpc_id      = var.reports_vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.reports_tags
}
resource "aws_security_group_rule" "reports_database_ingress" {
  type                     = "ingress"
  security_group_id        = var.reports_database_security_group_id
  source_security_group_id = aws_security_group.reports_builder.id
  protocol                 = "tcp"
  from_port                = 5432
  to_port                  = 5432
  description              = "PostgreSQL from the private report builder only"
}
resource "aws_iam_role" "reports_builder" {
  assume_role_policy  = local.reports_lambda_assume_role
  managed_policy_arns = ["arn:${data.aws_partition.reports.partition}:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"]
  tags                = local.reports_tags
  inline_policy {
    name = "BuildAndStoreReports"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = local.reports_ecr_arn },
        { Effect = "Allow", Action = "s3:PutObject", Resource = "${local.reports_bucket_arn}/reports/*" },
        { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.reports.arn },
        { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.reports_database_url_secret_arn }
      ]
    })
  }
}
resource "aws_lambda_function" "reports_builder" {
  function_name = "${var.reports_project_name}-report-builder"
  package_type  = "Image"
  image_uri     = var.reports_image_uri
  architectures = ["arm64"]
  role          = aws_iam_role.reports_builder.arn
  timeout       = 60
  memory_size   = 512
  image_config { command = ["app.reports.lambda_handler.handler"] }
  vpc_config {
    subnet_ids         = var.reports_private_subnet_ids
    security_group_ids = [aws_security_group.reports_builder.id]
  }
  environment {
    variables = {
      REPORTS_BUCKET    = local.reports_bucket_name
      DATABASE_URL      = data.aws_secretsmanager_secret_version.reports_database_url.secret_string
      COGNITO_ISSUER    = var.reports_cognito_issuer
      COGNITO_CLIENT_ID = var.reports_cognito_client_id
    }
  }
  tags       = local.reports_tags
  depends_on = [aws_cloudwatch_log_group.reports_builder]
}
resource "aws_iam_role" "reports_mailer" {
  assume_role_policy  = local.reports_lambda_assume_role
  managed_policy_arns = ["arn:${data.aws_partition.reports.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"]
  tags                = local.reports_tags
  inline_policy {
    name = "ReadAndMailReports"
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = local.reports_ecr_arn },
        { Effect = "Allow", Action = "s3:GetObject", Resource = "${local.reports_bucket_arn}/reports/*" },
        { Effect = "Allow", Action = ["ses:SendEmail", "ses:SendRawEmail"], Resource = "arn:${data.aws_partition.reports.partition}:ses:${data.aws_region.reports.region}:${data.aws_caller_identity.reports.account_id}:identity/${var.reports_report_email}" }
      ]
    })
  }
}
resource "aws_lambda_function" "reports_mailer" {
  function_name = "${var.reports_project_name}-report-mailer"
  package_type  = "Image"
  image_uri     = var.reports_image_uri
  architectures = ["arm64"]
  role          = aws_iam_role.reports_mailer.arn
  timeout       = 30
  memory_size   = 256
  image_config { command = ["app.reports.mailer.handler"] }
  environment {
    variables = {
      REPORTS_BUCKET = local.reports_bucket_name
      REPORT_EMAIL   = var.reports_report_email
    }
  }
  tags       = local.reports_tags
  depends_on = [aws_cloudwatch_log_group.reports_mailer]
}
resource "aws_lambda_permission" "reports_mailer_s3" {
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.reports_mailer.arn
  principal      = "s3.amazonaws.com"
  source_account = data.aws_caller_identity.reports.account_id
  source_arn     = local.reports_bucket_arn
}
# S3 owns one notification configuration per bucket; import/merge any existing
# notifications before migration. The separate resource breaks the CFN cycle.
resource "aws_s3_bucket_notification" "reports" {
  bucket = aws_s3_bucket.reports.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.reports_mailer.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".csv"
  }
  depends_on = [aws_lambda_permission.reports_mailer_s3]
}
resource "aws_lambda_event_source_mapping" "reports_builder" {
  event_source_arn = aws_sqs_queue.reports.arn
  function_name    = aws_lambda_function.reports_builder.arn
  batch_size       = 1
  enabled          = true
}
resource "aws_iam_role" "reports_schedule" {
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = local.reports_tags
  inline_policy {
    name = "QueueWeeklyReport"
    policy = jsonencode({
      Version   = "2012-10-17"
      Statement = [{ Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.reports.arn }]
    })
  }
}
resource "aws_scheduler_schedule" "reports_weekly" {
  name                         = "${var.reports_project_name}-weekly-report"
  description                  = "Request the previous ISO week's report every Monday morning in Kyiv."
  state                        = "ENABLED"
  schedule_expression          = "cron(0 7 ? * MON *)"
  schedule_expression_timezone = "Europe/Kyiv"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_sqs_queue.reports.arn
    role_arn = aws_iam_role.reports_schedule.arn
    input    = jsonencode({ week = null, source = "schedule" })
  }
}
resource "aws_cloudwatch_metric_alarm" "reports_dlq" {
  alarm_name          = "${var.reports_project_name}-report-dlq-not-empty"
  alarm_description   = "Report requests require investigation after three failed deliveries."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.reports_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  tags                = local.reports_tags
}
resource "aws_cloudwatch_log_group" "reports_builder" {
  name              = "/aws/lambda/${var.reports_project_name}-report-builder"
  retention_in_days = 14
  tags              = local.reports_tags
  lifecycle { prevent_destroy = true }
}
resource "aws_cloudwatch_log_group" "reports_mailer" {
  name              = "/aws/lambda/${var.reports_project_name}-report-mailer"
  retention_in_days = 14
  tags              = local.reports_tags
  lifecycle { prevent_destroy = true }
}

output "reports_bucket_name" { value = aws_s3_bucket.reports.id }
output "reports_queue_url" { value = aws_sqs_queue.reports.id }
output "reports_queue_arn" { value = aws_sqs_queue.reports.arn }
output "reports_builder_function_name" { value = aws_lambda_function.reports_builder.function_name }
output "reports_mailer_function_name" { value = aws_lambda_function.reports_mailer.function_name }
output "reports_scheduler_name" { value = aws_scheduler_schedule.reports_weekly.name }
output "reports_schedule_role_arn" { value = aws_iam_role.reports_schedule.arn }
