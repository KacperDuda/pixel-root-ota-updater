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
