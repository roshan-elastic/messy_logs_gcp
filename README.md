# GCP Cloud Run Logs → Pub/Sub → Dataflow → Elasticsearch

Streams structured logs from a Cloud Run service and a log-generator Cloud Function through Pub/Sub and Dataflow into an Elasticsearch `logs.ecs` data stream.

## Architecture

```
Cloud Run  ─┐
             ├─→ Cloud Logging → Log Router Sink → Pub/Sub Topic (logs-input)
Cloud Fn   ─┘       → Pub/Sub Subscription → Dataflow (PubSub_to_Elasticsearch_Flex) → Elastic Cloud (logs.ecs)
```

Failed records are routed to a `logs-errors` Pub/Sub topic. A GCS bucket holds Dataflow temp files, UDFs, and the function source.

---

## Prerequisites

### 1. Install gcloud CLI

```bash
brew install --cask google-cloud-sdk
```

### 2. Authenticate with GCP

```bash
gcloud init
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 3. Install Terraform

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

---

## Configuration

Copy the example vars file and fill in your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Then edit `terraform.tfvars`. **This file contains secrets — it is gitignored and must never be committed.**

### Required values

#### `project_id`
Your GCP project ID. Find it in the [GCP Console](https://console.cloud.google.com) or run:
```bash
gcloud projects list
```
```hcl
project_id = "my-gcp-project-123"
```

#### `region`
GCP region to deploy all resources into. `us-central1` is recommended as the Dataflow template is hosted there.
```hcl
region = "us-central1"
```

#### `elasticsearch_connection_url`
The HTTPS endpoint for your Elastic Cloud cluster. Find it in Kibana under **Stack Management → Elasticsearch → Endpoints**, or in the Elastic Cloud console under your deployment's **Connections** tab.
```hcl
elasticsearch_connection_url = "https://<cluster-id>.es.us-central1.gcp.elastic-cloud.com"
```

#### `elasticsearch_api_key`
A base64-encoded Elasticsearch API key used by Dataflow to authenticate writes. Create one in Kibana under **Stack Management → API Keys**, then encode it:
```bash
echo -n "your-key-id:your-api-key-value" | base64
```
Paste the output here:
```hcl
elasticsearch_api_key = "eW91ci1rZXktaWQ6eW91ci1hcGkta2V5LXZhbHVl"
```

### Optional values

#### `elasticsearch_index`
The Elasticsearch data stream to write logs into. Defaults to `logs.ecs` if omitted.

| Value | Description |
|---|---|
| `logs.ecs` | ECS-schema stream — recommended for GCP logs. Preserves all GCP fields. |
| `logs.otel` | OTel-schema stream — remaps fields to OTel conventions. Not recommended for raw GCP logs. |

```hcl
elasticsearch_index = "logs.ecs"
```

#### `dataflow_region`
Override the region used for Dataflow workers only. Useful if your primary region has capacity constraints. Leave commented out to use the same value as `region`.
```hcl
# dataflow_region = "us-east1"
```

---

## How Dataflow works in this pipeline

This pipeline uses the Google-provided **[Pub/Sub to Elasticsearch](https://cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-to-elasticsearch)** Flex Template (`PubSub_to_Elasticsearch_Flex`). It is a managed, streaming Dataflow job that reads messages from a Pub/Sub subscription and writes them to Elasticsearch as documents with no custom Java or Beam code required.

### What the template does by default

Out of the box the template creates a data stream named `logs-gcp.DATASET-NAMESPACE` in Elasticsearch (e.g. `logs-gcp.pubsub-default`), controlled by the `dataset` and `namespace` parameters.

### How this project overrides the target index

Rather than using the default `logs-gcp.*` stream, this project uses the template's **JavaScript Index UDF** feature to route every document to the Elasticsearch data stream of your choice (configured via `elasticsearch_index` in `terraform.tfvars`, defaulting to `logs.ecs`).

The UDF lives at `udfs/index_fn.js` and is uploaded to GCS at deploy time:

```javascript
function getIndex(document) {
  return "logs.ecs"; // or whatever elasticsearch_index is set to
}
```

Terraform wires it into the Dataflow job via two parameters:

```hcl
javaScriptIndexFnGcsPath = "gs://<bucket>/udfs/index_fn.js"
javaScriptIndexFnName    = "getIndex"
```

This tells the template to call `getIndex()` for every document and use the return value as the `_index` for the Elasticsearch bulk request, overriding the default `logs-gcp.*` stream entirely.

### Key template parameters configured

| Parameter | Value | Why |
|---|---|---|
| `inputSubscription` | `logs-input-sub` | The Pub/Sub subscription receiving Cloud Run logs via the Log Router sink |
| `connectionUrl` | Your Elastic Cloud HTTPS endpoint | Where to write documents |
| `apiKey` | Base64-encoded API key | Authentication |
| `errorOutputTopic` | `logs-errors` Pub/Sub topic | Failed records go here instead of being silently dropped |
| `javaScriptIndexFnGcsPath` | GCS path to `index_fn.js` | Points the template at the index UDF |
| `javaScriptIndexFnName` | `getIndex` | The function name to call in the UDF |
| `javascriptTextTransformGcsPath` | GCS path to `transform_fn.js` | Optional document transform UDF |
| `bulkInsertMethod` | `CREATE` | Required for Elasticsearch data streams, which only accept `create` operations |
| `workerMachineType` | `e2-standard-2` | Avoids capacity issues in shared GCP zones |

### Changing the target data stream

To send to a different Elasticsearch data stream, update `elasticsearch_index` in `terraform.tfvars` and re-run `terraform apply`. The UDF file is regenerated and the Dataflow job is replaced automatically.

```hcl
elasticsearch_index = "logs.otel"  # or any valid data stream name
```

> **Note:** Not all data streams accept arbitrary document shapes. See the Gotchas section below before switching away from `logs.ecs`.

---

## Gotchas

### `logs.otel` silently drops documents that don't match OTel schema

`logs.otel` expects data in OpenTelemetry conventions. When documents don't match — for example, raw GCP Cloud Run logs with fields like `httpRequest`, `severity`, `logName`, and `resource.labels.*` — the ingest pipeline routes them to the stream's failure store instead of rejecting them. The bulk API still returns `201 created`, so there is **no visible error**. The documents simply never appear in Discover or the Streams UI.

Specifically, `logs.otel` remaps:
- `message` → `body.text`
- `host.name` → `resource.attributes.host.name`

Any fields outside the expected OTel structure are silently discarded.

**If in doubt, send to `logs.ecs`.** It accepts raw GCP log structure as-is, preserves all fields (`message`, `httpRequest.*`, `severity`, `logName`, `trace`, etc.), and documents reliably arrive in the stream.

---

## Deploy

```bash
terraform init
terraform plan
terraform apply
```

After applying, Terraform prints the URLs for both services:

```
cloud_run_url       = "https://hello-world-<hash>-uc.a.run.app"
log_generator_url   = "https://<region>-<project>.cloudfunctions.net/log-generator"
```

## Generating demo logs

### Option 1 — Log Generator Cloud Function (recommended)

Open the `log_generator_url` in your browser. Each page load:

1. Generates 4–5 structured log events at `INFO`, `WARNING`, and `ERROR` severity — simulating a realistic e-commerce session (user login, product view, cart, checkout/error).
2. Returns an HTML page showing exactly what was logged and the `session_id` shared across all events.
3. Logs flow through Cloud Logging → Pub/Sub → Dataflow → `logs.ecs` and typically arrive in **60–90 seconds**.

Reload the page as many times as you like to generate fresh batches.

> The function runs on Cloud Run infrastructure, so the Log Router sink (which filters on `resource.type="cloud_run_revision"`) automatically picks up its logs — no extra configuration needed.

### Option 2 — Hello World Cloud Run service

Open the `cloud_run_url` in your browser or `curl` it:

```bash
curl "https://hello-world-<hash>-uc.a.run.app/?source=manual-test"
```

Each request generates a standard Cloud Run HTTP request log in `logs.ecs` with fields like `httpRequest.requestUrl`, `httpRequest.status`, `severity`, and `trace`.

---

## Finding logs in Elasticsearch

Query the `logs.ecs` data stream for the last 5 minutes. For logs generated by the Cloud Function, filter on `jsonPayload.source: "log-generator-function"` or search for a specific `jsonPayload.session_id` shown on the function's HTML response page.

---

## Tear down

```bash
terraform destroy
```

---

## File Structure

```
wired-streams-gcp/
├── main.tf                   - all GCP resources (Cloud Run, Cloud Function, Pub/Sub, Dataflow, GCS, IAM)
├── variables.tf              - variable definitions
├── outputs.tf                - useful post-deploy output values
├── terraform.tfvars.example  - template — copy to terraform.tfvars and fill in secrets
├── terraform.tfvars          - your real values (gitignored, never commit)
├── functions/
│   └── log_generator/
│       ├── main.py           - HTTP Cloud Function: generates structured demo log events
│       └── requirements.txt  - Python dependencies (functions-framework)
└── udfs/
    └── index_fn.js           - Dataflow UDF: routes all documents to the configured index
```
