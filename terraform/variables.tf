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
  default     = "512Mi"
}

variable "mlflow_tracking_uri" {
  description = "Reachable MLflow tracking URI for the Cloud Run inference service."
  type        = string
  default     = ""

  validation {
    condition = (
      !var.provision_cloud_run_service || trimspace(var.mlflow_tracking_uri) != ""
    )
    error_message = "Set mlflow_tracking_uri when provision_cloud_run_service is true."
  }
}

variable "cloud_run_env_vars" {
  description = "Additional environment variables for the Cloud Run inference service."
  type        = map(string)
  default     = {}
}

variable "provision_online_compose_host" {
  description = "Whether Terraform should create a single online Docker host for the full Airflow, MLflow, and app stack."
  type        = bool
  default     = false
}

variable "online_compose_host_name" {
  description = "Compute Engine instance name for the online Docker host."
  type        = string
  default     = "foehncast-online"
}

variable "online_compose_host_zone" {
  description = "Zone for the online Docker host."
  type        = string
  default     = "europe-west6-b"
}

variable "online_compose_machine_type" {
  description = "Machine type for the online Docker host."
  type        = string
  default     = "e2-standard-4"
}

variable "online_compose_disk_size_gb" {
  description = "Boot disk size in GB for the online Docker host."
  type        = number
  default     = 40
}

variable "online_compose_subnet_cidr" {
  description = "CIDR range for the dedicated online Docker host subnet."
  type        = string
  default     = "10.42.0.0/24"
}

variable "online_compose_public_ports" {
  description = "TCP ports exposed publicly by the online Docker host."
  type        = list(number)
  default     = [8000]
}

variable "online_compose_git_ref" {
  description = "Git ref that the online Docker host should check out before starting the stack."
  type        = string
  default     = "main"
}

variable "online_compose_airflow_admin_username" {
  description = "Airflow admin username for the online Docker host."
  type        = string
  default     = "admin"
}

variable "online_compose_app_image" {
  description = "Optional app image URI for the online Docker host. Leave empty to use the default GHCR image."
  type        = string
  default     = ""
}

variable "online_compose_airflow_image" {
  description = "Optional Airflow image URI for the online Docker host. Leave empty to use the default GHCR image."
  type        = string
  default     = ""
}

variable "online_compose_mlflow_image" {
  description = "Optional MLflow image URI for the online Docker host. Leave empty to use the default GHCR image."
  type        = string
  default     = ""
}

variable "online_compose_env_vars" {
  description = "Additional environment variables for the online Docker host stack."
  type        = map(string)
  default     = {}
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository."
  type        = string
  default     = "javihslu"
}

variable "github_repository" {
  description = "GitHub repository name."
  type        = string
  default     = "foehncast"
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
