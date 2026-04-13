variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "us-central1"
}

variable "elasticsearch_connection_url" {
  description = "Elastic Cloud connection URL (CloudID format, e.g. https://<cluster>.es.<region>.gcp.elastic-cloud.com)"
  type        = string
}

variable "elasticsearch_api_key" {
  description = "Base64-encoded Elasticsearch API key for Dataflow authentication"
  type        = string
  sensitive   = true
}

variable "elasticsearch_index" {
  description = "Elasticsearch index name to write logs to (e.g. logs.ecs, logs.otel, my-custom-index)"
  type        = string
  default     = "logs.ecs"
}

variable "dataflow_region" {
  description = "GCP region for the Dataflow job workers. Can differ from region if us-central1 has capacity issues."
  type        = string
  default     = ""
}
