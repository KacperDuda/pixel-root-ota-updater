terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "sabre-gcp-project"
  region  = "us-central1"
}

# 1. Bucket to store the final images and the "last_seen_hash" file
resource "google_storage_bucket" "rom_bucket" {
  name          = "pixel10-frankel-builds"
  location      = "US"
  force_destroy = false
  uniform_bucket_level_access = true
}

# 2. Service Account for the Builder
resource "google_service_account" "builder_sa" {
  account_id   = "pixel-kernel-builder"
  display_name = "Pixel Kernel Builder SA"
}

# Grant permissions to Storage and Secret Manager
resource "google_project_iam_member" "storage_admin" {
  project = "your-gcp-project-id"
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = "your-gcp-project-id"
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 3. Cloud Build Trigger (Connected to your GitHub)
resource "google_cloudbuild_trigger" "hourly_check" {
  name = "pixel10-update-check"
  
  # Link to your repo
  github {
    owner = "your-github-username"
    name  = "your-repo-name"
    push {
      branch = "^main$"
    }
  }

  # We use a specific file to define the build steps
  filename = "cloudbuild.yaml"
  
  service_account = google_service_account.builder_sa.id
  
  # We don't want this to run on git push, only on schedule, 
  # but Cloud Build requires an event. We will trigger this manually via Scheduler.
  disabled = true 
}

# 4. Scheduler to trigger the build every hour
resource "google_cloud_scheduler_job" "trigger_build" {
  name        = "trigger-pixel-build"
  description = "Triggers Cloud Build to check for Pixel updates"
  schedule    = "0 * * * *" # Every hour
  time_zone   = "Etc/UTC"

  http_target {
    http_method = "POST"
    uri         = "https://cloudbuild.googleapis.com/v1/projects/your-gcp-project-id/triggers/${google_cloudbuild_trigger.hourly_check.trigger_id}:run"
    
    oauth_token {
      service_account_email = google_service_account.builder_sa.email
    }
  }
}