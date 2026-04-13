terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ──────────────────────────────────────────────
# APIs
# ──────────────────────────────────────────────

resource "google_project_service" "pubsub" {
  service            = "pubsub.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "dataflow" {
  service            = "dataflow.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "logging" {
  service            = "logging.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "compute" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudfunctions" {
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

# ──────────────────────────────────────────────
# GCS Bucket (Dataflow temp + UDF)
# ──────────────────────────────────────────────

locals {
  dataflow_bucket_name = "${var.project_id}-dataflow"
}

resource "google_storage_bucket" "dataflow" {
  name                        = local.dataflow_bucket_name
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  depends_on = [google_project_service.storage]
}

resource "google_storage_bucket_object" "index_fn" {
  name    = "udfs/index_fn.js"
  bucket  = google_storage_bucket.dataflow.name
  content = "function getIndex(document) { return \"${var.elasticsearch_index}\"; }"
}

# The logs@stream.processing ingest pipeline's normalize_for_stream processor
# expands the message JSON string into top-level fields but also tries to write
# message as a field — which conflicts with the logs data stream's field alias.
# Pre-expand the GCP log fields here and drop message so the pipeline doesn't fail.
resource "google_storage_bucket_object" "transform_fn" {
  name   = "udfs/transform_fn.js"
  bucket = google_storage_bucket.dataflow.name
  content = <<-EOF
    function transform(inJson) {
      var doc = JSON.parse(inJson);
      if (doc.message) {
        try {
          var payload = JSON.parse(doc.message);
          var keys = Object.keys(payload);
          for (var i = 0; i < keys.length; i++) {
            doc[keys[i]] = payload[keys[i]];
          }
        } catch (e) {}
        delete doc.message;
      }
      return JSON.stringify(doc);
    }
  EOF
}


# ──────────────────────────────────────────────
# Pub/Sub Topics + Subscription
# ──────────────────────────────────────────────

resource "google_pubsub_topic" "logs_input" {
  name = "logs-input"

  depends_on = [google_project_service.pubsub]
}

resource "google_pubsub_subscription" "logs_input_sub" {
  name  = "logs-input-sub"
  topic = google_pubsub_topic.logs_input.id

  ack_deadline_seconds = 60

  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_topic" "logs_errors" {
  name = "logs-errors"

  depends_on = [google_project_service.pubsub]
}

# ──────────────────────────────────────────────
# Cloud Run Service
# ──────────────────────────────────────────────

resource "google_cloud_run_v2_service" "hello_world" {
  name     = "hello-world"
  location = var.region

  template {
    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"
    }
  }

  depends_on = [google_project_service.run]
}

resource "google_cloud_run_v2_service_iam_member" "hello_world_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.hello_world.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ──────────────────────────────────────────────
# Log Router Sink
# ──────────────────────────────────────────────

resource "google_logging_project_sink" "cloud_run_to_pubsub" {
  name        = "cloud-run-to-pubsub"
  destination = "pubsub.googleapis.com/${google_pubsub_topic.logs_input.id}"
  filter      = "resource.type=\"cloud_run_revision\""

  unique_writer_identity = true

  depends_on = [google_project_service.logging]
}

# ──────────────────────────────────────────────
# IAM
# ──────────────────────────────────────────────

# Allow the log sink's service account to publish to the logs-input topic
resource "google_pubsub_topic_iam_member" "sink_publisher" {
  topic  = google_pubsub_topic.logs_input.id
  role   = "roles/pubsub.publisher"
  member = google_logging_project_sink.cloud_run_to_pubsub.writer_identity
}

# Dataflow default service account
locals {
  dataflow_sa = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

data "google_project" "project" {
  project_id = var.project_id
}

resource "google_storage_bucket_iam_member" "dataflow_gcs" {
  bucket     = google_storage_bucket.dataflow.name
  role       = "roles/storage.objectAdmin"
  member     = local.dataflow_sa
  depends_on = [google_project_service.compute]
}

resource "google_pubsub_subscription_iam_member" "dataflow_subscriber" {
  subscription = google_pubsub_subscription.logs_input_sub.name
  role         = "roles/pubsub.subscriber"
  member       = local.dataflow_sa
  depends_on   = [google_project_service.compute]
}

resource "google_pubsub_topic_iam_member" "dataflow_error_publisher" {
  topic      = google_pubsub_topic.logs_errors.id
  role       = "roles/pubsub.publisher"
  member     = local.dataflow_sa
  depends_on = [google_project_service.compute]
}

# ──────────────────────────────────────────────
# Dataflow Flex Template Job
# ──────────────────────────────────────────────

locals {
  dataflow_region = var.dataflow_region != "" ? var.dataflow_region : var.region
}

resource "google_dataflow_flex_template_job" "pubsub_to_elasticsearch" {
  provider                = google-beta
  name                    = "pubsub-to-elasticsearch"
  container_spec_gcs_path = "gs://dataflow-templates-${local.dataflow_region}/latest/flex/PubSub_to_Elasticsearch_Flex"
  region                  = local.dataflow_region
  enable_streaming_engine = true

  parameters = {
    inputSubscription        = google_pubsub_subscription.logs_input_sub.id
    connectionUrl            = var.elasticsearch_connection_url
    apiKey                   = var.elasticsearch_api_key
    errorOutputTopic         = google_pubsub_topic.logs_errors.id
    javaScriptIndexFnGcsPath            = "gs://${local.dataflow_bucket_name}/${google_storage_bucket_object.index_fn.name}"
    javaScriptIndexFnName               = "getIndex"
    javascriptTextTransformGcsPath      = "gs://${local.dataflow_bucket_name}/${google_storage_bucket_object.transform_fn.name}"
    javascriptTextTransformFunctionName = "transform"
    bulkInsertMethod                    = "CREATE"
    workerMachineType        = "e2-standard-2"
    workerZone               = "${local.dataflow_region}-b"
  }

  skip_wait_on_job_termination = true

  on_delete = "drain"

  depends_on = [
    google_project_service.dataflow,
    google_storage_bucket_object.index_fn,
    google_storage_bucket_object.transform_fn,
    google_pubsub_subscription.logs_input_sub,
    google_pubsub_topic.logs_errors,
  ]
}

# ──────────────────────────────────────────────
# Cloud Function — Log Generator
# ──────────────────────────────────────────────

# Zip the function source and upload to GCS
data "archive_file" "log_generator" {
  type        = "zip"
  source_dir  = "${path.module}/functions/log_generator"
  output_path = "${path.module}/functions/log_generator.zip"
}

resource "google_storage_bucket_object" "log_generator_source" {
  name   = "functions/log_generator-${data.archive_file.log_generator.output_md5}.zip"
  bucket = google_storage_bucket.dataflow.name
  source = data.archive_file.log_generator.output_path
}

resource "google_cloudfunctions2_function" "log_generator" {
  name     = "log-generator"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "log_generator"
    source {
      storage_source {
        bucket = google_storage_bucket.dataflow.name
        object = google_storage_bucket_object.log_generator_source.name
      }
    }
  }

  service_config {
    max_instance_count = 5
    available_memory   = "256M"
    timeout_seconds    = 60
    # Allow unauthenticated browser access
    ingress_settings               = "ALLOW_ALL"
    all_traffic_on_latest_revision = true
  }

  depends_on = [
    google_project_service.cloudfunctions,
    google_project_service.cloudbuild,
    google_project_service.artifactregistry,
    google_storage_bucket_object.log_generator_source,
  ]
}

# Make the function publicly accessible (no auth required for browser)
resource "google_cloud_run_v2_service_iam_member" "log_generator_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.log_generator.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
