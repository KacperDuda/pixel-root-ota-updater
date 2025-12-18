# 7. Cloud Run Job - Automator Logic
# To zadanie będzie uruchamiane cyklicznie przez Scheduler oraz ręcznie przez Cloud Build (po update)
resource "google_cloud_run_v2_job" "automator_job" {
  name     = "${var.github_repo_name}-job"
  location = var.gcp_region

  depends_on = [
    google_service_account_iam_member.builder_act_as_self,
    google_artifact_registry_repository.docker_repo,
    google_secret_manager_secret_version.avb_private_key_version # Upewnij się, że wersja sekretu istnieje
  ]

  template {
    template {
      service_account = google_service_account.builder_sa.email
      timeout         = "3600s" # 1h timeout, same as Cloud Build

      containers {
        # Przy pierwszym uruchomieniu używamy obrazu "placeholder".
        # Cloud Build (w cloudbuild.yaml) jest odpowiedzialny za aktualizację tego zadania, aby używało właściwego obrazu po jego zbudowaniu.
        image = "gcr.io/google-containers/pause"
        
        env {
          name = "_DEVICE_CODENAME"
          value = "frankel"
        }
        env {
          name = "_BUCKET_NAME"
          value = google_storage_bucket.release_bucket.name
        }
        env {
          name = "CACHE_BUCKET_NAME"
          value = google_storage_bucket.ota_cache_bucket.name
        }

        # Montowanie sekretu (klucz AVB)
        volume_mounts {
          name       = "avb-key-volume"
          mount_path = "/app/secrets"
        }

        # Zasoby (RAM/CPU) - Zwiększone dla OTA Patching
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

# 8. Cloud Scheduler - Trigger 24h
resource "google_cloud_scheduler_job" "daily_runner" {
  name        = "${var.github_repo_name}-daily-cron"
  description = "Triggers Pixel Automator Cloud Run Job every 24h"
  schedule    = "0 3 * * *" # 3:00 AM daily
  time_zone   = "Europe/Warsaw"
  region      = var.gcp_region

  depends_on = [
    google_project_service.cloud_scheduler_api,
  ]

  http_target {
    # Cloud Run Job invocation
    uri         = "https://${var.gcp_region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.gcp_project_id}/jobs/${google_cloud_run_v2_job.automator_job.name}:run"
    http_method = "POST"
    
    oauth_token {
      service_account_email = google_service_account.builder_sa.email
    }
  }
}
