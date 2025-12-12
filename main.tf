# Zmienne konfiguracyjne
variable "gcp_project_id" {
  description = "Twoje ID projektu w Google Cloud."
  type        = string
  default     = "sabre-gcp-project"
}

variable "gcp_region" {
  description = "Region GCP do wdrożenia zasobów."
  type        = string
  default     = "europe-central2" # Warszawa
}

variable "github_owner" {
  description = "Właściciel repozytorium na GitHubie."
  type        = string
  default     = "KacperDuda"
}

variable "github_repo_name" {
  description = "Nazwa repozytorium na GitHubie."
  type        = string
  default     = "pixel-root-ota-updater"
}

# Konfiguracja Terraform i Providera
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# 1. Bucket na gotowe obrazy
resource "google_storage_bucket" "release_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-release" # Dynamiczna nazwa bucketa
  location      = "EU"
  force_destroy = true # Umożliwia usunięcie bucketa, nawet jeśli zawiera obiekty
  uniform_bucket_level_access = true
}

# 2. Bucket na Cache (Oryginalne pliki OTA)
resource "google_storage_bucket" "ota_cache_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-ota-cache"
  location      = "EU"
  force_destroy = true 
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition {
      age = 30 # Czyść cache starszy niż 30 dni
    }
    action {
      type = "Delete"
    }
  }
}

# Uprawnienia publiczne do odczytu (dla klientów OTA)
resource "google_storage_bucket_iam_member" "release_bucket_public_viewer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# 3. Sekrety w Secret Manager
resource "google_secret_manager_secret" "avb_private_key" {
  secret_id = "avb-private-key"
  replication {
    auto {}
  }
}

# Dodanie wartości (wersji) do sekretu
resource "google_secret_manager_secret_version" "avb_private_key_version" {
  secret      = google_secret_manager_secret.avb_private_key.id
  secret_data = file("${path.module}/cyber_rsa4096_private.pem") # Wczytanie klucza z pliku
}



# 4. Service Account dla Buildera
resource "google_service_account" "builder_sa" {
  account_id   = "${var.github_repo_name}-builder" # Dynamiczna nazwa konta
  display_name = "Cloud Build Service Account for ${var.github_repo_name}"
}

# Nadanie uprawnień do pisania logów (Wymagane, aby widzieć output w Cloud Console)
resource "google_project_iam_member" "builder_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

# Nadanie uprawnień dla Service Account do Release Bucketa
resource "google_storage_bucket_iam_member" "builder_release_bucket_writer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectAdmin" 
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

# Nadanie uprawnień dla Service Account do Cache Bucketa (zapis/odczyt)
resource "google_storage_bucket_iam_member" "builder_cache_bucket_writer" {
  bucket = google_storage_bucket.ota_cache_bucket.name
  role   = "roles/storage.objectAdmin" 
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

# Nadanie uprawnień do odczytu konkretnych sekretów
resource "google_secret_manager_secret_iam_member" "builder_private_key_accessor" {
  project   = google_secret_manager_secret.avb_private_key.project
  secret_id = google_secret_manager_secret.avb_private_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 3b. API & Uprawnienia do GCR / Artifact Registry
# Nowe projekty GCP używają Artifact Registry zamiast starego GCR, nawet pod adresem gcr.io
resource "google_project_service" "container_registry_api" {
  service = "containerregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifact_registry_api" {
  service = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_scheduler_api" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_run_api" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

# Cloud Build SA potrzebuje Storage Admin (dla starego GCR)
resource "google_project_iam_member" "builder_gcr_admin" {
  project = var.gcp_project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

# ...ORAZ Artifact Registry Admin (Wymagane do utworzenia repozytorium przy pierwszym pushu)
resource "google_project_iam_member" "builder_ar_admin" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 3c. ActAs Permission (Kluczowe dla Cloud Run)
# Cloud Build używa tego konta (builder_sa) do wykonania 'gcloud run jobs update'.
# W specyfikacji Joba (google_cloud_run_v2_job) też podajemy 'service_account = builder_sa'.
# Aby builder mógł "przypisać" to konto do Joba, musi mieć uprawnienie 'actAs' na samym sobie.
resource "google_service_account_iam_member" "builder_act_as_self" {
  service_account_id = google_service_account.builder_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 5. Repozytorium Docker w Artifact Registry
resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.gcp_region
  repository_id = "${var.github_repo_name}-repo" # Nazwa repozytorium
  description   = "Docker repository for ${var.github_repo_name}"
  format        = "DOCKER"

  # Upewnij się, że API jest włączone przed próbą utworzenia repozytorium
  depends_on = [
    google_project_service.artifact_registry_api
  ]
}

# 5. Cloud Build Trigger - uruchamia budowanie po pushu do `main`
resource "google_cloudbuild_trigger" "push_to_main_trigger" {
  name     = "${var.github_repo_name}-push-to-main"
  location = "global" # Triggery Cloud Build są zasobem globalnym
  filename = "cloudbuild.yaml" # Wskazanie pliku konfiguracyjnego w repozytorium
  service_account = google_service_account.builder_sa.id

  # Połączenie z repozytorium GitHub i definicja zdarzenia (push do main)
  github {
    owner = var.github_owner
    name  = var.github_repo_name
    push {
      branch = "^main$"
    }
  }

  substitutions = {
    _BUCKET_NAME      = google_storage_bucket.release_bucket.name
    _CACHE_BUCKET_NAME = google_storage_bucket.ota_cache_bucket.name
    _DOCKER_REPO_URL  = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.docker_repo.repository_id}"
    _DEVICE_CODENAME  = "frankel"
    _WEB_BUCKET_NAME  = google_storage_bucket.web_flasher_bucket.name
    _REGION           = var.gcp_region
    _REPO_NAME        = var.github_repo_name
  }
}

# 6. Web Flasher Hosting
resource "google_storage_bucket" "web_flasher_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-web-flasher"
  location      = "EU"
  force_destroy = true
  
  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }
  
  uniform_bucket_level_access = true
}

# Publiczny dostęp do strony WWW
resource "google_storage_bucket_iam_member" "web_flasher_public" {
  bucket = google_storage_bucket.web_flasher_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Uprawnienia dla Buildera do deployowania strony
resource "google_storage_bucket_iam_member" "builder_web_writer" {
  bucket = google_storage_bucket.web_flasher_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

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

# Uprawnienia dla Contbuildera do uruchamiania Cloud Run (jeśli Cloud Build ma to robić)
resource "google_project_iam_member" "builder_run_admin" {
  project = var.gcp_project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

# Service Account ActAs (wymagane, by Cloud Build mógł zlecić uruchomienie Joba jako inny SA - 'builder_sa')
# W tym przypadku Cloud Build działa jako 'builder_sa', a Job też jako 'builder_sa', więc ActAs jest implicit,
# ale warto dodać explicite jeśli builder triggera używa domyślnego konta Cloud Build.
# Tutaj trigger używa `service_account = google_service_account.builder_sa.id`, więc jest OK. 