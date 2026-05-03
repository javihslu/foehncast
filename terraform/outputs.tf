output "artifact_registry_repository" {
  description = "Artifact Registry repository path for container images."
  value       = google_artifact_registry_repository.containers.id
}

output "artifact_bucket_name" {
  description = "GCS bucket managed by Terraform for artifacts."
  value       = google_storage_bucket.artifacts.name
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
