mock_provider "google" {}
mock_provider "random" {}

variables {
  project_id = "spry-lab9-example"
}

run "database_and_registry_before_image" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_service.backend) == 0 && length(google_cloud_run_v2_service_iam_member.invoker) == 0
    error_message = "There must be no Cloud Run service or invoker grant before an image is pushed."
  }

  assert {
    condition = (
      google_sql_database_instance.postgres.database_version == "POSTGRES_16" &&
      google_sql_database_instance.postgres.settings[0].tier == "db-f1-micro" &&
      google_sql_database_instance.postgres.settings[0].disk_size == 10 &&
      google_sql_database_instance.postgres.settings[0].disk_type == "PD_SSD" &&
      google_sql_database_instance.postgres.settings[0].ip_configuration[0].ssl_mode == "ENCRYPTED_ONLY" &&
      length(google_sql_database_instance.postgres.settings[0].ip_configuration[0].authorized_networks) == 0
    )
    error_message = "Use PostgreSQL 16, a 10 GB SSD micro instance, and encrypted connections with no authorized direct networks."
  }
}

run "backend_private_by_default" {
  command = plan

  variables {
    backend_image_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    cognito_issuer       = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Example"
    cognito_client_id    = "publicclientid"
    database_running     = false
  }

  assert {
    condition = (
      !google_cloud_run_v2_service.backend[0].invoker_iam_disabled &&
      length(google_cloud_run_v2_service_iam_member.invoker) == 0 &&
      google_cloud_run_v2_service.backend[0].template[0].service_account == "spry-lab9-runtime@spry-lab9-example.iam.gserviceaccount.com" &&
      google_cloud_run_v2_service.backend[0].template[0].scaling[0].min_instance_count == 0 &&
      google_secret_manager_secret_iam_member.runtime_database_url.role == "roles/secretmanager.secretAccessor"
    )
    error_message = "Cloud Run must retain its IAM check, have no default invoker grant, and run as the scoped scale-to-zero runtime account."
  }

  assert {
    condition     = google_sql_database_instance.postgres.settings[0].activation_policy == "NEVER"
    error_message = "The database stop toggle must stop compute."
  }
}

run "deploy_requires_cognito_settings" {
  command = plan

  variables {
    backend_image_digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }

  expect_failures = [google_cloud_run_v2_service.backend]
}

run "public_invocation_rejected" {
  command = plan

  variables {
    cloud_run_invokers = ["allUsers", "allAuthenticatedUsers"]
  }

  expect_failures = [var.cloud_run_invokers]
}
