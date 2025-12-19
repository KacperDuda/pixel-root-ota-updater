variable "gcp_project_id" {
  description = "Your Google Cloud Project ID."
  type        = string
  default     = "sabre-gcp-project"
}

variable "gcp_region" {
  description = "GCP Region for resources."
  type        = string
  default     = "europe-central2"
}

variable "github_owner" {
  description = "GitHub Repository Owner."
  type        = string
  default     = "KacperDuda"
}

variable "github_repo_name" {
  description = "GitHub Repository Name."
  type        = string
  default     = "pixel-root-ota-updater"
}
