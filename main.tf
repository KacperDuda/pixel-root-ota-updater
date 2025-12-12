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

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Konfiguracja Providera
provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# 1. Bucket na gotowe obrazy i pliki tymczasowe
resource "google_storage_bucket" "release_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-release" # Dynamiczna nazwa bucketa
  location      = "EU"
  force_destroy = true # Umożliwia usunięcie bucketa, nawet jeśli zawiera obiekty
  uniform_bucket_level_access = true
}

# Uprawnienia publiczne do odczytu (dla klientów OTA)
resource "google_storage_bucket_iam_member" "release_bucket_public_viewer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# 2. Secret Manager na hasło do klucza prywatnego AVB
resource "google_secret_manager_secret" "avb_passphrase" {
  secret_id = "avb-key-passphrase"
  replication {
    auto {}
  }
}
resource "google_secret_manager_secret_version" "avb_passphrase_initial_version" {
  secret      = google_secret_manager_secret.avb_passphrase.id
  secret_data = "bardzo_tajne_haslo_do_klucza_pk8" # Zmień lub ustaw ręcznie w konsoli
  # WAŻNE: Nigdy nie trzymaj prawdziwych haseł w kodzie! Użyj zmiennych lub ustaw ręcznie.
  lifecycle {
    prevent_destroy = true
  }
}

# 3. Service Account dla Buildera
resource "google_service_account" "builder_sa" {
  account_id   = "${var.github_repo_name}-builder" # Dynamiczna nazwa konta
  display_name = "Cloud Build Service Account for ${var.github_repo_name}"
}

# Nadanie uprawnień dla Service Account na poziomie projektu
resource "google_project_iam_member" "builder_storage_admin" {
  project = var.gcp_project_id
  role    = "roles/storage.admin" # Pełne uprawnienia do GCS w projekcie
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}
resource "google_project_iam_member" "builder_secret_accessor" {
  project   = var.gcp_project_id
  role      = "roles/secretmanager.secretAccessor" # Dostęp do wszystkich sekretów
  member    = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 4. Cloud Build Trigger - uruchamia budowanie po pushu do `main`
resource "google_cloudbuild_trigger" "push_to_main_trigger" {
  name     = "${var.github_repo_name}-push-to-main"
  location = "global" # Triggery Cloud Build są zasobem globalnym
  github {
    owner = var.github_owner
    name  = var.github_repo_name
    push {
      branch = "^main$"
    }
  }
  # Plik z definicją kroków budowania w Twoim repozytorium
  filename        = "cloudbuild.yaml"
  service_account = google_service_account.builder_sa.id
}