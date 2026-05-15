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


def test_build_runtime_release_summary_normalizes_deploy_candidate_request() -> None:
    summary = runtime_release.build_runtime_release_summary(
        {
            "action": "DEPLOY_CANDIDATE",
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
    assert summary["runtime_receiver"] == "hosted_airflow"


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
        "runtime_receiver": "hosted_airflow",
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
        "runtime_receiver": "hosted_airflow",
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
