# Konfiguracja Providera
provider "google" {
  project = "twoj-project-id" # Zmień na swoje ID projektu
  region  = "europe-central2" # Warszawa
}

# 1. Bucket na obrazy OTA, klucze publiczne i pliki JSON
# Będzie publiczny do odczytu (dla Custota), ale zapis tylko dla Buildera
resource "google_storage_bucket" "ota_bucket" {
  name          = "pixel-ota-frankel-release"
  location      = "EU"
  force_destroy = false

  uniform_bucket_level_access = true

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
}

# Uprawnienia publiczne do odczytu (dla klientów OTA)
resource "google_storage_bucket_iam_member" "public_read" {
  bucket = google_storage_bucket.ota_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# 2. Secret Manager - tu trzymamy hasło do klucza prywatnego AVB
# Klucz prywatny .pk8 może być też w SM, albo na bezpiecznym buckecie
resource "google_secret_manager_secret" "avb_passphrase" {
  secret_id = "avb-key-passphrase"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "avb_passphrase_val" {
  secret      = google_secret_manager_secret.avb_passphrase.id
  secret_data = "bardzo_tajne_haslo_do_klucza_pk8" # Zmień lub ustaw ręcznie w konsoli
}

# 3. Service Account dla Buildera
resource "google_service_account" "builder_sa" {
  account_id   = "ota-builder-sa"
  display_name = "OTA Builder Service Account"
}

# Nadanie uprawnień SA do Bucketa (zapis) i Secret Managera (odczyt hasła)
resource "google_storage_bucket_iam_member" "builder_storage_admin" {
  bucket = google_storage_bucket.ota_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "builder_secret_accessor" {
  secret_id = google_secret_manager_secret.avb_passphrase.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 4. Cloud Run Job - Wykonawca zadania
resource "google_cloud_run_v2_job" "ota_builder" {
  name     = "pixel-ota-builder"
  location = "europe-central2"

  template {
    template {
      service_account = google_service_account.builder_sa.email
      
      containers {
        image = "gcr.io/twoj-project-id/pixel-builder:latest" # Zbudowany z Dockerfile
        
        resources {
          limits = {
            cpu    = "4"   # Patchowanie i pakowanie wymaga mocy
            memory = "8Gi" # Obrazy Pixela są duże
          }
        }

        env {
          name  = "BUCKET_NAME"
          value = google_storage_bucket.ota_bucket.name
        }
        
        env {
          name  = "DEVICE_CODENAME"
          value = "frankel"
        }

        env {
          name = "AVB_PASSPHRASE"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.avb_passphrase.name
              version = "latest"
            }
          }
        }
      }
    }
  }
}

# 5. Cloud Scheduler - Uruchamia Job co 24h
resource "google_cloud_scheduler_job" "daily_build_trigger" {
  name             = "trigger-ota-build"
  description      = "Codzienne sprawdzanie aktualizacji Pixela"
  schedule         = "0 3 * * *" # 3:00 rano
  time_zone        = "Europe/Warsaw"
  attempt_deadline = "320s"

  http_target {
    http_method = "POST"
    uri         = "https://europe-central2-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/pixel-ota-builder:run"
    
    oauth_token {
      service_account_email = google_service_account.builder_sa.email
    }
  }
}