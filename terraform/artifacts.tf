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
