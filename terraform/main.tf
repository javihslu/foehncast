locals {
  github_repository_path            = "${var.github_owner}/${var.github_repository}"
  artifact_registry_host            = "${var.region}-docker.pkg.dev"
  artifact_registry_repository_path = "${local.artifact_registry_host}/${var.project_id}/${var.artifact_registry_repository_id}"
  cloud_run_image                   = var.cloud_run_image != "" ? var.cloud_run_image : "${local.artifact_registry_repository_path}/foehncast-app:latest"
  cloud_run_grafana_image           = var.cloud_run_grafana_image != "" ? var.cloud_run_grafana_image : "${local.artifact_registry_repository_path}/foehncast-grafana:latest"
  cloud_run_ui_image                = var.cloud_run_ui_image != "" ? var.cloud_run_ui_image : "${local.artifact_registry_repository_path}/foehncast-ui:latest"
  cloud_run_mlflow_image            = var.cloud_run_mlflow_image != "" ? var.cloud_run_mlflow_image : "${local.artifact_registry_repository_path}/foehncast-mlflow:latest"
  online_compose_app_image          = var.online_compose_app_image != "" ? var.online_compose_app_image : "${local.artifact_registry_repository_path}/foehncast-app:latest"
  online_compose_airflow_image      = var.online_compose_airflow_image != "" ? var.online_compose_airflow_image : "${local.artifact_registry_repository_path}/foehncast-airflow:latest"
  online_compose_mlflow_image       = var.online_compose_mlflow_image != "" ? var.online_compose_mlflow_image : "${local.artifact_registry_repository_path}/foehncast-mlflow:latest"
  feast_registry_uri                = "gs://${var.artifact_bucket_name}/feast/registry.db"
  feast_staging_uri                 = "gs://${var.artifact_bucket_name}/feast/staging"
  feast_bigquery_table              = "${var.project_id}.${var.bigquery_dataset_id}.${var.bigquery_feature_table_id}"
  prediction_event_dataset_id       = "foehncast_monitoring"
  prediction_event_table_id         = "prediction_events"
  # When MLflow is deployed on Cloud Run, use its URL; otherwise fall back to
  # the explicit variable (e.g. an external MLflow server).
  mlflow_tracking_uri = (
    var.provision_cloud_run_mlflow
    ? google_cloud_run_v2_service.mlflow[0].uri
    : var.mlflow_tracking_uri
  )

  cloud_run_env_vars = merge(
    {
      GCP_PROJECT_ID                       = var.project_id
      GCP_LOCATION                         = var.region
      GOOGLE_CLOUD_PROJECT                 = var.project_id
      MLFLOW_TRACKING_URI                  = local.mlflow_tracking_uri
      STORAGE_BACKEND                      = "bigquery"
      STORAGE_BIGQUERY_PROJECT_ID          = var.project_id
      STORAGE_BIGQUERY_DATASET             = var.bigquery_dataset_id
      STORAGE_BIGQUERY_TABLE               = var.bigquery_feature_table_id
      FOEHNCAST_FEAST_SOURCE               = "bigquery"
      FOEHNCAST_FEAST_PROJECT              = "foehncast"
      FOEHNCAST_FEAST_PROJECT_ID           = var.project_id
      FOEHNCAST_FEAST_REGISTRY             = local.feast_registry_uri
      FOEHNCAST_FEAST_GCS_BUCKET           = var.artifact_bucket_name
      FOEHNCAST_FEAST_GCS_STAGING_LOCATION = local.feast_staging_uri
      FOEHNCAST_FEAST_BIGQUERY_DATASET     = var.bigquery_dataset_id
      FOEHNCAST_FEAST_BIGQUERY_LOCATION    = var.bigquery_location
      FOEHNCAST_FEAST_BIGQUERY_TABLE       = local.feast_bigquery_table
      FOEHNCAST_FEAST_DATASTORE_DATABASE   = var.feast_online_store_database_name
      FOEHNCAST_PIPELINE_REPORT_DIR        = "gs://${var.artifact_bucket_name}/airflow/reports"
    },
    var.cloud_run_env_vars,
  )
  online_compose_env_vars = merge(
    {
      APP_BIND_HOST                                 = contains(var.online_compose_public_ports, 8000) ? "0.0.0.0" : "127.0.0.1"
      AIRFLOW_BIND_HOST                             = contains(var.online_compose_public_ports, 8080) ? "0.0.0.0" : "127.0.0.1"
      MLFLOW_BIND_HOST                              = contains(var.online_compose_public_ports, 5001) ? "0.0.0.0" : "127.0.0.1"
      AIRFLOW_ADMIN_USERNAME                        = var.online_compose_airflow_admin_username
      AIRFLOW_ADMIN_PASSWORD_FILE                   = "/workspace/airflow/.admin-password"
      AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS = "false"
      AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_USERS      = "${var.online_compose_airflow_admin_username}:admin"
      AIRFLOW__API_AUTH__JWT_SECRET                 = random_password.airflow_api_auth_jwt_secret.result
      GCP_PROJECT_ID                                = var.project_id
      GCP_LOCATION                                  = var.region
      MLFLOW_ARTIFACT_DESTINATION                   = "gs://${var.artifact_bucket_name}/mlflow/artifacts"
      STORAGE_BACKEND                               = "bigquery"
      STORAGE_BIGQUERY_PROJECT_ID                   = var.project_id
      STORAGE_BIGQUERY_DATASET                      = var.bigquery_dataset_id
      STORAGE_BIGQUERY_TABLE                        = var.bigquery_feature_table_id
      FOEHNCAST_FEAST_SOURCE                        = "bigquery"
      FOEHNCAST_FEAST_PROJECT                       = "foehncast"
      FOEHNCAST_FEAST_PROJECT_ID                    = var.project_id
      FOEHNCAST_FEAST_REGISTRY                      = local.feast_registry_uri
      FOEHNCAST_FEAST_GCS_BUCKET                    = var.artifact_bucket_name
      FOEHNCAST_FEAST_GCS_STAGING_LOCATION          = local.feast_staging_uri
      FOEHNCAST_FEAST_BIGQUERY_DATASET              = var.bigquery_dataset_id
      FOEHNCAST_FEAST_BIGQUERY_LOCATION             = var.bigquery_location
      FOEHNCAST_FEAST_BIGQUERY_TABLE                = local.feast_bigquery_table
      FOEHNCAST_FEAST_DATASTORE_DATABASE            = var.feast_online_store_database_name
      FOEHNCAST_PIPELINE_REPORT_DIR                 = "gs://${var.artifact_bucket_name}/airflow/reports"
      FOEHNCAST_APP_IMAGE                           = local.online_compose_app_image
      FOEHNCAST_AIRFLOW_IMAGE                       = local.online_compose_airflow_image
      FOEHNCAST_MLFLOW_IMAGE                        = local.online_compose_mlflow_image
    },
    var.online_compose_env_vars,
  )
  cloud_composer_secret_resource_paths = {
    for env_name, secret_id in var.cloud_composer_secret_env_vars :
    env_name => (
      can(regex("^projects/[^/]+/secrets/[^/]+(?:/versions/[^/]+)?$", trimspace(secret_id)))
      ? trimspace(secret_id)
      : "projects/${var.project_id}/secrets/${trimspace(secret_id)}"
    )
  }
  cloud_composer_secret_iam_ids = {
    for env_name, secret_id in local.cloud_composer_secret_resource_paths :
    env_name => regexreplace(secret_id, "/versions/[^/]+$", "")
  }
  cloud_composer_secret_env_var_refs = {
    for env_name, secret_id in local.cloud_composer_secret_resource_paths :
    env_name => "sm://${secret_id}"
  }
  cloud_composer_env_vars = merge(
    {
      GCP_PROJECT_ID                        = var.project_id
      GCP_LOCATION                          = var.region
      GOOGLE_CLOUD_PROJECT                  = var.project_id
      MLFLOW_ARTIFACT_DESTINATION           = "gs://${var.artifact_bucket_name}/mlflow/artifacts"
      MLFLOW_TRACKING_URI                   = local.mlflow_tracking_uri
      STORAGE_BACKEND                       = "bigquery"
      STORAGE_BIGQUERY_PROJECT_ID           = var.project_id
      STORAGE_BIGQUERY_DATASET              = var.bigquery_dataset_id
      STORAGE_BIGQUERY_TABLE                = var.bigquery_feature_table_id
      FOEHNCAST_FEAST_SOURCE                = "bigquery"
      FOEHNCAST_FEAST_PROJECT               = "foehncast"
      FOEHNCAST_FEAST_PROJECT_ID            = var.project_id
      FOEHNCAST_FEAST_REGISTRY              = local.feast_registry_uri
      FOEHNCAST_FEAST_GCS_BUCKET            = var.artifact_bucket_name
      FOEHNCAST_FEAST_GCS_STAGING_LOCATION  = local.feast_staging_uri
      FOEHNCAST_FEAST_BIGQUERY_DATASET      = var.bigquery_dataset_id
      FOEHNCAST_FEAST_BIGQUERY_LOCATION     = var.bigquery_location
      FOEHNCAST_FEAST_BIGQUERY_TABLE        = local.feast_bigquery_table
      FOEHNCAST_FEAST_DATASTORE_DATABASE    = var.feast_online_store_database_name
      FOEHNCAST_PIPELINE_REPORT_DIR         = "gs://${var.artifact_bucket_name}/airflow/reports"
      FOEHNCAST_RUNTIME_RELEASE_REPORT_PATH = "gs://${var.artifact_bucket_name}/airflow/reports/runtime-release-latest.json"
    },
    var.cloud_composer_env_vars,
    local.cloud_composer_secret_env_var_refs,
  )
  cloud_composer_pypi_packages = merge(
    {
      evidently                   = ">=0.7.21"
      feast                       = "[gcp]>=0.63.0"
      google-cloud-bigquery       = ">=3.30.0"
      google-cloud-secret-manager = ">=2.23.0"
      google-cloud-storage        = ">=2.19.0"
      matplotlib                  = ">=3.8"
      mlflow                      = ">=3.0"
      pandas                      = ">=2.0"
      pyarrow                     = ">=14.0"
      pyyaml                      = ">=6.0"
      requests                    = ">=2.31"
      scikit-learn                = ">=1.5"
    },
    var.cloud_composer_pypi_packages,
  )

  forecast_feature_schema = [
    {
      name        = "forecast_time"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Hourly forecast timestamp."
    },
    {
      name        = "wind_speed_10m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Wind speed at 10 m in km/h."
    },
    {
      name        = "wind_speed_80m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Wind speed at 80 m in km/h."
    },
    {
      name        = "wind_speed_120m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Wind speed at 120 m in km/h."
    },
    {
      name        = "wind_direction_10m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Wind direction at 10 m in degrees."
    },
    {
      name        = "wind_direction_80m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Wind direction at 80 m in degrees."
    },
    {
      name        = "wind_gusts_10m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Wind gust speed at 10 m in km/h."
    },
    {
      name        = "temperature_2m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Air temperature at 2 m in Celsius."
    },
    {
      name        = "precipitation"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Hourly precipitation."
    },
    {
      name        = "relative_humidity_2m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Relative humidity at 2 m in percent."
    },
    {
      name        = "cloud_cover"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cloud cover in percent."
    },
    {
      name        = "pressure_msl"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Mean sea-level pressure."
    },
    {
      name        = "cape"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Convective available potential energy."
    },
    {
      name        = "lifted_index"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Lifted index from Open-Meteo."
    },
    {
      name        = "spot_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Stable spot identifier from config.yaml."
    },
    {
      name        = "spot_name"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Human-readable spot name."
    },
    {
      name        = "hour_of_day_sin"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cyclical encoding of the forecast hour."
    },
    {
      name        = "hour_of_day_cos"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cyclical encoding of the forecast hour."
    },
    {
      name        = "day_of_year_sin"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cyclical encoding of the day of year."
    },
    {
      name        = "day_of_year_cos"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cyclical encoding of the day of year."
    },
    {
      name        = "wind_direction_10m_sin"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cyclical sine encoding of 10 m wind direction."
    },
    {
      name        = "wind_direction_10m_cos"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cyclical cosine encoding of 10 m wind direction."
    },
    {
      name        = "wind_steadiness"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Rolling coefficient of variation of 10 m wind speed."
    },
    {
      name        = "gust_excess_10m"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Absolute difference between gust speed and sustained 10 m wind speed."
    },
    {
      name        = "gust_factor"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Ratio of gust speed to sustained wind speed."
    },
    {
      name        = "shore_alignment"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Cosine similarity of wind direction to shore orientation."
    },
    {
      name        = "dataset_name"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Logical dataset partition such as train or forecast."
    },
  ]

  prediction_event_schema = [
    {
      name        = "prediction_timestamp"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Timestamp when the prediction payload was recorded."
    },
    {
      name        = "forecast_time"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "Forecast timestamp associated with the predicted quality row."
    },
    {
      name        = "quality_index"
      type        = "FLOAT"
      mode        = "REQUIRED"
      description = "Predicted quality index for one forecast row."
    },
    {
      name        = "endpoint"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Serving endpoint that produced the prediction payload."
    },
    {
      name        = "model_version"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Resolved model version used for the prediction."
    },
    {
      name        = "spot_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Stable spot identifier from config.yaml."
    },
    {
      name        = "spot_name"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Human-readable spot name at prediction time."
    },
    {
      name        = "requested_spot_ids"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "JSON-encoded requested spot ids from the inference request."
    },
  ]

  required_services = toset([
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "composer.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "sts.googleapis.com",
    "workflows.googleapis.com",
  ])
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "random_password" "airflow_api_auth_jwt_secret" {
  length  = 32
  special = false
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "containers" {
  provider = google

  location      = var.region
  repository_id = var.artifact_registry_repository_id
  description   = "Docker images for the FoehnCast services"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "artifacts" {
  name                        = var.artifact_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }

    action {
      type = "Delete"
    }
  }
}

resource "google_bigquery_dataset" "feature_store" {
  dataset_id                 = var.bigquery_dataset_id
  location                   = var.bigquery_location
  description                = "FoehnCast curated feature store"
  delete_contents_on_destroy = false

  depends_on = [google_project_service.required]
}

resource "google_bigquery_table" "forecast_features" {
  dataset_id          = google_bigquery_dataset.feature_store.dataset_id
  table_id            = var.bigquery_feature_table_id
  description         = "Curated hourly feature rows for training and inference"
  deletion_protection = false
  schema              = jsonencode(local.forecast_feature_schema)
  clustering          = ["spot_id", "dataset_name"]

  time_partitioning {
    type  = "DAY"
    field = "forecast_time"
  }
}

resource "google_bigquery_dataset" "monitoring_store" {
  dataset_id                 = local.prediction_event_dataset_id
  location                   = var.bigquery_location
  description                = "FoehnCast retained inference monitoring facts"
  delete_contents_on_destroy = false

  depends_on = [google_project_service.required]
}

resource "google_bigquery_table" "prediction_events" {
  dataset_id          = google_bigquery_dataset.monitoring_store.dataset_id
  table_id            = local.prediction_event_table_id
  description         = "Retained prediction-event history for hosted inference monitoring"
  deletion_protection = false
  schema              = jsonencode(local.prediction_event_schema)
  clustering          = ["model_version", "endpoint", "spot_id"]

  time_partitioning {
    type  = "DAY"
    field = "prediction_timestamp"
  }
}

resource "google_firestore_database" "feast_online_store" {
  project                     = var.project_id
  name                        = var.feast_online_store_database_name
  location_id                 = var.feast_online_store_location
  type                        = "DATASTORE_MODE"
  app_engine_integration_mode = "DISABLED"
  deletion_policy             = "DELETE"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "github_deployer" {
  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions deployer"
}

resource "google_project_iam_member" "github_project_admin" {
  for_each = toset([
    "roles/artifactregistry.admin",
    "roles/bigquery.admin",
    "roles/cloudbuild.builds.editor",
    "roles/composer.admin",
    "roles/compute.admin",
    "roles/datastore.owner",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_service_account" "cloud_run_runtime" {
  account_id   = "foehncast-cloud-run"
  display_name = "FoehnCast Cloud Run runtime"
}

resource "google_service_account" "online_compose_runtime" {
  count = var.provision_online_compose_host ? 1 : 0

  account_id   = "foehncast-online-compose"
  display_name = "FoehnCast online compose runtime"
}

resource "google_service_account" "cloud_composer_runtime" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  account_id   = "foehncast-composer"
  display_name = "FoehnCast Cloud Composer runtime"
}

resource "google_project_iam_member" "github_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_cloud_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "github_service_account_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_storage_bucket_iam_member" "github_bucket_admin" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "cloud_build_writer" {
  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"
}

# ---------------------------------------------------------------------------
# Dedicated Cloud Build service account (least-privilege alternative to the
# default Cloud Build SA).  Builds are submitted by GitHub Actions via the
# github_deployer SA; the build itself runs as this SA when
# --service-account is passed to `gcloud builds submit`.
# ---------------------------------------------------------------------------

resource "google_service_account" "cloud_build" {
  account_id   = "foehncast-cloud-build"
  display_name = "FoehnCast Cloud Build"
}

resource "google_artifact_registry_repository_iam_member" "cloud_build_sa_writer" {
  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_project_iam_member" "cloud_build_sa_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_service_account_iam_member" "github_deployer_impersonate_cloud_build" {
  service_account_id = google_service_account.cloud_build.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "cloud_run_reader" {
  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_storage_bucket_iam_member" "cloud_run_bucket_reader" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_storage_bucket_iam_member" "cloud_run_bucket_metadata_reader" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "cloud_run_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "cloud_run_bigquery_read_session_user" {
  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "cloud_run_datastore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "cloud_run_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "cloud_run_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_bigquery_dataset_iam_member" "cloud_run_bigquery_reader" {
  dataset_id = google_bigquery_dataset.feature_store.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_bigquery_dataset_iam_member" "cloud_run_monitoring_bigquery_editor" {
  dataset_id = google_bigquery_dataset.monitoring_store.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "online_compose_bigquery_job_user" {
  count = var.provision_online_compose_host ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_project_iam_member" "online_compose_bigquery_read_session_user" {
  count = var.provision_online_compose_host ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_project_iam_member" "online_compose_datastore_user" {
  count = var.provision_online_compose_host ? 1 : 0

  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "online_compose_reader" {
  count = var.provision_online_compose_host ? 1 : 0

  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_storage_bucket_iam_member" "online_compose_bucket_admin" {
  count = var.provision_online_compose_host ? 1 : 0

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_storage_bucket_iam_member" "online_compose_bucket_metadata_reader" {
  count = var.provision_online_compose_host ? 1 : 0

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_bigquery_dataset_iam_member" "online_compose_bigquery_editor" {
  count = var.provision_online_compose_host ? 1 : 0

  dataset_id = google_bigquery_dataset.feature_store.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_bigquery_dataset_iam_member" "online_compose_monitoring_bigquery_editor" {
  count = var.provision_online_compose_host ? 1 : 0

  dataset_id = google_bigquery_dataset.monitoring_store.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_project_iam_member" "cloud_composer_worker" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  project = var.project_id
  role    = "roles/composer.worker"
  member  = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_service_account_iam_member" "cloud_composer_service_agent_extension" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  service_account_id = google_service_account.cloud_composer_runtime[0].name
  role               = "roles/composer.ServiceAgentV2Ext"
  member             = "serviceAccount:service-${data.google_project.current.number}@cloudcomposer-accounts.iam.gserviceaccount.com"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "cloud_composer_bigquery_job_user" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_project_iam_member" "cloud_composer_bigquery_read_session_user" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_project_iam_member" "cloud_composer_datastore_user" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_artifact_registry_repository_iam_member" "cloud_composer_reader" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  location   = google_artifact_registry_repository.containers.location
  repository = google_artifact_registry_repository.containers.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_storage_bucket_iam_member" "cloud_composer_bucket_admin" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_storage_bucket_iam_member" "cloud_composer_bucket_metadata_reader" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_bigquery_dataset_iam_member" "cloud_composer_bigquery_editor" {
  count = var.provision_cloud_composer_environment ? 1 : 0

  dataset_id = google_bigquery_dataset.feature_store.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_secret_manager_secret_iam_member" "cloud_composer_secret_accessor" {
  for_each = var.provision_cloud_composer_environment ? local.cloud_composer_secret_iam_ids : {}

  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_composer_runtime[0].email}"
}

resource "google_cloud_run_v2_service" "app" {
  count               = var.provision_cloud_run_service ? 1 : 0
  name                = var.cloud_run_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.cloud_run_runtime.email
    timeout         = "300s"

    scaling {
      min_instance_count = var.cloud_run_min_instance_count
      max_instance_count = var.cloud_run_max_instance_count
    }

    containers {
      image = local.cloud_run_image

      ports {
        container_port = var.cloud_run_container_port
      }

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }
      }

      dynamic "env" {
        for_each = local.cloud_run_env_vars
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.required,
    google_firestore_database.feast_online_store,
    google_artifact_registry_repository_iam_member.cloud_run_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_metadata_reader,
    google_project_iam_member.cloud_run_bigquery_job_user,
    google_project_iam_member.cloud_run_bigquery_read_session_user,
    google_project_iam_member.cloud_run_datastore_user,
    google_bigquery_dataset_iam_member.cloud_run_bigquery_reader,
    google_bigquery_dataset_iam_member.cloud_run_monitoring_bigquery_editor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.provision_cloud_run_service && var.cloud_run_allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.app[0].location
  name     = google_cloud_run_v2_service.app[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Cloud Run — Grafana (read-only monitoring dashboard)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "grafana" {
  count               = var.provision_cloud_run_grafana ? 1 : 0
  name                = var.cloud_run_grafana_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    timeout = "30s"

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = local.cloud_run_grafana_image

      ports {
        container_port = 3000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GRAFANA_PROMETHEUS_URL"
        value = var.cloud_run_grafana_prometheus_url
      }

      # Read-only public viewer surface — anonymous access, embedding enabled.
      env {
        name  = "GF_AUTH_ANONYMOUS_ENABLED"
        value = "true"
      }
      env {
        name  = "GF_AUTH_ANONYMOUS_ORG_ROLE"
        value = "Viewer"
      }
      env {
        name  = "GF_AUTH_DISABLE_LOGIN_FORM"
        value = "true"
      }
      env {
        name  = "GF_SECURITY_ALLOW_EMBEDDING"
        value = "true"
      }
      env {
        name  = "GF_SECURITY_ADMIN_PASSWORD"
        value = random_password.grafana_admin[0].result
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [google_project_service.required]
}

resource "random_password" "grafana_admin" {
  count   = var.provision_cloud_run_grafana ? 1 : 0
  length  = 24
  special = false
}

resource "google_cloud_run_v2_service_iam_member" "grafana_public_invoker" {
  count    = var.provision_cloud_run_grafana ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.grafana[0].location
  name     = google_cloud_run_v2_service.grafana[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Cloud SQL — MLflow metadata backend (PostgreSQL micro)
# ---------------------------------------------------------------------------

resource "google_sql_database_instance" "mlflow" {
  count = var.provision_cloud_run_mlflow ? 1 : 0

  name             = var.cloud_sql_mlflow_instance_name
  database_version = "POSTGRES_15"
  region           = var.region
  project          = var.project_id

  deletion_protection = false

  settings {
    tier              = "db-f1-micro"
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"

    disk_size    = 10
    disk_type    = "PD_HDD"
    disk_autoresize = false

    ip_configuration {
      ipv4_enabled = true
      # Public IP is enabled but NO authorized_networks are defined,
      # so direct TCP connections are blocked.  Cloud Run connects
      # via Auth Proxy sidecar (unix socket through the Cloud SQL
      # Admin API).  Operators use `gcloud sql connect`.
    }

    backup_configuration {
      enabled = false
    }

    database_flags {
      name  = "max_connections"
      value = "50"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "mlflow" {
  count = var.provision_cloud_run_mlflow ? 1 : 0

  name     = "mlflow"
  instance = google_sql_database_instance.mlflow[0].name
}

resource "random_password" "mlflow_db" {
  count   = var.provision_cloud_run_mlflow ? 1 : 0
  length  = 24
  special = false
}

resource "google_sql_user" "mlflow" {
  count = var.provision_cloud_run_mlflow ? 1 : 0

  instance = google_sql_database_instance.mlflow[0].name
  name     = "mlflow"
  password = random_password.mlflow_db[0].result
}

# Grant the Cloud Run SA permission to connect via Cloud SQL Auth Proxy.
resource "google_project_iam_member" "cloud_run_cloudsql_client" {
  count = var.provision_cloud_run_mlflow ? 1 : 0

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

# ---------------------------------------------------------------------------
# Cloud Run — MLflow (tracking server, protected)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "mlflow" {
  count               = var.provision_cloud_run_mlflow ? 1 : 0
  name                = var.cloud_run_mlflow_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.cloud_run_runtime.email
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.mlflow[0].connection_name]
      }
    }

    containers {
      image = local.cloud_run_mlflow_image

      ports {
        container_port = 5001
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      env {
        name  = "MLFLOW_BACKEND_STORE_URI"
        value = "postgresql+psycopg2://mlflow:${random_password.mlflow_db[0].result}@/${google_sql_database.mlflow[0].name}?host=/cloudsql/${google_sql_database_instance.mlflow[0].connection_name}"
      }

      env {
        name  = "MLFLOW_ARTIFACT_DESTINATION"
        value = "gs://${var.artifact_bucket_name}/mlflow/artifacts"
      }

      env {
        name  = "MLFLOW_PORT"
        value = "5001"
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.required,
    google_sql_database.mlflow,
    google_sql_user.mlflow,
    google_project_iam_member.cloud_run_cloudsql_client,
    google_artifact_registry_repository_iam_member.cloud_run_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_metadata_reader,
  ]
}

# MLflow is NOT public — only authenticated service accounts can invoke it.
# Operators access via `gcloud run services proxy` or IAP (if configured).
# The shared Cloud Run service account can invoke MLflow for tracking calls.
resource "google_cloud_run_v2_service_iam_member" "mlflow_internal_invoker" {
  count    = var.provision_cloud_run_mlflow ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.mlflow[0].location
  name     = google_cloud_run_v2_service.mlflow[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

# ---------------------------------------------------------------------------
# Cloud Run — UI (Streamlit rider console)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "ui" {
  count               = var.provision_cloud_run_ui ? 1 : 0
  name                = var.cloud_run_ui_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.cloud_run_runtime.email
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = local.cloud_run_ui_image

      ports {
        container_port = 8501
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      dynamic "env" {
        for_each = local.cloud_run_env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "FOEHNCAST_GRAFANA_BASE_URL"
        value = (
          var.provision_cloud_run_grafana
          ? google_cloud_run_v2_service.grafana[0].uri
          : var.cloud_run_ui_grafana_url
        )
      }

      env {
        name  = "FOEHNCAST_GRAFANA_ALLOW_EMBEDDING"
        value = "true"
      }

      env {
        name  = "FOEHNCAST_PROMETHEUS_URL"
        value = var.cloud_run_ui_prometheus_url
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_LOCATION"
        value = var.region
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.required,
    google_firestore_database.feast_online_store,
    google_artifact_registry_repository_iam_member.cloud_run_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_metadata_reader,
    google_project_iam_member.cloud_run_bigquery_job_user,
    google_project_iam_member.cloud_run_bigquery_read_session_user,
    google_project_iam_member.cloud_run_datastore_user,
    google_bigquery_dataset_iam_member.cloud_run_bigquery_reader,
    google_bigquery_dataset_iam_member.cloud_run_monitoring_bigquery_editor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "ui_public_invoker" {
  count    = var.provision_cloud_run_ui ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.ui[0].location
  name     = google_cloud_run_v2_service.ui[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Cloud Run Jobs — Pipeline stages (reuse the app image)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_job" "feature_pipeline" {
  count    = var.provision_cloud_workflows ? 1 : 0
  name     = "foehncast-feature-pipeline"
  location = var.region

  template {
    template {
      service_account = google_service_account.cloud_run_runtime.email
      timeout         = "600s"
      max_retries     = 1

      containers {
        image = local.cloud_run_image

        command = ["python", "-c"]
        args    = ["from foehncast.orchestration import run_feature_pipeline_job; run_feature_pipeline_job(dataset='train')"]

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }

        dynamic "env" {
          for_each = local.cloud_run_env_vars
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_job" "training_pipeline" {
  count    = var.provision_cloud_workflows ? 1 : 0
  name     = "foehncast-training-pipeline"
  location = var.region

  template {
    template {
      service_account = google_service_account.cloud_run_runtime.email
      timeout         = "900s"
      max_retries     = 0

      containers {
        image = local.cloud_run_image

        command = ["python", "-c"]
        args    = ["from foehncast.orchestration import run_training_pipeline_step; run_training_pipeline_step(dataset='train')"]

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        dynamic "env" {
          for_each = local.cloud_run_env_vars
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_job" "inference_pipeline" {
  count    = var.provision_cloud_workflows ? 1 : 0
  name     = "foehncast-inference-pipeline"
  location = var.region

  template {
    template {
      service_account = google_service_account.cloud_run_runtime.email
      timeout         = "300s"
      max_retries     = 1

      containers {
        image = local.cloud_run_image

        command = ["python", "-c"]
        args    = ["from foehncast.orchestration import run_inference_pipeline_step; run_inference_pipeline_step()"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        dynamic "env" {
          for_each = local.cloud_run_env_vars
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [google_project_service.required]
}

# ---------------------------------------------------------------------------
# Cloud Workflows — Pipeline orchestration (feature → train → infer)
# ---------------------------------------------------------------------------

resource "google_service_account" "workflows" {
  count = var.provision_cloud_workflows ? 1 : 0

  account_id   = "foehncast-workflows"
  display_name = "FoehnCast Cloud Workflows orchestrator"
}

# The workflow SA needs to run Cloud Run Jobs.
resource "google_project_iam_member" "workflows_run_invoker" {
  count = var.provision_cloud_workflows ? 1 : 0

  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.workflows[0].email}"
}

resource "google_project_iam_member" "workflows_run_developer" {
  count = var.provision_cloud_workflows ? 1 : 0

  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.workflows[0].email}"
}

resource "google_workflows_workflow" "pipeline_cascade" {
  count = var.provision_cloud_workflows ? 1 : 0

  name            = "foehncast-pipeline-cascade"
  region          = var.region
  description     = "FoehnCast FTI pipeline cascade: feature → training → inference"
  service_account = google_service_account.workflows[0].id

  source_contents = <<-YAML
    main:
      steps:
        - log_start:
            call: sys.log
            args:
              text: "FoehnCast pipeline cascade started"
              severity: INFO

        - run_feature_pipeline:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: projects/${var.project_id}/locations/${var.region}/jobs/foehncast-feature-pipeline
            result: feature_result

        - log_feature_done:
            call: sys.log
            args:
              text: "Feature pipeline completed"
              severity: INFO

        - run_training_pipeline:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: projects/${var.project_id}/locations/${var.region}/jobs/foehncast-training-pipeline
            result: training_result

        - log_training_done:
            call: sys.log
            args:
              text: "Training pipeline completed"
              severity: INFO

        - run_inference_pipeline:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: projects/${var.project_id}/locations/${var.region}/jobs/foehncast-inference-pipeline
            result: inference_result

        - log_complete:
            call: sys.log
            args:
              text: "FoehnCast pipeline cascade completed successfully"
              severity: INFO

        - return_result:
            return:
              feature: $${feature_result}
              training: $${training_result}
              inference: $${inference_result}
  YAML

  depends_on = [
    google_project_service.required,
    google_cloud_run_v2_job.feature_pipeline,
    google_cloud_run_v2_job.training_pipeline,
    google_cloud_run_v2_job.inference_pipeline,
  ]
}

# ---------------------------------------------------------------------------
# Cloud Scheduler — Cron trigger for the pipeline cascade
# ---------------------------------------------------------------------------

resource "google_cloud_scheduler_job" "pipeline_cascade" {
  count = var.provision_cloud_workflows ? 1 : 0

  name             = "foehncast-pipeline-cascade"
  description      = "Run the FoehnCast FTI pipeline cascade every 6 hours"
  schedule         = var.cloud_workflows_schedule
  time_zone        = "Europe/Zurich"
  attempt_deadline = "30s"
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "https://workflowexecutions.googleapis.com/v1/${google_workflows_workflow.pipeline_cascade[0].id}/executions"

    oauth_token {
      service_account_email = google_service_account.workflows[0].email
    }
  }

  depends_on = [google_project_service.required]
}

# Grant the UI service account permission to trigger workflows (on-demand button).
resource "google_project_iam_member" "ui_workflows_invoker" {
  count = var.provision_cloud_workflows && var.provision_cloud_run_ui ? 1 : 0

  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_compute_network" "online_compose" {
  count                   = var.provision_online_compose_host ? 1 : 0
  name                    = "${var.online_compose_host_name}-network"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "online_compose" {
  count         = var.provision_online_compose_host ? 1 : 0
  name          = "${var.online_compose_host_name}-subnet"
  ip_cidr_range = var.online_compose_subnet_cidr
  region        = var.region
  network       = google_compute_network.online_compose[0].id
}

resource "google_compute_network" "cloud_composer" {
  count                   = var.provision_cloud_composer_environment ? 1 : 0
  name                    = "${var.cloud_composer_environment_name}-network"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "cloud_composer" {
  count         = var.provision_cloud_composer_environment ? 1 : 0
  name          = "${var.cloud_composer_environment_name}-subnet"
  ip_cidr_range = var.cloud_composer_subnet_cidr
  region        = var.region
  network       = google_compute_network.cloud_composer[0].id
}

resource "google_compute_firewall" "online_compose_public" {
  count   = var.provision_online_compose_host ? 1 : 0
  name    = "${var.online_compose_host_name}-public"
  network = google_compute_network.online_compose[0].name

  allow {
    protocol = "tcp"
    ports    = concat(["22"], [for port in var.online_compose_public_ports : tostring(port)])
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.online_compose_host_name]
}

resource "google_compute_address" "online_compose" {
  count  = var.provision_online_compose_host ? 1 : 0
  name   = "${var.online_compose_host_name}-ip"
  region = var.region
}

resource "google_compute_instance" "online_compose" {
  count        = var.provision_online_compose_host ? 1 : 0
  name         = var.online_compose_host_name
  machine_type = var.online_compose_machine_type
  zone         = var.online_compose_host_zone
  tags         = [var.online_compose_host_name]

  boot_disk {
    initialize_params {
      image = "projects/debian-cloud/global/images/family/debian-12"
      size  = var.online_compose_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.online_compose[0].id

    access_config {
      nat_ip = google_compute_address.online_compose[0].address
    }
  }

  service_account {
    email  = google_service_account.online_compose_runtime[0].email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = templatefile("${path.module}/templates/online-compose-host.sh.tftpl", {
    github_repository_path = local.github_repository_path
    git_ref                = var.online_compose_git_ref
    artifact_registry_host = local.artifact_registry_host
    stack_env              = local.online_compose_env_vars
  })

  depends_on = [
    google_project_service.required,
    google_firestore_database.feast_online_store,
    google_compute_firewall.online_compose_public,
    google_project_iam_member.online_compose_bigquery_job_user,
    google_project_iam_member.online_compose_bigquery_read_session_user,
    google_project_iam_member.online_compose_datastore_user,
    google_artifact_registry_repository_iam_member.online_compose_reader,
    google_storage_bucket_iam_member.online_compose_bucket_admin,
    google_storage_bucket_iam_member.online_compose_bucket_metadata_reader,
    google_bigquery_dataset_iam_member.online_compose_bigquery_editor,
    google_bigquery_dataset_iam_member.online_compose_monitoring_bigquery_editor,
  ]
}

resource "google_composer_environment" "cloud_composer" {
  count  = var.provision_cloud_composer_environment ? 1 : 0
  name   = var.cloud_composer_environment_name
  region = var.region

  labels = {
    stack   = "foehncast"
    surface = "managed-orchestration"
  }

  config {
    software_config {
      image_version = var.cloud_composer_image_version

      airflow_config_overrides = {
        "core-dags_are_paused_at_creation" = "True"
      }

      env_variables = local.cloud_composer_env_vars
      pypi_packages = local.cloud_composer_pypi_packages
    }

    node_config {
      network         = google_compute_network.cloud_composer[0].id
      subnetwork      = google_compute_subnetwork.cloud_composer[0].id
      service_account = google_service_account.cloud_composer_runtime[0].name
    }
  }

  depends_on = [
    google_project_service.required,
    google_firestore_database.feast_online_store,
    google_project_iam_member.cloud_composer_worker,
    google_service_account_iam_member.cloud_composer_service_agent_extension,
    google_project_iam_member.cloud_composer_bigquery_job_user,
    google_project_iam_member.cloud_composer_bigquery_read_session_user,
    google_project_iam_member.cloud_composer_datastore_user,
    google_artifact_registry_repository_iam_member.cloud_composer_reader,
    google_storage_bucket_iam_member.cloud_composer_bucket_admin,
    google_storage_bucket_iam_member.cloud_composer_bucket_metadata_reader,
    google_bigquery_dataset_iam_member.cloud_composer_bigquery_editor,
    google_secret_manager_secret_iam_member.cloud_composer_secret_accessor,
  ]
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.github_oidc_pool_id
  display_name              = "GitHub Actions"
  description               = "OIDC trust for GitHub Actions deployments"

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.github_oidc_provider_id
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == '${local.github_repository_path}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_workload_identity_user" {
  service_account_id = google_service_account.github_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${local.github_repository_path}"
}
