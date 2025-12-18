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

  # UWAGA: Jeśli napotkasz błędy sieciowe typu "connect: cannot assign requested address"
  # podczas uruchamiania `terraform plan` lub `apply`, szczególnie w środowiskach takich jak Google Cloud Shell,
  # może to być spowodowane problemami z łącznością IPv6.
  #
  # Aby to naprawić, spróbuj wyłączyć IPv6 w swoim terminalu przed uruchomieniem Terraform, używając poleceń:
  # sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
  # sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1
}
