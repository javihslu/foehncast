"""Tests for the deployment parity comparison."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from foehncast.inference_pipeline import parity

_SPOTS = [
    {
        "id": "silvaplana",
        "name": "Silvaplana",
        "lat": 46.45,
        "lon": 9.79,
        "shore_orientation_deg": 220,
    },
    {
        "id": "urnersee",
        "name": "Urnersee",
        "lat": 46.93,
        "lon": 8.6,
        "shore_orientation_deg": 190,
    },
]

_HEALTH = {"status": "healthy", "model_alias": "champion", "model_version": "3"}

_PREDICT = {
    "model_version": "3",
    "predictions": [
        {
            "spot_id": "silvaplana",
            "spot_name": "Silvaplana",
            "forecast": [
                {"time": "2026-05-10T12:00:00", "quality_index": 3.5},
                {"time": "2026-05-10T13:00:00", "quality_index": 4.0},
            ],
        },
        {
            "spot_id": "urnersee",
            "spot_name": "Urnersee",
            "forecast": [{"time": "2026-05-10T12:00:00", "quality_index": 1.25}],
        },
    ],
}

_RANK = {
    "model_version": "3",
    "ranked_spots": [
        {
            "spot_id": "silvaplana",
            "spot_name": "Silvaplana",
            "quality_index": 4.0,
            "drive_minutes": 120.0,
            "session_hours": 2.0,
            "ride_drive_ratio": 4.0,
            "score": 0.9,
        },
        {
            "spot_id": "urnersee",
            "spot_name": "Urnersee",
            "quality_index": 1.25,
            "drive_minutes": 45.0,
            "session_hours": 1.0,
            "ride_drive_ratio": 1.6,
            "score": 0.2,
        },
    ],
}


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    """Serves canned payloads per base URL, and records what was asked."""

    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def _lookup(self, url: str, body: dict[str, Any] | None) -> _FakeResponse:
        self.calls.append((url, body))
        endpoint = url.rsplit("/", 1)[-1]
        return _FakeResponse(self.payloads[_side(url)][endpoint])

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._lookup(url, None)

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._lookup(url, kwargs.get("json"))


def _side(url: str) -> str:
    return "left" if url.startswith("http://left") else "right"


def _payload_set() -> dict[str, Any]:
    return {
        "spots": copy.deepcopy(_SPOTS),
        "health": copy.deepcopy(_HEALTH),
        "predict": copy.deepcopy(_PREDICT),
        "rank": copy.deepcopy(_RANK),
    }


def _session(right: dict[str, Any] | None = None) -> _FakeSession:
    return _FakeSession({"left": _payload_set(), "right": right or _payload_set()})


def test_training_window_is_validated_and_has_no_default() -> None:
    assert parity.asserted_training_window("2025-01-01", "2026-05-10") == (
        "2025-01-01..2026-05-10"
    )
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parity.asserted_training_window("01/01/2025", "2026-05-10")
    with pytest.raises(ValueError, match="starts after it ends"):
        parity.asserted_training_window("2026-05-10", "2025-01-01")


def test_identical_deployments_agree_and_report_the_window() -> None:
    report = parity.run(
        _session(),
        "http://left",
        "http://right",
        training_window="2025-01-01..2026-05-10",
    )

    assert report.agrees
    assert report.differences == []
    assert report.metrics["predict"]["hours_compared"] == 3
    assert "2025-01-01..2026-05-10" in parity.render(report)


def test_both_deployments_are_asked_about_the_same_spots() -> None:
    right = _payload_set()
    right["spots"].append(
        {"id": "thunersee", "name": "Thunersee", "lat": 46.7, "lon": 7.7}
    )
    session = _session(right)

    report = parity.run(
        session, "http://left", "http://right", training_window="2025-01-01..2026-05-10"
    )

    requested = [body["spot_ids"] for _, body in session.calls if body is not None]
    assert requested == [["silvaplana", "urnersee"]] * 4
    assert report.metrics["spots_requested"] == ["silvaplana", "urnersee"]
    assert any("thunersee" in difference for difference in report.differences)


def test_quality_index_gap_beyond_tolerance_is_a_disagreement() -> None:
    right = _payload_set()
    right["predict"]["predictions"][0]["forecast"][1]["quality_index"] = 4.4

    report = parity.run(
        _session(right), "http://left", "http://right", training_window="w"
    )

    assert not report.agrees
    assert any("quality_index differs" in item for item in report.differences)
    assert report.metrics["predict"]["max_quality_index_delta"] == pytest.approx(0.4)


def test_rolled_forecast_hours_are_counted_not_failed() -> None:
    right = _payload_set()
    right["predict"]["predictions"][0]["forecast"].append(
        {"time": "2026-05-10T14:00:00", "quality_index": 4.2}
    )

    differences, metrics = parity.compare_predictions(_PREDICT, right["predict"])

    assert differences == []
    assert metrics["unmatched_hours"] == {"baseline": 0, "candidate": 1}
    assert metrics["hours_compared"] == 3


def test_no_shared_forecast_hour_is_a_disagreement() -> None:
    right = _payload_set()
    for prediction in right["predict"]["predictions"]:
        for hour in prediction["forecast"]:
            hour["time"] = hour["time"].replace("2026-05-10", "2026-05-11")

    differences, _ = parity.compare_predictions(_PREDICT, right["predict"])

    assert len(differences) == 2
    assert all("no forecast hour covered by both" in item for item in differences)


def test_ranking_order_and_scores_are_compared() -> None:
    right = copy.deepcopy(_RANK)
    right["ranked_spots"].reverse()
    right["ranked_spots"][0]["score"] = 0.25

    differences, metrics = parity.compare_rankings(_RANK, right)

    assert any(item.startswith("/rank order:") for item in differences)
    assert any(".score:" in item for item in differences)
    assert metrics["max_deltas"]["score"] == pytest.approx(0.05)


def test_model_version_is_context_but_status_is_not() -> None:
    unhealthy = {"status": "degraded", "model_alias": "champion", "model_version": "9"}

    assert parity.compare_health(_HEALTH, {**_HEALTH, "model_version": "9"}) == []
    assert parity.compare_health(_HEALTH, unhealthy) != []


def test_report_serialises_for_machine_readers() -> None:
    report = parity.run(
        _session(),
        "http://left",
        "http://right",
        training_window="2025-01-01..2026-05-10",
    )
    payload = report.as_dict()

    assert payload["agrees"] is True
    assert payload["training_window"] == "2025-01-01..2026-05-10"
    assert payload["context"]["baseline"]["model_version"] == "3"
