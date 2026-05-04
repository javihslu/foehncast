output "project_id" {
  description = "GCP project ID managed by this Terraform configuration."
  value       = var.project_id
}

output "region" {
  description = "Primary GCP region used by this Terraform configuration."
  value       = var.region
}

output "artifact_registry_repository_id" {
  description = "Artifact Registry repository name used for container images."
  value       = google_artifact_registry_repository.containers.repository_id
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository path for container images."
  value       = google_artifact_registry_repository.containers.id
}

output "artifact_bucket_name" {
  description = "GCS bucket managed by Terraform for artifacts."
  value       = google_storage_bucket.artifacts.name
}

output "bigquery_dataset_id" {
  description = "BigQuery dataset for curated feature data."
  value       = google_bigquery_dataset.feature_store.dataset_id
}

output "bigquery_feature_table_id" {
  description = "BigQuery table for curated feature rows."
  value       = google_bigquery_table.forecast_features.table_id
}

output "github_deployer_service_account" {
  description = "Service account used by GitHub Actions via Workload Identity Federation."
  value       = google_service_account.github_deployer.email
}

output "github_workload_identity_provider" {
  description = "Full provider name for GitHub OIDC authentication."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "cloud_run_runtime_service_account" {
  description = "Service account intended for Cloud Run runtime execution."
  value       = google_service_account.cloud_run_runtime.email
}

output "cloud_run_service_name" {
  description = "Cloud Run service name for the inference API, if provisioned."
  value       = try(google_cloud_run_v2_service.app[0].name, null)
}

output "cloud_run_service_url" {
  description = "Cloud Run service URL for the inference API, if provisioned."
  value       = try(google_cloud_run_v2_service.app[0].uri, null)
}
