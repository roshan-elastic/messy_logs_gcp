# GCP Cloud Run Logs → Pub/Sub → Dataflow → Elasticsearch

Streams structured logs from a Cloud Run service through Pub/Sub and Dataflow into an Elasticsearch `logs.ecs` index.

## Architecture

```
Cloud Run → Cloud Logging → Log Router Sink → Pub/Sub Topic (logs-input)
  → Pub/Sub Subscription → Dataflow (PubSub_to_Elasticsearch_Flex) → Elastic Cloud (logs.ecs)
```

Failed records are routed to a `logs-errors` Pub/Sub topic. A GCS bucket holds Dataflow temp files and the index function UDF.

---

## Prerequisites

### 1. Install gcloud CLI (macOS)

Install the Google Cloud SDK via Homebrew:

```bash
brew install --cask google-cloud-sdk
```

Verify the installation:

```bash
gcloud --version
```

### 2. Authenticate and configure your project

Initialize gcloud and select your GCP project:

```bash
gcloud init
```

Authenticate application default credentials (required by the Terraform Google provider):

```bash
gcloud auth application-default login
```

Set your active project:

```bash
gcloud config set project YOUR_PROJECT_ID
```

---

## Usage

1. Copy the example tfvars file and fill in your values:

   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Initialize Terraform:

   ```bash
   terraform init
   ```

3. Review the plan:

   ```bash
   terraform plan -var-file=terraform.tfvars
   ```

4. Apply:

   ```bash
   terraform apply -var-file=terraform.tfvars
   ```

---

## File Structure

```
wired-streams-gcp/
├── main.tf                   - all GCP resources
├── variables.tf              - project_id, region, ES credentials, etc.
├── outputs.tf                - useful output values
├── terraform.tfvars.example  - template for user values (no secrets)
└── udfs/
    └── index_fn.js           - JS UDF: always returns "logs.ecs"
```

## Key Variables

| Variable | Description |
|---|---|
| `project_id` | GCP project ID |
| `region` | GCP region (default: `us-central1`) |
| `elasticsearch_connection_url` | Elastic Cloud CloudID format |
| `elasticsearch_api_key` | Base64-encoded API key (sensitive) |
