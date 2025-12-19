resource "google_cloud_run_v2_job" "automator_job" {
  name     = "${var.github_repo_name}-job"
  location = var.gcp_region

  depends_on = [
    google_service_account_iam_member.builder_act_as_self,
    google_artifact_registry_repository.docker_repo,
    google_secret_manager_secret_version.avb_private_key_version
  ]

  template {
    template {
      service_account = google_service_account.builder_sa.email
      timeout         = "3600s"

      containers {
        # Initial placeholder image; updated by Cloud Build.
        image = "gcr.io/google-containers/pause"
        
        env {
          name  = "_DEVICE_CODENAME"
          value = "frankel"
        }
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.gcp_project_id
        }
        env {
          name  = "_BUCKET_NAME"
          value = google_storage_bucket.release_bucket.name
        }
        env {
          name  = "CACHE_BUCKET_NAME"
          value = google_storage_bucket.ota_cache_bucket.name
        }

        volume_mounts {
          name       = "avb-key-volume"
          mount_path = "/app/secrets"
        }

        resources {
          limits = {
            memory = "16Gi"
            cpu    = "4"
          }
        }
      }

      volumes {
        name = "avb-key-volume"
        secret {
          secret = google_secret_manager_secret.avb_private_key.secret_id
          items {
            version = "latest"
            path    = "cyber_rsa4096_private.pem"
          }
        }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "daily_runner" {
  name        = "${var.github_repo_name}-daily-cron"
  description = "Triggers Pixel Automator Cloud Run Job every 24h"
  schedule    = "0 3 * * *"
  time_zone   = "Europe/Warsaw"
  region      = var.gcp_region

  depends_on = [
    google_project_service.cloud_scheduler_api,
  ]

  http_target {
    uri         = "https://${var.gcp_region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.gcp_project_id}/jobs/${google_cloud_run_v2_job.automator_job.name}:run"
    http_method = "POST"
    
    oauth_token {
      service_account_email = google_service_account.builder_sa.email
    }
  }
}
