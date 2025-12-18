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
