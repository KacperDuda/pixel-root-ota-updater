resource "google_service_account" "builder_sa" {
  account_id   = "${var.github_repo_name}-builder"
  display_name = "Cloud Build Service Account for ${var.github_repo_name}"
}

resource "google_project_iam_member" "builder_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_project_iam_member" "builder_gcr_admin" {
  project = var.gcp_project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_project_iam_member" "builder_ar_admin" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

# Allows Cloud Build to impersonate itself for Cloud Run updates (gcloud run jobs update).
resource "google_service_account_iam_member" "builder_act_as_self" {
  service_account_id = google_service_account.builder_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_project_iam_member" "builder_run_admin" {
  project = var.gcp_project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_project_iam_member" "builder_metric_writer" {
  project = var.gcp_project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}
