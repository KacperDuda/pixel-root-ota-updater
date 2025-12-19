resource "google_cloudbuild_trigger" "push_to_main_trigger" {
  name     = "${var.github_repo_name}-push-to-main"
  location = "global"
  filename = "cloudbuild.yaml"
  service_account = google_service_account.builder_sa.id

  github {
    owner = var.github_owner
    name  = var.github_repo_name
    push {
      branch = "^main$"
    }
  }

  substitutions = {
    _BUCKET_NAME       = google_storage_bucket.release_bucket.name
    _CACHE_BUCKET_NAME = google_storage_bucket.ota_cache_bucket.name
    _DOCKER_REPO_URL   = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.docker_repo.repository_id}"
    _DEVICE_CODENAME   = "frankel"
    _WEB_BUCKET_NAME   = google_storage_bucket.web_flasher_bucket.name
    _REGION            = var.gcp_region
    _REPO_NAME         = var.github_repo_name
  }
}
