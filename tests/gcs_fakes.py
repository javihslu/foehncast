"""Shared fake GCS storage classes for tests.

Several test modules need lightweight stand-ins for the google-cloud-storage
SDK objects. This module provides canonical fakes so each test file only
defines domain-specific helpers.
"""

from __future__ import annotations

from types import SimpleNamespace


class FakeStorageBlob:
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


class FakeStorageBucket:
    def __init__(self, bucket_name: str, objects: dict[tuple[str, str], str]) -> None:
        self.bucket_name = bucket_name
        self._objects = objects

    def blob(self, object_name: str) -> FakeStorageBlob:
        return FakeStorageBlob(self.bucket_name, object_name, self._objects)


class FakeStorageClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], str] = {}

    def bucket(self, bucket_name: str) -> FakeStorageBucket:
        return FakeStorageBucket(bucket_name, self.objects)

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
