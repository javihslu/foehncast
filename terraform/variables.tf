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
