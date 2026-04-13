# GCP Cloud Run Logs → Pub/Sub → Dataflow → Elasticsearch

Streams structured logs from a Cloud Run service through Pub/Sub and Dataflow into an Elasticsearch `logs.ecs` data stream.

## Architecture

```
Cloud Run → Cloud Logging → Log Router Sink → Pub/Sub Topic (logs-input)
  → Pub/Sub Subscription → Dataflow (PubSub_to_Elasticsearch_Flex) → Elastic Cloud (logs.ecs)
```

Failed records are routed to a `logs-errors` Pub/Sub topic. A GCS bucket holds Dataflow temp files and the index UDF.

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

## Deploy

```bash
terraform init
terraform plan
terraform apply
```

## Tear down

```bash
terraform destroy
```

---

## File Structure

```
wired-streams-gcp/
├── main.tf                   - all GCP resources (Cloud Run, Pub/Sub, Dataflow, GCS, IAM)
├── variables.tf              - variable definitions
├── outputs.tf                - useful post-deploy output values
├── terraform.tfvars.example  - template — copy to terraform.tfvars and fill in secrets
├── terraform.tfvars          - your real values (gitignored, never commit)
└── udfs/
    └── index_fn.js           - Dataflow UDF: routes all documents to the configured index
```
