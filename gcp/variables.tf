variable "project_id" {
  type        = string
  description = "An existing, dedicated GCP lab project ID. This stack does not create projects or attach billing."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Use a Google Cloud project ID of 6–30 lowercase letters, digits, and hyphens."
  }
}

variable "region" {
  type        = string
  description = "Region shared by Cloud Run, Cloud SQL, and Artifact Registry."
  default     = "us-central1"
}

variable "backend_image_digest" {
  type        = string
  description = "Digest of the backend image already pushed to the Lab 9 Artifact Registry repository; null skips Cloud Run."
  default     = null

  validation {
    condition     = var.backend_image_digest == null || can(regex("^sha256:[a-f0-9]{64}$", var.backend_image_digest))
    error_message = "Use a sha256 digest, not an image tag or URL."
  }
}

variable "cognito_issuer" {
  type        = string
  description = "Existing AWS Cognito HTTPS user-pool issuer. Required when deploying Cloud Run."
  default     = null

  validation {
    condition = var.cognito_issuer == null || try(
      can(regex("^https://cognito-idp\\.[a-z]{2}(-[a-z]+)+-[0-9]\\.amazonaws\\.com(\\.cn)?/[a-z]{2}(-[a-z]+)+-[0-9]_[A-Za-z0-9]+$", var.cognito_issuer)) &&
      startswith(split("/", var.cognito_issuer)[3], "${split(".", var.cognito_issuer)[1]}_"),
      false,
    )
    error_message = "Use an exact AWS Cognito user-pool issuer URL."
  }
}

variable "cognito_client_id" {
  type        = string
  description = "Existing public AWS Cognito client ID. Required when deploying Cloud Run."
  default     = null

  validation {
    condition     = var.cognito_client_id == null || can(regex("^[A-Za-z0-9]{1,128}$", var.cognito_client_id))
    error_message = "Use the public Cognito app-client ID."
  }
}

variable "cors_origins" {
  type        = string
  description = "Comma-separated trusted browser origins; this does not grant Cloud Run invocation."
  default     = "http://localhost:5173"
}

variable "cloud_run_invokers" {
  type        = set(string)
  description = "Named user, group, or service account principals allowed to invoke this Cloud Run service. No public or domain-wide principals."
  default     = []

  validation {
    condition     = alltrue([for member in var.cloud_run_invokers : can(regex("^(user|group|serviceAccount):[^:@*\\s]+@[^:@*\\s]+$", member))])
    error_message = "Use principals like user:alice@example.com or group:spry-lab@example.com."
  }
}

variable "database_running" {
  type        = bool
  description = "Set false to stop Cloud SQL compute; disk costs continue and DB-backed API requests fail."
  default     = true
}

variable "database_deletion_protection" {
  type        = bool
  description = "Protect the database in Terraform and in the Cloud SQL API. Disable and apply before intentional destroy."
  default     = true
}
