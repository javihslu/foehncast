locals {
  github_repository_path = "${var.github_owner}/${var.github_repository}"
  pipeline_job_names = {
    feature   = "foehncast-feature-pipeline"
    training  = "foehncast-training-pipeline"
    inference = "foehncast-inference-pipeline"
    drift     = "foehncast-drift-detection"
  }
  artifact_registry_host            = "${var.region}-docker.pkg.dev"
  artifact_registry_repository_path = "${local.artifact_registry_host}/${var.project_id}/${var.artifact_registry_repository_id}"
  cloud_run_image                   = var.cloud_run_image != "" ? var.cloud_run_image : "${local.artifact_registry_repository_path}/foehncast-app:latest"
  cloud_run_ui_image                = var.cloud_run_ui_image != "" ? var.cloud_run_ui_image : "${local.artifact_registry_repository_path}/foehncast-ui:latest"
  cloud_run_mlflow_image            = var.cloud_run_mlflow_image != "" ? var.cloud_run_mlflow_image : "${local.artifact_registry_repository_path}/foehncast-mlflow:latest"
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
      FOEHNCAST_STATE_DIR                  = "gs://${var.artifact_bucket_name}/state"
    },
    var.cloud_run_env_vars,
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
    "compute.googleapis.com",
    "container.googleapis.com",
    "developerconnect.googleapis.com",
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

# Cloud Build 2nd-gen connection links the GitHub repo to GCP for triggers.
# Created by scripts/setup-cloud-triggers.sh (gcloud + OAuth flow) and imported.
resource "google_cloudbuildv2_connection" "github" {
  count    = var.provision_cloud_build_triggers ? 1 : 0
  location = var.region
  name     = "foehncast-github"

  github_config {
    app_installation_id = var.github_app_installation_id
  }

  # Connection is created by setup script and imported into state.
  lifecycle {
    ignore_changes = [github_config]
  }

  depends_on = [google_project_service.required]
}

resource "google_cloudbuildv2_repository" "foehncast" {
  count             = var.provision_cloud_build_triggers ? 1 : 0
  location          = var.region
  name              = "foehncast"
  parent_connection = google_cloudbuildv2_connection.github[0].name
  remote_uri        = "https://github.com/${var.github_owner}/${var.github_repository}.git"

  depends_on = [google_cloudbuildv2_connection.github]
}

# Cloud Build triggers — replace GitHub Actions publish-images.yml.
# Each trigger watches specific paths and builds the corresponding image.
resource "google_cloudbuild_trigger" "publish_app" {
  count           = var.provision_cloud_build_triggers ? 1 : 0
  name            = "publish-app"
  location        = var.region
  service_account = google_service_account.cloud_build.id

  repository_event_config {
    repository = google_cloudbuildv2_repository.foehncast[0].id
    push {
      branch = "^main$"
    }
  }

  included_files = ["src/**", "containers/app/**", "cloudbuild/app.yaml", "pyproject.toml", "uv.lock"]
  filename       = "cloudbuild/app.yaml"

  substitutions = {
    _REGION           = var.region
    _IMAGE_REPOSITORY = "${local.artifact_registry_repository_path}/foehncast-app"
    _SERVICE_NAME     = var.cloud_run_service_name
    _FEATURE_JOB      = local.pipeline_job_names.feature
    _TRAINING_JOB     = local.pipeline_job_names.training
    _INFERENCE_JOB    = local.pipeline_job_names.inference
    _DRIFT_JOB        = local.pipeline_job_names.drift
  }

  depends_on = [google_project_service.required]
}



resource "google_cloudbuild_trigger" "publish_mlflow" {
  count           = var.provision_cloud_build_triggers ? 1 : 0
  name            = "publish-mlflow"
  location        = var.region
  service_account = google_service_account.cloud_build.id

  repository_event_config {
    repository = google_cloudbuildv2_repository.foehncast[0].id
    push {
      branch = "^main$"
    }
  }

  included_files = ["containers/mlflow/**", "cloudbuild/mlflow.yaml"]
  filename       = "cloudbuild/mlflow.yaml"

  substitutions = {
    _REGION           = var.region
    _IMAGE_REPOSITORY = "${local.artifact_registry_repository_path}/foehncast-mlflow"
    _SERVICE_NAME     = var.cloud_run_mlflow_service_name
  }

  depends_on = [google_project_service.required]
}

resource "google_cloudbuild_trigger" "publish_ui" {
  count           = var.provision_cloud_build_triggers ? 1 : 0
  name            = "publish-ui"
  location        = var.region
  service_account = google_service_account.cloud_build.id

  repository_event_config {
    repository = google_cloudbuildv2_repository.foehncast[0].id
    push {
      branch = "^main$"
    }
  }

  included_files = ["ui/**", "containers/ui/**", "cloudbuild/ui.yaml", "pyproject.toml", "uv.lock"]
  filename       = "cloudbuild/ui.yaml"

  substitutions = {
    _REGION           = var.region
    _IMAGE_REPOSITORY = "${local.artifact_registry_repository_path}/foehncast-ui"
    _SERVICE_NAME     = var.cloud_run_ui_service_name
  }

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
    "roles/cloudscheduler.admin",
    "roles/cloudsql.admin",
    "roles/compute.admin",
    "roles/datastore.owner",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/storage.admin",
    "roles/workflows.admin",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_service_account" "cloud_run_runtime" {
  account_id   = "foehncast-cloud-run"
  display_name = "FoehnCast Cloud Run runtime"
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

# Dedicated Cloud Build SA — builds run as this SA via --service-account.
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

resource "google_project_iam_member" "cloud_build_sa_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_service_account_iam_member" "cloud_build_act_as_runtime" {
  service_account_id = google_service_account.cloud_run_runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloud_build.email}"
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

resource "google_storage_bucket_iam_member" "cloud_run_bucket_writer" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
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
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_bigquery_dataset_iam_member" "cloud_run_monitoring_bigquery_editor" {
  dataset_id = google_bigquery_dataset.monitoring_store.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
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

      startup_probe {
        http_get {
          path = "/health"
          port = var.cloud_run_container_port
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 6
        timeout_seconds       = 5
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = var.cloud_run_container_port
        }
        period_seconds = 30
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

    disk_size       = 10
    disk_type       = "PD_HDD"
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
      min_instance_count = 1
      max_instance_count = 3
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
          cpu    = "2"
          memory = "4Gi"
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

      startup_probe {
        http_get {
          path = "/health"
          port = 5001
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 5
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 5001
        }
        period_seconds = 30
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
      min_instance_count = 1
      max_instance_count = 3
    }

    containers {
      image = local.cloud_run_ui_image

      ports {
        container_port = 8501
      }

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

      env {
        name = "FOEHNCAST_PROMETHEUS_URL"
        # Empty override falls back to serve's own PromQL facade.
        value = var.cloud_run_ui_prometheus_url != "" ? var.cloud_run_ui_prometheus_url : (var.provision_cloud_run_service ? google_cloud_run_v2_service.app[0].uri : "")
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCP_LOCATION"
        value = var.region
      }

      env {
        name  = "FOEHNCAST_UI_OPERATOR_TOKEN"
        value = var.ui_operator_token
      }

      startup_probe {
        http_get {
          path = "/_stcore/health"
          port = 8501
        }
        initial_delay_seconds = 10
        period_seconds        = 10
        failure_threshold     = 5
      }

      liveness_probe {
        http_get {
          path = "/_stcore/health"
          port = 8501
        }
        period_seconds = 30
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

resource "google_cloud_run_v2_job" "feature_pipeline" {
  count    = var.provision_cloud_workflows ? 1 : 0
  name     = local.pipeline_job_names.feature
  location = var.region

  deletion_protection = false

  template {
    template {
      service_account = google_service_account.cloud_run_runtime.email
      timeout         = "600s"
      max_retries     = 1

      containers {
        image = local.cloud_run_image

        command = ["python", "-c"]
        args    = ["from foehncast.orchestration import run_feature_pipeline_job; run_feature_pipeline_job(dataset='forecast')"]

        resources {
          limits = {
            cpu    = "4"
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

resource "google_cloud_run_v2_job" "training_pipeline" {
  count    = var.provision_cloud_workflows ? 1 : 0
  name     = local.pipeline_job_names.training
  location = var.region

  deletion_protection = false

  template {
    template {
      service_account = google_service_account.cloud_run_runtime.email
      timeout         = "900s"
      max_retries     = 0

      containers {
        image = local.cloud_run_image

        command = ["python", "-c"]
        args    = ["from foehncast.orchestration import run_training_pipeline_step, evaluate_training_run, register_training_run; run_id = run_training_pipeline_step(dataset='train'); evaluate_training_run(run_id, dataset='train', requested_stage='Production'); register_training_run(run_id, stage='Production', dataset='train')"]

        resources {
          limits = {
            cpu    = "4"
            memory = "8Gi"
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
  name     = local.pipeline_job_names.inference
  location = var.region

  deletion_protection = false

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

resource "google_cloud_run_v2_job" "drift_detection" {
  count    = var.provision_cloud_workflows ? 1 : 0
  name     = local.pipeline_job_names.drift
  location = var.region

  deletion_protection = false

  template {
    template {
      service_account = google_service_account.cloud_run_runtime.email
      timeout         = "300s"
      max_retries     = 1

      containers {
        image = local.cloud_run_image

        command = ["python", "-c"]
        args    = ["from foehncast.orchestration import run_feature_drift_detection_step, run_prediction_drift_detection_step; run_feature_drift_detection_step(dataset='forecast', reference_dataset='train'); run_prediction_drift_detection_step()"]

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

resource "google_cloud_scheduler_job" "drift_detection" {
  count = var.provision_cloud_workflows ? 1 : 0

  name             = local.pipeline_job_names.drift
  description      = "Run drift detection every 12 hours"
  schedule         = "0 */12 * * *"
  time_zone        = "Europe/Zurich"
  attempt_deadline = "30s"
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${local.pipeline_job_names.drift}:run"

    oauth_token {
      service_account_email = google_service_account.workflows[0].email
    }
  }

  depends_on = [
    google_project_service.required,
    google_cloud_run_v2_job.drift_detection,
  ]
}

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

resource "google_project_iam_member" "workflows_log_writer" {
  count = var.provision_cloud_workflows ? 1 : 0

  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.workflows[0].email}"
}

# The workflow SA needs workflows.invoker to allow Cloud Scheduler to create executions.
resource "google_project_iam_member" "workflows_invoker" {
  count = var.provision_cloud_workflows ? 1 : 0

  project = var.project_id
  role    = "roles/workflows.invoker"
  member  = "serviceAccount:${google_service_account.workflows[0].email}"
}

# Cloud Scheduler service agent must be able to impersonate the workflows SA to mint OAuth tokens.
resource "google_service_account_iam_member" "scheduler_act_as_workflows" {
  count = var.provision_cloud_workflows ? 1 : 0

  service_account_id = google_service_account.workflows[0].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
}

resource "google_workflows_workflow" "pipeline_cascade" {
  count = var.provision_cloud_workflows ? 1 : 0

  name                = "foehncast-pipeline-cascade"
  region              = var.region
  description         = "FoehnCast FTI pipeline cascade: feature → training → inference"
  service_account     = google_service_account.workflows[0].id
  deletion_protection = false

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
              name: projects/${var.project_id}/locations/${var.region}/jobs/${local.pipeline_job_names.feature}
            result: feature_result

        - log_feature_done:
            call: sys.log
            args:
              text: "Feature pipeline completed"
              severity: INFO

        - run_training_pipeline:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: projects/${var.project_id}/locations/${var.region}/jobs/${local.pipeline_job_names.training}
            result: training_result

        - log_training_done:
            call: sys.log
            args:
              text: "Training pipeline completed"
              severity: INFO

        - run_inference_pipeline:
            call: googleapis.run.v2.projects.locations.jobs.run
            args:
              name: projects/${var.project_id}/locations/${var.region}/jobs/${local.pipeline_job_names.inference}
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
