# 3. Sekrety w Secret Manager
resource "google_secret_manager_secret" "avb_private_key" {
  secret_id = "avb-private-key"
  replication {
    auto {}
  }
}

# Dodanie wartości (wersji) do sekretu
resource "google_secret_manager_secret_version" "avb_private_key_version" {
  secret      = google_secret_manager_secret.avb_private_key.id
  # Zmieniono ścieżkę na ../ aby wskazywała poziom wyżej (root projektu), gdzie zwykle leży klucz
  secret_data = file("${path.module}/../cyber_rsa4096_private.pem") 
}

# Nadanie uprawnień do odczytu konkretnych sekretów
resource "google_secret_manager_secret_iam_member" "builder_private_key_accessor" {
  project   = google_secret_manager_secret.avb_private_key.project
  secret_id = google_secret_manager_secret.avb_private_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.builder_sa.email}"
}
