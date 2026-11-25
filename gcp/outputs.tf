output "backend_image_repository" {
  description = "Push the Cloud Run image to this repository and pass its digest as backend_image_digest."
  value       = local.image_repository
}

output "cloud_run_url" {
  description = "IAM-protected Cloud Run HTTPS endpoint; null until an image is configured."
  value       = one(google_cloud_run_v2_service.backend[*].uri)
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name for the Cloud SQL Auth Proxy."
  value       = google_sql_database_instance.postgres.connection_name
}
