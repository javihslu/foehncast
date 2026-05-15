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
  value       = try(google_artifact_registry_repository.containers.repository_id, var.artifact_registry_repository_id)
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository path for container images."
  value       = try(google_artifact_registry_repository.containers.id, "projects/${var.project_id}/locations/${var.region}/repositories/${var.artifact_registry_repository_id}")
}

output "artifact_bucket_name" {
  description = "GCS bucket managed by Terraform for artifacts."
  value       = try(google_storage_bucket.artifacts.name, var.artifact_bucket_name)
}

output "bigquery_dataset_id" {
  description = "BigQuery dataset for curated feature data."
  value       = try(google_bigquery_dataset.feature_store.dataset_id, var.bigquery_dataset_id)
}

output "bigquery_location" {
  description = "BigQuery location for curated feature data."
  value       = var.bigquery_location
}

output "bigquery_feature_table_id" {
  description = "BigQuery table for curated feature rows."
  value       = try(google_bigquery_table.forecast_features.table_id, var.bigquery_feature_table_id)
}

output "feast_online_store_location" {
  description = "Location of the Firestore Datastore-mode database used by Feast online serving."
  value       = try(google_firestore_database.feast_online_store.location_id, var.feast_online_store_location)
}

output "feast_online_store_database_name" {
  description = "Database name of the Firestore Datastore-mode database used by Feast online serving."
  value       = try(google_firestore_database.feast_online_store.name, var.feast_online_store_database_name)
}

output "github_deployer_service_account" {
  description = "Service account used by GitHub Actions via Workload Identity Federation."
  value       = try(google_service_account.github_deployer.email, "github-actions-deployer@${var.project_id}.iam.gserviceaccount.com")
}

output "github_workload_identity_provider" {
  description = "Full provider name for GitHub OIDC authentication."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "cloud_run_runtime_service_account" {
  description = "Service account intended for Cloud Run runtime execution."
  value       = try(google_service_account.cloud_run_runtime.email, "foehncast-cloud-run@${var.project_id}.iam.gserviceaccount.com")
}

output "online_compose_runtime_service_account" {
  description = "Service account intended for the online compose host runtime when that target is enabled."
  value       = var.provision_online_compose_host ? try(google_service_account.online_compose_runtime[0].email, "foehncast-online-compose@${var.project_id}.iam.gserviceaccount.com") : null
}

output "cloud_composer_runtime_service_account" {
  description = "Service account intended for the Cloud Composer environment when that target is enabled."
  value       = var.provision_cloud_composer_environment ? try(google_service_account.cloud_composer_runtime[0].email, "foehncast-composer@${var.project_id}.iam.gserviceaccount.com") : null
}

output "provision_cloud_composer_environment" {
  description = "Whether Terraform is configured to provision the Cloud Composer environment."
  value       = var.provision_cloud_composer_environment
}

output "configured_cloud_composer_environment_name" {
  description = "Configured Cloud Composer environment name for the managed orchestration target."
  value       = var.cloud_composer_environment_name
}

output "cloud_composer_environment_name" {
  description = "Cloud Composer environment name, if provisioned."
  value       = try(google_composer_environment.cloud_composer[0].name, null)
}

output "cloud_composer_airflow_uri" {
  description = "Airflow web interface URI for the Cloud Composer environment, if provisioned."
  value       = try(google_composer_environment.cloud_composer[0].config[0].airflow_uri, null)
}

output "cloud_composer_dag_gcs_prefix" {
  description = "DAG bucket prefix for the Cloud Composer environment, if provisioned."
  value       = try(google_composer_environment.cloud_composer[0].config[0].dag_gcs_prefix, null)
}

output "provision_cloud_run_service" {
  description = "Whether Terraform is configured to provision the Cloud Run inference service."
  value       = var.provision_cloud_run_service
}

output "configured_cloud_run_service_name" {
  description = "Configured Cloud Run service name for the inference API."
  value       = var.cloud_run_service_name
}

output "configured_cloud_run_container_port" {
  description = "Configured container port for the Cloud Run inference service."
  value       = var.cloud_run_container_port
}

output "configured_cloud_run_allow_unauthenticated" {
  description = "Whether the configured Cloud Run inference service should allow unauthenticated access."
  value       = var.cloud_run_allow_unauthenticated
}

output "configured_cloud_run_min_instance_count" {
  description = "Configured minimum Cloud Run instance count."
  value       = var.cloud_run_min_instance_count
}

output "configured_cloud_run_max_instance_count" {
  description = "Configured maximum Cloud Run instance count."
  value       = var.cloud_run_max_instance_count
}

output "configured_cloud_run_cpu" {
  description = "Configured CPU limit for the Cloud Run inference service."
  value       = var.cloud_run_cpu
}

output "configured_cloud_run_memory" {
  description = "Configured memory limit for the Cloud Run inference service."
  value       = var.cloud_run_memory
}

output "mlflow_tracking_uri" {
  description = "Configured MLflow tracking URI used by the Cloud Run inference service."
  value       = var.mlflow_tracking_uri
}

output "cloud_run_service_name" {
  description = "Cloud Run service name for the inference API, if provisioned."
  value       = try(google_cloud_run_v2_service.app[0].name, null)
}

output "cloud_run_service_url" {
  description = "Cloud Run service URL for the inference API, if provisioned."
  value       = try(google_cloud_run_v2_service.app[0].uri, null)
}

output "primary_hosted_api_target" {
  description = "Primary hosted API target. The promoted hosted contract requires Cloud Run to carry the public API surface."
  value       = try(google_cloud_run_v2_service.app[0].uri, null) != null ? "cloud-run" : "none"
}

output "primary_hosted_api_url" {
  description = "Primary hosted API URL. The promoted hosted contract requires this to resolve to Cloud Run."
  value       = try(google_cloud_run_v2_service.app[0].uri, null)
}

output "online_compose_host_ip" {
  description = "Public IP address of the online Docker host, if provisioned."
  value       = try(google_compute_address.online_compose[0].address, null)
}

output "provision_online_compose_host" {
  description = "Whether Terraform is configured to provision the online Docker host."
  value       = var.provision_online_compose_host
}

output "online_compose_host_name" {
  description = "Configured name for the online Docker host."
  value       = var.online_compose_host_name
}

output "online_compose_host_zone" {
  description = "Configured zone for the online Docker host."
  value       = var.online_compose_host_zone
}

output "online_compose_machine_type" {
  description = "Configured machine type for the online Docker host."
  value       = var.online_compose_machine_type
}

output "online_compose_disk_size_gb" {
  description = "Configured boot disk size in GB for the online Docker host."
  value       = var.online_compose_disk_size_gb
}

output "online_compose_app_url" {
  description = "Public URL for the online inference API, if provisioned."
  value       = var.provision_online_compose_host && contains(var.online_compose_public_ports, 8000) ? "http://${google_compute_address.online_compose[0].address}:8000" : null
}

output "online_compose_airflow_url" {
  description = "Public URL for the online Airflow UI, if provisioned and explicitly exposed."
  value       = var.provision_online_compose_host && contains(var.online_compose_public_ports, 8080) ? "http://${google_compute_address.online_compose[0].address}:8080" : null
}

output "online_compose_mlflow_url" {
  description = "Public URL for the online MLflow UI, if provisioned and explicitly exposed."
  value       = var.provision_online_compose_host && contains(var.online_compose_public_ports, 5001) ? "http://${google_compute_address.online_compose[0].address}:5001" : null
}
