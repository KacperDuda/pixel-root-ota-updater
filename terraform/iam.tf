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

# Uprawnienia dla Contbuildera do uruchamiania Cloud Run (jeśli Cloud Build ma to robić)
resource "google_project_iam_member" "builder_run_admin" {
  project = var.gcp_project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}
