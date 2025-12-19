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

  # Note: Disable IPv6 if you encounter connectivity issues (e.g. in Cloud Shell)
  # sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
  # sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1
}
