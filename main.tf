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
# Note: Manually upload private key via gcloud/Console

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
    _DEVICE_CODENAME  = "frankel" 
    _WEB_BUCKET_NAME  = google_storage_bucket.web_flasher_bucket.name
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