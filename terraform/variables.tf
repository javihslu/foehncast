variable "project_id" {
  description = "GCP project ID for FoehnCast resources."
  type        = string
}

variable "region" {
  description = "Primary GCP region for deployed resources."
  type        = string
  default     = "europe-west6"
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository name for container images."
  type        = string
  default     = "foehncast-docker"
}

variable "artifact_bucket_name" {
  description = "GCS bucket for artifacts and Terraform-managed storage assets."
  type        = string
}

variable "bigquery_dataset_id" {
  description = "BigQuery dataset ID for curated feature data."
  type        = string
  default     = "foehncast"
}

variable "bigquery_location" {
  description = "BigQuery location for the feature dataset."
  type        = string
  default     = "europe-west6"
}

variable "bigquery_feature_table_id" {
  description = "BigQuery table ID for curated feature rows."
  type        = string
  default     = "forecast_features"
}

variable "feast_online_store_location" {
  description = "Location for the Firestore Datastore-mode database backing Feast online serving."
  type        = string
  default     = "europe-west6"
}

variable "feast_online_store_database_name" {
  description = "Database name for the Firestore Datastore-mode database backing Feast online serving."
  type        = string
  default     = "feast-online"
}

variable "provision_cloud_run_service" {
  description = "Whether Terraform should create the Cloud Run inference service."
  type        = bool
  default     = false
}

variable "cloud_run_service_name" {
  description = "Cloud Run service name for the inference API."
  type        = string
  default     = "foehncast-serve"
}

variable "cloud_run_image" {
  description = "Container image URI for the Cloud Run inference service. Leave empty to use the default Artifact Registry path."
  type        = string
  default     = ""
}

variable "cloud_run_container_port" {
  description = "Container port exposed by the Cloud Run service."
  type        = number
  default     = 8080
}

variable "cloud_run_allow_unauthenticated" {
  description = "Whether the Cloud Run service should allow unauthenticated requests."
  type        = bool
  default     = true
}

variable "cloud_run_min_instance_count" {
  description = "Minimum number of Cloud Run instances kept warm."
  type        = number
  default     = 0
}

variable "cloud_run_max_instance_count" {
  description = "Maximum number of Cloud Run instances."
  type        = number
  default     = 2
}

variable "cloud_run_cpu" {
  description = "CPU limit for the Cloud Run container."
  type        = string
  default     = "1"
}

variable "cloud_run_memory" {
  description = "Memory limit for the Cloud Run container."
  type        = string
  default     = "1Gi"
}

variable "mlflow_tracking_uri" {
  description = "Reachable MLflow tracking URI for the Cloud Run inference service."
  type        = string
  default     = ""

  validation {
    condition = (
      !var.provision_cloud_run_service ||
      var.provision_cloud_run_mlflow ||
      trimspace(var.mlflow_tracking_uri) != ""
    )
    error_message = "Set mlflow_tracking_uri when provision_cloud_run_service is true and provision_cloud_run_mlflow is false."
  }
}

variable "cloud_run_env_vars" {
  description = "Additional environment variables for the Cloud Run inference service."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Cloud SQL + Cloud Run — MLflow
# ---------------------------------------------------------------------------

variable "provision_cloud_run_mlflow" {
  description = "Whether Terraform should create a Cloud SQL instance and Cloud Run MLflow tracking server."
  type        = bool
  default     = false
}

variable "cloud_run_mlflow_service_name" {
  description = "Cloud Run service name for the MLflow tracking server."
  type        = string
  default     = "foehncast-mlflow"
}

variable "cloud_run_mlflow_image" {
  description = "Container image URI for the Cloud Run MLflow service. Leave empty to use the default Artifact Registry path."
  type        = string
  default     = ""
}

variable "cloud_sql_mlflow_instance_name" {
  description = "Cloud SQL instance name for the MLflow PostgreSQL backend."
  type        = string
  default     = "foehncast-mlflow"
}

variable "provision_cloud_run_ui" {
  description = "Whether Terraform should create a Cloud Run UI (Streamlit) service."
  type        = bool
  default     = false
}

variable "cloud_run_ui_service_name" {
  description = "Cloud Run service name for the Streamlit UI."
  type        = string
  default     = "foehncast-ui"
}

variable "cloud_run_ui_image" {
  description = "Container image URI for the Cloud Run UI service. Leave empty to use the default Artifact Registry path."
  type        = string
  default     = ""
}

variable "cloud_run_ui_prometheus_url" {
  description = "Prometheus-compatible query URL for server-side metric lookups from the Streamlit UI."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Cloud Workflows — Serverless pipeline orchestration
# ---------------------------------------------------------------------------

variable "provision_cloud_workflows" {
  description = "Whether Terraform should create Cloud Run Jobs, a Cloud Workflow, and a Cloud Scheduler trigger for serverless pipeline orchestration."
  type        = bool
  default     = false
}

variable "cloud_workflows_schedule" {
  description = "Cron schedule for the pipeline cascade (Cloud Scheduler). Set to empty string to disable scheduling."
  type        = string
  default     = "0 */6 * * *"
}

# ---------------------------------------------------------------------------
# GitHub OIDC and Delivery
# ---------------------------------------------------------------------------

variable "github_owner" {
  description = "GitHub user or organization that owns the repository."
  type        = string

  validation {
    condition     = var.github_owner != "your-github-username"
    error_message = "Set github_owner to your GitHub user or organization."
  }
}

variable "github_repository" {
  description = "GitHub repository name."
  type        = string

  validation {
    condition     = var.github_repository != "your-repo-name"
    error_message = "Set github_repository to your repository name."
  }
}

variable "github_oidc_pool_id" {
  description = "Workload Identity Pool ID used by GitHub Actions."
  type        = string
  default     = "github-actions"
}

variable "github_oidc_provider_id" {
  description = "Workload Identity Provider ID used by GitHub Actions."
  type        = string
  default     = "github-oidc"
}

variable "provision_cloud_build_triggers" {
  description = "Whether to create Cloud Build triggers via Developer Connect."
  type        = bool
  default     = false
}

variable "github_app_installation_id" {
  description = "GitHub App installation ID for Developer Connect (from GCP Console)."
  type        = string
  default     = ""
}

variable "ui_operator_token" {
  description = "Shared secret gating the pipeline trigger in the public UI. Empty disables the trigger."
  type        = string
  default     = ""
  sensitive   = true
}
