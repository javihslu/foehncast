"""Shared fake BigQuery classes for tests.

Both test_store.py and test_prediction_log.py need lightweight stand-ins for
the google-cloud-bigquery SDK objects. This module provides canonical fakes
so each test file only defines domain-specific helpers.
"""

from __future__ import annotations


class FakeLoadJobConfig:
    def __init__(self, write_disposition: str, **kwargs: object) -> None:
        self.write_disposition = write_disposition
        for name, value in kwargs.items():
            setattr(self, name, value)


class FakeTimePartitioning:
    def __init__(
        self,
        *,
        type_: object,
        field: str,
        expiration_ms: int,
        require_partition_filter: bool,
    ) -> None:
        self.type_ = type_
        self.field = field
        self.expiration_ms = expiration_ms
        self.require_partition_filter = require_partition_filter


class FakeScalarQueryParameter:
    def __init__(self, name: str, param_type: str, value: object) -> None:
        self.name = name
        self.param_type = param_type
        self.value = value


class FakeQueryJobConfig:
    def __init__(self, query_parameters: list[object]) -> None:
        self.query_parameters = query_parameters


class FakeCompletedJob:
    """A job whose .result() immediately returns None."""

    def __init__(self, callback=None) -> None:
        self._callback = callback

    def result(self):
        if self._callback is not None:
            self._callback()
        return None
