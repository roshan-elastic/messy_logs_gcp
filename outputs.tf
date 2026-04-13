output "cloud_run_url" {
  description = "Public URL of the hello-world Cloud Run service"
  value       = google_cloud_run_v2_service.hello_world.uri
}

output "gcs_bucket_name" {
  description = "Name of the GCS bucket used for Dataflow temp files and the UDF"
  value       = google_storage_bucket.dataflow.name
}

output "gcs_bucket_url" {
  description = "Console URL for the GCS bucket"
  value       = "https://console.cloud.google.com/storage/browser/${google_storage_bucket.dataflow.name}"
}

output "pubsub_input_topic" {
  description = "Full resource name of the logs-input Pub/Sub topic"
  value       = google_pubsub_topic.logs_input.id
}

output "pubsub_input_subscription" {
  description = "Full resource name of the logs-input-sub Pub/Sub subscription"
  value       = google_pubsub_subscription.logs_input_sub.id
}

output "pubsub_errors_topic" {
  description = "Full resource name of the logs-errors Pub/Sub topic"
  value       = google_pubsub_topic.logs_errors.id
}

output "log_sink_name" {
  description = "Name of the Cloud Logging sink that routes Cloud Run logs to Pub/Sub"
  value       = google_logging_project_sink.cloud_run_to_pubsub.name
}

output "log_sink_writer_identity" {
  description = "Service account identity used by the log sink to publish messages"
  value       = google_logging_project_sink.cloud_run_to_pubsub.writer_identity
}

output "dataflow_job_name" {
  description = "Name of the Dataflow Flex Template job"
  value       = google_dataflow_flex_template_job.pubsub_to_elasticsearch.name
}

output "dataflow_job_url" {
  description = "Console URL for the Dataflow job"
  value       = "https://console.cloud.google.com/dataflow/jobs/${var.region}/${google_dataflow_flex_template_job.pubsub_to_elasticsearch.job_id}?project=${var.project_id}"
}

output "udf_gcs_path" {
  description = "GCS path to the index function UDF used by the Dataflow job"
  value       = "gs://${google_storage_bucket.dataflow.name}/${google_storage_bucket_object.index_fn.name}"
}
