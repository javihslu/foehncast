"""Tests for runtime release handoff normalization and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import foehncast.runtime_release as runtime_release


class _FakeStorageBlob:
    def __init__(
        self,
        bucket_name: str,
        object_name: str,
        objects: dict[tuple[str, str], str],
    ) -> None:
        self.bucket_name = bucket_name
        self.name = object_name
        self._objects = objects

    def upload_from_string(
        self,
        data: str,
        *,
        content_type: str | None = None,
    ) -> None:
        del content_type
        self._objects[(self.bucket_name, self.name)] = data

    def exists(self) -> bool:
        return (self.bucket_name, self.name) in self._objects

    def download_as_text(self, *, encoding: str = "utf-8") -> str:
        del encoding
        if not self.exists():
            raise FileNotFoundError(self.name)
        return self._objects[(self.bucket_name, self.name)]


class _FakeStorageBucket:
    def __init__(self, bucket_name: str, objects: dict[tuple[str, str], str]) -> None:
        self.bucket_name = bucket_name
        self._objects = objects

    def blob(self, object_name: str) -> _FakeStorageBlob:
        return _FakeStorageBlob(self.bucket_name, object_name, self._objects)


class _FakeStorageClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], str] = {}

    def bucket(self, bucket_name: str) -> _FakeStorageBucket:
        return _FakeStorageBucket(bucket_name, self.objects)

    def list_blobs(
        self,
        bucket_name: str,
        *,
        prefix: str = "",
    ) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(name=object_name)
            for stored_bucket, object_name in sorted(self.objects)
            if stored_bucket == bucket_name and object_name.startswith(prefix)
        ]


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def test_normalize_runtime_release_request_accepts_json_string_payload() -> None:
    request = runtime_release.normalize_runtime_release_request(
        '{"action": "PROMOTE_CANDIDATE", "candidate_alias": "Candidate"}'
    )

    assert request["action"] == "promote_candidate"
    assert request["candidate_alias"] == "candidate"
    assert request["target_alias"] == "champion"
    assert request["request_source"] == "github-actions"
    assert request["requested_at"]


def test_normalize_runtime_release_request_rejects_non_object_json_payload() -> None:
    with pytest.raises(
        ValueError,
        match="Runtime release request must decode to a JSON object.",
    ):
        runtime_release.normalize_runtime_release_request('["promote_candidate"]')


def test_normalized_runtime_release_request_json_sorts_payload_keys() -> None:
    request_json = runtime_release.normalized_runtime_release_request_json(
        '{"action": "PROMOTE_CANDIDATE", "candidate_alias": "Candidate"}'
    )

    assert json.loads(request_json)["action"] == "promote_candidate"
    assert request_json.index('"action"') < request_json.index('"candidate_alias"')


def test_normalize_runtime_release_request_tracks_airflow_targets() -> None:
    request = runtime_release.normalize_runtime_release_request(
        {
            "action": "promote_candidate",
            "requested_airflow_target": "AUTO",
            "selected_airflow_target": "LOCAL_AIRFLOW",
        }
    )

    assert request["requested_airflow_target"] == "auto"
    assert request["selected_airflow_target"] == "local_airflow"


def test_runtime_release_request_from_env_builds_normalized_payload() -> None:
    request = runtime_release.runtime_release_request_from_env(
        {
            "ACTION": "PROMOTE_CANDIDATE",
            "GITHUB_SERVER_URL": "https://github.com/",
            "GITHUB_REPOSITORY": "javihslu/foehncast",
            "GITHUB_WORKFLOW": "Trigger Runtime Release",
            "GITHUB_RUN_ID": "42",
            "GITHUB_SHA": "abc123",
            "REQUESTED_AIRFLOW_TARGET": "AUTO",
            "AIRFLOW_TARGET": "LOCAL_AIRFLOW",
            "CANDIDATE_ALIAS": "Candidate",
        },
        requested_at="2026-05-16T12:00:00+00:00",
    )

    assert request["action"] == "promote_candidate"
    assert request["requested_at"] == "2026-05-16T12:00:00+00:00"
    assert (
        request["github_run_url"]
        == "https://github.com/javihslu/foehncast/actions/runs/42"
    )
    assert request["requested_airflow_target"] == "auto"
    assert request["selected_airflow_target"] == "local_airflow"
    assert request["candidate_alias"] == "candidate"


def test_write_runtime_release_request_file_persists_normalized_payload(
    tmp_path: Path,
) -> None:
    request_path = runtime_release.write_runtime_release_request_file(
        tmp_path / "runtime-release-request.json",
        environ={
            "ACTION": "DEPLOY_CANDIDATE",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "javihslu/foehncast",
            "GITHUB_WORKFLOW": "Trigger Runtime Release",
            "GITHUB_RUN_ID": "99",
            "GITHUB_SHA": "def456",
            "REQUESTED_AIRFLOW_TARGET": "local_airflow",
            "IMAGE_URI": "europe-west6-docker.pkg.dev/demo/foehncast/foehncast-app:sha-123",
        },
        requested_at="2026-05-16T12:05:00+00:00",
    )

    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["action"] == "deploy_candidate"
    assert request["requested_at"] == "2026-05-16T12:05:00+00:00"
    assert request["requested_airflow_target"] == "local_airflow"
    assert request["selected_airflow_target"] == "local_airflow"
    assert request["image_uri"]


def test_main_write_request_from_env_writes_request_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ACTION", "PROMOTE_CANDIDATE")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "javihslu/foehncast")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Trigger Runtime Release")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "abc123")

    request_path = tmp_path / "runtime-release-request.json"

    exit_code = runtime_release.main(
        [
            "write-request-from-env",
            "--output-file",
            str(request_path),
        ]
    )

    assert exit_code == 0
    assert (
        json.loads(request_path.read_text(encoding="utf-8"))["action"]
        == "promote_candidate"
    )


def test_main_normalize_request_prints_normalized_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "runtime-release-request.json"
    request_path.write_text(
        json.dumps(
            {
                "action": "PROMOTE_CANDIDATE",
                "requested_airflow_target": "AUTO",
                "selected_airflow_target": "Local_Airflow",
                "candidate_alias": "Candidate",
                "target_alias": "Champion",
                "github_repository": "javihslu/foehncast",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = runtime_release.main(
        [
            "normalize-request",
            "--request-file",
            str(request_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "promote_candidate"
    assert payload["requested_airflow_target"] == "auto"
    assert payload["selected_airflow_target"] == "local_airflow"
    assert payload["candidate_alias"] == "candidate"
    assert payload["target_alias"] == "champion"


def test_main_normalize_request_reports_validation_errors_on_stderr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_path = tmp_path / "runtime-release-request.json"
    request_path.write_text(json.dumps(["promote_candidate"]) + "\n", encoding="utf-8")

    exit_code = runtime_release.main(
        [
            "normalize-request",
            "--request-file",
            str(request_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Runtime release request must decode to a JSON object." in captured.err


def test_main_verify_report_prints_local_verified_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runtime_release, "project_root", lambda: tmp_path)
    report_path = tmp_path / "airflow" / "reports" / "runtime-release-latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"dag_run_id": "runtime_release__ok"}) + "\n",
        encoding="utf-8",
    )

    exit_code = runtime_release.main(
        [
            "verify-report",
            "--expected-run-id",
            "runtime_release__ok",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dag_run_id"] == "runtime_release__ok"
    assert payload["report_path"] == str(report_path)


def test_main_verify_report_reports_missing_summary_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runtime_release, "project_root", lambda: tmp_path)

    exit_code = runtime_release.main(
        [
            "verify-report",
            "--expected-run-id",
            "runtime_release__missing",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "Runtime release report was not written to" in captured.err


def test_main_verify_report_reports_mismatched_run_id_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runtime_release, "project_root", lambda: tmp_path)
    report_path = tmp_path / "airflow" / "reports" / "runtime-release-latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"dag_run_id": "runtime_release__actual"}) + "\n",
        encoding="utf-8",
    )

    exit_code = runtime_release.main(
        [
            "verify-report",
            "--expected-run-id",
            "runtime_release__expected",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert (
        "runtime release report does not match dag run 'runtime_release__expected'"
        in captured.err
    )


def test_main_verify_report_prints_gcs_verified_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_storage = _FakeStorageClient()
    fake_storage.objects[
        ("demo-bucket", "airflow/reports/runtime-release-latest.json")
    ] = json.dumps({"dag_run_id": "runtime_release__ok"}) + "\n"
    monkeypatch.setattr(runtime_release, "_new_storage_client", lambda: fake_storage)
    monkeypatch.setenv(
        "FOEHNCAST_RUNTIME_RELEASE_REPORT_PATH",
        "gs://demo-bucket/airflow/reports/runtime-release-latest.json",
    )

    exit_code = runtime_release.main(
        [
            "verify-report",
            "--expected-run-id",
            "runtime_release__ok",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dag_run_id"] == "runtime_release__ok"
    assert (
        payload["report_path"]
        == "gs://demo-bucket/airflow/reports/runtime-release-latest.json"
    )


def test_build_runtime_release_summary_normalizes_deploy_candidate_request() -> None:
    summary = runtime_release.build_runtime_release_summary(
        {
            "action": "DEPLOY_CANDIDATE",
            "requested_airflow_target": "auto",
            "selected_airflow_target": "local_airflow",
            "image_uri": "europe-west6-docker.pkg.dev/demo/foehncast/foehncast-app:sha-123",
            "candidate_revision_tag": "Candidate",
            "candidate_alias": "Candidate",
            "target_alias": "Champion",
            "request_source": "github-actions",
            "github_repository": "javihslu/foehncast",
        },
        dag_run_id="runtime_release__2026-05-14T10-00-00Z",
    )

    assert summary["action"] == "deploy_candidate"
    assert (
        summary["image_uri"]
        == "europe-west6-docker.pkg.dev/demo/foehncast/foehncast-app:sha-123"
    )
    assert summary["candidate_revision_tag"] == "candidate"
    assert summary["candidate_alias"] == "candidate"
    assert summary["target_alias"] == "champion"
    assert summary["dag_id"] == "runtime_release"
    assert summary["dag_run_id"] == "runtime_release__2026-05-14T10-00-00Z"
    assert summary["runtime_receiver"] == "airflow_api"
    assert summary["requested_airflow_target"] == "auto"
    assert summary["selected_airflow_target"] == "local_airflow"


def test_build_runtime_release_summary_requires_rollback_coordinates() -> None:
    with pytest.raises(ValueError):
        runtime_release.build_runtime_release_summary(
            {"action": "rollback_live", "rollback_revision": "candidate"},
            dag_run_id="runtime_release__rollback",
        )


def test_write_runtime_release_summary_persists_latest_and_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runtime_release, "project_root", lambda: tmp_path)

    summary = {
        "generated_at": "2026-05-14T11:00:00+00:00",
        "state": "accepted",
        "runtime_receiver": "airflow_api",
        "requested_airflow_target": "auto",
        "selected_airflow_target": "local_airflow",
        "dag_id": "runtime_release",
        "dag_run_id": "runtime_release__2026-05-14T11-00-00Z",
        "action": "promote_candidate",
        "request_source": "github-actions",
        "github_repository": "javihslu/foehncast",
        "github_workflow": "Trigger Runtime Release",
        "github_run_id": "42",
        "github_run_url": "https://github.com/javihslu/foehncast/actions/runs/42",
        "github_sha": "abc123",
        "image_uri": "",
        "candidate_revision_tag": "candidate",
        "candidate_alias": "candidate",
        "target_alias": "champion",
        "rollback_revision": "",
        "rollback_model_version": "",
        "rollback_revision_tag": "rollback",
    }

    latest_path = runtime_release.write_runtime_release_summary(summary)

    assert (
        latest_path == tmp_path / "airflow" / "reports" / "runtime-release-latest.json"
    )
    assert (
        _read_json(latest_path)["dag_run_id"] == "runtime_release__2026-05-14T11-00-00Z"
    )
    assert _read_json(latest_path)["selected_airflow_target"] == "local_airflow"
    history_paths = runtime_release.runtime_release_summary_history_paths()
    assert len(history_paths) == 1
    assert history_paths[0].name == "runtime-release-20260514T110000000000Z.json"
    assert _read_json(history_paths[0])["action"] == "promote_candidate"


def test_verify_runtime_release_summary_adds_report_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(runtime_release, "project_root", lambda: tmp_path)
    report_path = tmp_path / "airflow" / "reports" / "runtime-release-latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"dag_run_id": "runtime_release__ok"}) + "\n",
        encoding="utf-8",
    )

    summary = runtime_release.verify_runtime_release_summary("runtime_release__ok")

    assert summary["dag_run_id"] == "runtime_release__ok"
    assert summary["report_path"] == str(report_path)


def test_write_runtime_release_summary_supports_gcs_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = _FakeStorageClient()
    monkeypatch.setattr(runtime_release, "_new_storage_client", lambda: fake_storage)
    monkeypatch.setenv(
        "FOEHNCAST_RUNTIME_RELEASE_REPORT_PATH",
        "gs://demo-bucket/airflow/reports/runtime-release-latest.json",
    )

    summary = {
        "generated_at": "2026-05-14T11:00:00+00:00",
        "state": "accepted",
        "runtime_receiver": "airflow_api",
        "requested_airflow_target": "auto",
        "selected_airflow_target": "local_airflow",
        "dag_id": "runtime_release",
        "dag_run_id": "runtime_release__2026-05-14T11-00-00Z",
        "action": "promote_candidate",
        "request_source": "github-actions",
        "github_repository": "javihslu/foehncast",
        "github_workflow": "Trigger Runtime Release",
        "github_run_id": "42",
        "github_run_url": "https://github.com/javihslu/foehncast/actions/runs/42",
        "github_sha": "abc123",
        "image_uri": "",
        "candidate_revision_tag": "candidate",
        "candidate_alias": "candidate",
        "target_alias": "champion",
        "rollback_revision": "",
        "rollback_model_version": "",
        "rollback_revision_tag": "rollback",
    }

    latest_path = runtime_release.write_runtime_release_summary(summary)

    assert latest_path == "gs://demo-bucket/airflow/reports/runtime-release-latest.json"
    assert (
        json.loads(
            fake_storage.objects[
                ("demo-bucket", "airflow/reports/runtime-release-latest.json")
            ]
        )["dag_run_id"]
        == "runtime_release__2026-05-14T11-00-00Z"
    )
    assert runtime_release.runtime_release_summary_history_paths() == [
        "gs://demo-bucket/airflow/reports/history/runtime-release-20260514T110000000000Z.json"
    ]


def test_verify_runtime_release_summary_adds_gcs_report_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_storage = _FakeStorageClient()
    fake_storage.objects[
        ("demo-bucket", "airflow/reports/runtime-release-latest.json")
    ] = json.dumps({"dag_run_id": "runtime_release__ok"}) + "\n"
    monkeypatch.setattr(runtime_release, "_new_storage_client", lambda: fake_storage)
    monkeypatch.setenv(
        "FOEHNCAST_RUNTIME_RELEASE_REPORT_PATH",
        "gs://demo-bucket/airflow/reports/runtime-release-latest.json",
    )

    summary = runtime_release.verify_runtime_release_summary("runtime_release__ok")

    assert summary["dag_run_id"] == "runtime_release__ok"
    assert (
        summary["report_path"]
        == "gs://demo-bucket/airflow/reports/runtime-release-latest.json"
    )
