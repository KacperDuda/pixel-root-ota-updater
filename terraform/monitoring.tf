resource "google_monitoring_notification_channel" "email_alert_channel" {
  display_name = "Pixel Automator Alert Channel"
  type         = "email"
  labels = {
    email_address = var.alert_email_address
  }
}

resource "google_monitoring_alert_policy" "pixel_build_failure_policy" {
  display_name = "Pixel Build Failure Alert"
  combiner     = "OR"
  conditions {
    display_name = "Build Failure Metric Present"
    condition_threshold {
      filter     = "metric.type=\"custom.googleapis.com/pixel_automator/build_failures\" AND resource.type=\"global\""
      duration   = "60s" # Aggregate over 1 minute
      comparison = "COMPARISON_GT"
      threshold_value = 0 # If count > 0, alert
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_COUNT"
        cross_series_reducer = "REDUCE_SUM" # Sum across all labels (e.g. devices)
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email_alert_channel.name]
  
  alert_strategy {
    auto_close = "1800s" # Auto close the incident after 30 mins
  }
}
