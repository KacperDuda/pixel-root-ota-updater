resource "google_storage_bucket" "release_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-release"
  location      = "EU"
  force_destroy = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "ota_cache_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-ota-cache"
  location      = "EU"
  force_destroy = true 
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition {
      age = 30 # Clean cache older than 30 days
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "release_bucket_public_viewer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_iam_member" "builder_release_bucket_writer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectAdmin" 
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_storage_bucket_iam_member" "builder_cache_bucket_writer" {
  bucket = google_storage_bucket.ota_cache_bucket.name
  role   = "roles/storage.objectAdmin" 
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

resource "google_storage_bucket" "web_flasher_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-web-flasher"
  location      = "EU"
  force_destroy = true
  
  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }
  
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "web_flasher_public" {
  bucket = google_storage_bucket.web_flasher_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_iam_member" "builder_web_writer" {
  bucket = google_storage_bucket.web_flasher_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}
