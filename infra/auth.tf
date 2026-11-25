# Unapplied draft of auth.yaml. Do not apply against CloudFormation-managed
# resources without a reviewed ownership/import migration and a safe state backend.
# Requires an AWS provider version supporting Cognito managed login branding.
# Google client_secret is sensitive but will still be stored in Terraform state.

variable "auth_project_name" {
  type    = string
  default = "spry"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,25}$", var.auth_project_name))
    error_message = "Use 1-26 lowercase letters, digits or hyphens, starting with a letter."
  }
}

variable "auth_site_url" {
  type = string
  validation {
    condition     = can(regex("^https://[a-z0-9]+\\.cloudfront\\.net$", var.auth_site_url))
    error_message = "Use an HTTPS CloudFront origin without a trailing slash."
  }
}

variable "auth_domain_prefix" {
  type    = string
  default = "spry-lab-673478369996"
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.auth_domain_prefix))
    error_message = "Use 3-63 lowercase letters, digits or hyphens, starting and ending with a letter or digit."
  }
}

variable "auth_google_client_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]+-[a-zA-Z0-9_-]+\\.apps\\.googleusercontent\\.com$", var.auth_google_client_id))
    error_message = "Use a Google OAuth web client ID."
  }
}

variable "auth_google_client_secret" {
  type      = string
  sensitive = true
  validation {
    condition     = length(var.auth_google_client_secret) >= 10
    error_message = "The Google OAuth client secret must be at least 10 characters."
  }
}

data "aws_region" "auth" {}

resource "aws_cognito_user_pool" "auth" {
  name                = "${var.auth_project_name}-users"
  user_pool_tier      = "ESSENTIALS"
  deletion_protection = "ACTIVE"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"

  username_configuration {
    case_sensitive = false
  }
  admin_create_user_config {
    allow_admin_create_user_only = false
  }
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = 0
      max_length = 2048
    }
  }
  tags = {
    PROJECT_NAME = var.auth_project_name
  }

  # CFN retains the pool on deletion/replacement. Terraform cannot directly
  # express that policy: block those actions until an operator handles retention.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cognito_identity_provider" "auth_google" {
  user_pool_id  = aws_cognito_user_pool.auth.id
  provider_name = "Google"
  provider_type = "Google"
  provider_details = {
    client_id        = var.auth_google_client_id
    client_secret    = var.auth_google_client_secret
    authorize_scopes = "openid email profile"
  }
  attribute_mapping = {
    email          = "email"
    email_verified = "email_verified"
  }
}

resource "aws_cognito_user_pool_client" "auth" {
  name         = "${var.auth_project_name}-web"
  user_pool_id = aws_cognito_user_pool.auth.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO", "Google"]
  callback_urls = [
    "${var.auth_site_url}/auth/callback/",
    "http://localhost:5173/auth/callback/",
  ]
  logout_urls = [
    "${var.auth_site_url}/",
    "http://localhost:5173/",
  ]
  access_token_validity         = 15
  id_token_validity             = 15
  refresh_token_validity        = 1
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  depends_on = [aws_cognito_identity_provider.auth_google]
}

resource "aws_cognito_user_pool_domain" "auth" {
  domain                = var.auth_domain_prefix
  user_pool_id          = aws_cognito_user_pool.auth.id
  managed_login_version = 2
}

resource "aws_cognito_managed_login_branding" "auth" {
  user_pool_id                = aws_cognito_user_pool.auth.id
  client_id                   = aws_cognito_user_pool_client.auth.id
  use_cognito_provided_values = true

  depends_on = [aws_cognito_user_pool_domain.auth]
}

output "auth_user_pool_id" {
  value = aws_cognito_user_pool.auth.id
}

output "auth_cognito_issuer" {
  value = "https://cognito-idp.${data.aws_region.auth.region}.amazonaws.com/${aws_cognito_user_pool.auth.id}"
}

output "auth_cognito_client_id" {
  value = aws_cognito_user_pool_client.auth.id
}

output "auth_cognito_domain" {
  value = "https://${var.auth_domain_prefix}.auth.${data.aws_region.auth.region}.amazoncognito.com"
}

output "auth_login_url" {
  value = "${var.auth_site_url}/login/"
}
