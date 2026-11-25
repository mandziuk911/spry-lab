locals {
  backend_enabled    = var.backend_image_digest != null
  runtime_account_id = "spry-lab9-runtime"
  runtime_account    = "${local.runtime_account_id}@${var.project_id}.iam.gserviceaccount.com"
  image_repository   = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend.repository_id}/backend"
}

resource "google_project_service" "lab" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false # Do not disable APIs that another stack might also use.
}

resource "google_artifact_registry_repository" "backend" {
  location      = var.region
  repository_id = "spry-lab9"
  description   = "Spry Lab 9 Cloud Run images"
  format        = "DOCKER"

  depends_on = [google_project_service.lab["artifactregistry.googleapis.com"]]
}

resource "google_sql_database_instance" "postgres" {
  name                = "spry-lab9-postgres"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.database_deletion_protection

  settings {
    edition                     = "ENTERPRISE"
    tier                        = "db-f1-micro"
    availability_type           = "ZONAL"
    activation_policy           = var.database_running ? "ALWAYS" : "NEVER"
    disk_type                   = "PD_SSD"
    disk_size                   = 10
    disk_autoresize             = false
    deletion_protection_enabled = var.database_deletion_protection

    ip_configuration {
      # Cloud Run uses the authenticated Cloud SQL connector over this IP.
      # No authorized networks are configured for direct connections.
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }
  }

  depends_on = [google_project_service.lab["sqladmin.googleapis.com"]]
}

resource "google_sql_database" "spry" {
  name     = "spry"
  instance = google_sql_database_instance.postgres.name
}

resource "random_password" "postgres" {
  length  = 40
  special = false # Alphanumerics also work literally in a PostgreSQL URI.
}

resource "google_sql_user" "spry" {
  name     = "spry"
  instance = google_sql_database_instance.postgres.name
  password = random_password.postgres.result
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "spry-lab9-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.lab["secretmanager.googleapis.com"]]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  # Inject the complete DSN to match the existing app's DATABASE_URL contract.
  secret_data = format(
    "postgresql+psycopg://%s:%s@/%s?host=%s",
    google_sql_user.spry.name,
    random_password.postgres.result,
    google_sql_database.spry.name,
    urlencode("/cloudsql/${google_sql_database_instance.postgres.connection_name}"),
  )
}

resource "google_secret_manager_secret_iam_member" "runtime_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.runtime_account}"
}

resource "google_cloud_run_v2_service" "backend" {
  count = local.backend_enabled ? 1 : 0

  name                 = "spry-lab9-api"
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  deletion_protection  = false

  template {
    service_account       = local.runtime_account
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }

    containers {
      image = "${local.image_repository}@${var.backend_image_digest}"

      ports {
        container_port = 8080
      }

      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = google_secret_manager_secret_version.database_url.version
          }
        }
      }

      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }

      env {
        name  = "COGNITO_ISSUER"
        value = var.cognito_issuer
      }

      env {
        name  = "COGNITO_CLIENT_ID"
        value = var.cognito_client_id
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.cognito_issuer != null && var.cognito_client_id != null
      error_message = "Set both Cognito values before deploying the current Spry backend."
    }
  }

  depends_on = [
    google_project_service.lab["run.googleapis.com"],
    google_secret_manager_secret_iam_member.runtime_database_url,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = local.backend_enabled ? var.cloud_run_invokers : toset([])

  name     = google_cloud_run_v2_service.backend[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = each.value
}
