resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.gcp_region
  repository_id = "${var.github_repo_name}-repo"
  description   = "Docker repository for ${var.github_repo_name}"
  format        = "DOCKER"

  depends_on = [
    google_project_service.artifact_registry_api
  ]
}
