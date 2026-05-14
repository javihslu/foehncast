#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUEST_FILE=""
DAG_ID="runtime_release"

usage() {
  echo "Usage: $0 --request-file path" >&2
}

verify_airflow_api_health() {
  local max_attempts="${1:-60}"
  local sleep_seconds="${2:-2}"
  local payload=""
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if payload="$(curl --retry 1 --retry-all-errors --retry-delay 0 -fsS "http://127.0.0.1:8080/api/v2/monitor/health" 2>/dev/null)"; then
      if printf '%s' "$payload" | python3 -c $'import json, sys\npayload = json.load(sys.stdin)\nrequired = ("metadatabase", "scheduler", "dag_processor", "triggerer")\nfor name in required:\n    status = (payload.get(name) or {}).get("status")\n    if status != "healthy":\n        raise SystemExit(1)\n'; then
        return 0
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "Timed out waiting for Airflow API health." >&2
  if [[ -n "$payload" ]]; then
    printf '%s\n' "$payload" >&2
  fi
  return 1
}

wait_for_airflow_dag_run_state() {
  local dag_id="$1"
  local dag_run_id="$2"
  local expected_state="$3"
  local max_attempts="${4:-120}"
  local sleep_seconds="${5:-2}"
  local payload=""
  local status
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if payload="$(curl --retry 1 --retry-all-errors --retry-delay 0 -fsS "http://127.0.0.1:8080/api/v2/dags/${dag_id}/dagRuns?limit=20&order_by=-start_date" 2>/dev/null)"; then
      if printf '%s' "$payload" | EXPECTED_RUN_ID="$dag_run_id" EXPECTED_STATE="$expected_state" python3 -c $'import json, os, sys\npayload = json.load(sys.stdin)\nexpected_run_id = os.environ["EXPECTED_RUN_ID"]\nexpected_state = os.environ["EXPECTED_STATE"].lower()\nruns = payload.get("dag_runs") or []\nfor run in runs:\n    if (run.get("dag_run_id") or "") != expected_run_id:\n        continue\n    state = (run.get("state") or "").lower()\n    if state == expected_state:\n        raise SystemExit(0)\n    if state in {"failed", "error"}:\n        print(json.dumps(run), file=sys.stderr)\n        raise SystemExit(2)\n    raise SystemExit(1)\nraise SystemExit(1)\n'; then
        return 0
      else
        status=$?
        if [[ "$status" -eq 2 ]]; then
          echo "Airflow DAG '${dag_id}' reached a terminal failure state." >&2
          printf '%s\n' "$payload" >&2
          return 1
        fi
      fi
    fi

    sleep "$sleep_seconds"
  done

  echo "Timed out waiting for Airflow DAG '${dag_id}' run '${dag_run_id}' to reach state '${expected_state}'." >&2
  if [[ -n "$payload" ]]; then
    printf '%s\n' "$payload" >&2
  fi
  return 1
}

normalize_request_payload() {
  python3 -c $'import json, sys\nfrom datetime import UTC, datetime\n\npayload = json.load(open(sys.argv[1], encoding="utf-8"))\nif not isinstance(payload, dict):\n    raise SystemExit("Runtime release request must be a JSON object.")\n\ndef clean(name, default=""):\n    value = payload.get(name, default)\n    if value is None:\n        return default\n    value = str(value).strip()\n    return value or default\n\naction = clean("action").lower()\nif action not in {"deploy_candidate", "promote_candidate", "rollback_live"}:\n    raise SystemExit("action must be deploy_candidate, promote_candidate, or rollback_live.")\n\nnormalized = {\n    "action": action,\n    "request_source": clean("request_source", "github-actions"),\n    "requested_at": clean("requested_at", datetime.now(tz=UTC).isoformat()),\n    "github_repository": clean("github_repository"),\n    "github_workflow": clean("github_workflow"),\n    "github_run_id": clean("github_run_id"),\n    "github_run_url": clean("github_run_url"),\n    "github_sha": clean("github_sha"),\n    "image_uri": clean("image_uri"),\n    "candidate_revision_tag": clean("candidate_revision_tag", "candidate").lower(),\n    "candidate_alias": clean("candidate_alias", "candidate").lower(),\n    "target_alias": clean("target_alias", "champion").lower(),\n    "rollback_revision": clean("rollback_revision"),\n    "rollback_model_version": clean("rollback_model_version"),\n    "rollback_revision_tag": clean("rollback_revision_tag", "rollback").lower(),\n}\n\nif action == "deploy_candidate" and not normalized["image_uri"]:\n    raise SystemExit("deploy_candidate requests require image_uri.")\nif action == "rollback_live" and not normalized["rollback_revision"]:\n    raise SystemExit("rollback_live requests require rollback_revision.")\nif action == "rollback_live" and not normalized["rollback_model_version"]:\n    raise SystemExit("rollback_live requests require rollback_model_version.")\n\nprint(json.dumps(normalized, sort_keys=True))\n' "$REQUEST_FILE"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --request-file)
      REQUEST_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$REQUEST_FILE" || ! -f "$REQUEST_FILE" ]]; then
  usage
  exit 1
fi

normalized_request="$(normalize_request_payload)"
dag_run_id="runtime_release__$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
logical_date="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
compose_args=(
  -f "$ROOT_DIR/docker-compose.yml"
  -f "$ROOT_DIR/docker-compose.cloud.yml"
  --env-file "$ROOT_DIR/.env"
)

verify_airflow_api_health 90 2 >&2

docker compose "${compose_args[@]}" exec -T airflow-webserver \
  airflow dags trigger "$DAG_ID" \
  --logical-date "$logical_date" \
  --run-id "$dag_run_id" \
  --conf "$normalized_request" >/dev/null

wait_for_airflow_dag_run_state "$DAG_ID" "$dag_run_id" success 120 2 >&2

report_path="$ROOT_DIR/airflow/reports/runtime-release-latest.json"
if [[ ! -f "$report_path" ]]; then
  echo "Runtime release report was not written to $report_path." >&2
  exit 1
fi

python3 -c $'import json, sys\nreport_path = sys.argv[1]\nexpected_run_id = sys.argv[2]\nreport = json.load(open(report_path, encoding="utf-8"))\nif report.get("dag_run_id") != expected_run_id:\n    raise SystemExit(f"runtime release report does not match dag run {expected_run_id!r}")\nreport["report_path"] = report_path\nprint(json.dumps(report, indent=2, sort_keys=True))\n' "$report_path" "$dag_run_id"
