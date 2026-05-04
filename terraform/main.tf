locals {
  github_repository_path       = "${var.github_owner}/${var.github_repository}"
  cloud_run_image              = var.cloud_run_image != "" ? var.cloud_run_image : "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository_id}/foehncast-app:latest"
  ghcr_registry_owner          = lower(var.github_owner)
  online_compose_app_image     = var.online_compose_app_image != "" ? var.online_compose_app_image : "ghcr.io/${local.ghcr_registry_owner}/foehncast-app:main"
  online_compose_airflow_image = var.online_compose_airflow_image != "" ? var.online_compose_airflow_image : "ghcr.io/${local.ghcr_registry_owner}/foehncast-airflow:main"
  online_compose_mlflow_image  = var.online_compose_mlflow_image != "" ? var.online_compose_mlflow_image : "ghcr.io/${local.ghcr_registry_owner}/foehncast-mlflow:main"
  cloud_run_env_vars = merge(
    {
      GCP_PROJECT_ID              = var.project_id
      GCP_LOCATION                = var.region
      GOOGLE_CLOUD_PROJECT        = var.project_id
      MLFLOW_TRACKING_URI         = var.mlflow_tracking_uri
      STORAGE_BACKEND             = "bigquery"
      STORAGE_BIGQUERY_PROJECT_ID = var.project_id
      STORAGE_BIGQUERY_DATASET    = var.bigquery_dataset_id
      STORAGE_BIGQUERY_TABLE      = var.bigquery_feature_table_id
    },
    var.cloud_run_env_vars,
  )
  online_compose_env_vars = merge(
    {
      APP_BIND_HOST                   = contains(var.online_compose_public_ports, 8000) ? "0.0.0.0" : "127.0.0.1"
      AIRFLOW_BIND_HOST               = contains(var.online_compose_public_ports, 8080) ? "0.0.0.0" : "127.0.0.1"
      MLFLOW_BIND_HOST                = contains(var.online_compose_public_ports, 5001) ? "0.0.0.0" : "127.0.0.1"
      AIRFLOW_CREATE_ADMIN_USER       = "true"
      AIRFLOW_ADMIN_USERNAME          = var.online_compose_airflow_admin_username
      AIRFLOW_ADMIN_FIRSTNAME         = "FoehnCast"
      AIRFLOW_ADMIN_LASTNAME          = "Admin"
      AIRFLOW_ADMIN_ROLE              = "Admin"
      AIRFLOW_ADMIN_EMAIL             = "admin@example.com"
      AIRFLOW_ADMIN_PASSWORD_FILE     = "/workspace/airflow/.admin-password"
      AIRFLOW__WEBSERVER__CONFIG_FILE = "/opt/airflow/webserver_config_cloud.py"
      GCP_PROJECT_ID                  = var.project_id
      GCP_LOCATION                    = var.region
      GCP_BUCKET_NAME                 = var.artifact_bucket_name
      STORAGE_BACKEND                 = "bigquery"
      STORAGE_BIGQUERY_PROJECT_ID     = var.project_id
      STORAGE_BIGQUERY_DATASET        = var.bigquery_dataset_id
      STORAGE_BIGQUERY_TABLE          = var.bigquery_feature_table_id
      FOEHNCAST_APP_IMAGE             = local.online_compose_app_image
      FOEHNCAST_AIRFLOW_IMAGE         = local.online_compose_airflow_image
      FOEHNCAST_MLFLOW_IMAGE          = local.online_compose_mlflow_image
    },
    var.online_compose_env_vars,
  )

  forecast_feature_schema = [
    {
      name        = "forecast_time"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "Hourly forecast timestamp."
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
      name        = "dataset_name"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Logical dataset partition such as train or forecast."
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
      name        = "wind_steadiness"
      type        = "FLOAT"
      mode        = "NULLABLE"
      description = "Rolling coefficient of variation of 10 m wind speed."
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
  ]

  required_services = toset([
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "sts.googleapis.com",
  ])
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

resource "google_service_account" "github_deployer" {
  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions deployer"
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

resource "google_project_iam_member" "cloud_run_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_bigquery_dataset_iam_member" "cloud_run_bigquery_reader" {
  dataset_id = google_bigquery_dataset.feature_store.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.cloud_run_runtime.email}"
}

resource "google_project_iam_member" "online_compose_bigquery_job_user" {
  count = var.provision_online_compose_host ? 1 : 0

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
}

resource "google_bigquery_dataset_iam_member" "online_compose_bigquery_editor" {
  count = var.provision_online_compose_host ? 1 : 0

  dataset_id = google_bigquery_dataset.feature_store.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.online_compose_runtime[0].email}"
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
    google_artifact_registry_repository_iam_member.cloud_run_reader,
    google_storage_bucket_iam_member.cloud_run_bucket_reader,
    google_project_iam_member.cloud_run_bigquery_job_user,
    google_bigquery_dataset_iam_member.cloud_run_bigquery_reader,
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
    stack_env              = local.online_compose_env_vars
  })

  depends_on = [
    google_project_service.required,
    google_compute_firewall.online_compose_public,
    google_project_iam_member.online_compose_bigquery_job_user,
    google_bigquery_dataset_iam_member.online_compose_bigquery_editor,
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
