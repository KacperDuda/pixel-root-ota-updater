# 1. Bucket na gotowe obrazy
resource "google_storage_bucket" "release_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-release" # Dynamiczna nazwa bucketa
  location      = "EU"
  force_destroy = true # Umożliwia usunięcie bucketa, nawet jeśli zawiera obiekty
  uniform_bucket_level_access = true
}

# 2. Bucket na Cache (Oryginalne pliki OTA)
resource "google_storage_bucket" "ota_cache_bucket" {
  name          = "${var.gcp_project_id}-${var.github_repo_name}-ota-cache"
  location      = "EU"
  force_destroy = true 
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition {
      age = 30 # Czyść cache starszy niż 30 dni
    }
    action {
      type = "Delete"
    }
  }
}

# Uprawnienia publiczne do odczytu (dla klientów OTA)
resource "google_storage_bucket_iam_member" "release_bucket_public_viewer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Nadanie uprawnień dla Service Account do Release Bucketa
resource "google_storage_bucket_iam_member" "builder_release_bucket_writer" {
  bucket = google_storage_bucket.release_bucket.name
  role   = "roles/storage.objectAdmin" 
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

# Nadanie uprawnień dla Service Account do Cache Bucketa (zapis/odczyt)
resource "google_storage_bucket_iam_member" "builder_cache_bucket_writer" {
  bucket = google_storage_bucket.ota_cache_bucket.name
  role   = "roles/storage.objectAdmin" 
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}

# 6. Web Flasher Hosting
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

# Publiczny dostęp do strony WWW
resource "google_storage_bucket_iam_member" "web_flasher_public" {
  bucket = google_storage_bucket.web_flasher_bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Uprawnienia dla Buildera do deployowania strony
resource "google_storage_bucket_iam_member" "builder_web_writer" {
  bucket = google_storage_bucket.web_flasher_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.builder_sa.email}"
}
