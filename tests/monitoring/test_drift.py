"""Tests for drift detection helpers."""

from __future__ import annotations

from pathlib import Path
import socket

import pandas as pd
import pytest

from foehncast.monitoring import drift


def _sample_evidently_metrics() -> list[dict[str, object]]:
    return [
        {
            "metric_name": "DriftedColumnsCount(drift_share=0.25)",
            "config": {
                "type": "evidently:metric_v2:DriftedColumnsCount",
                "drift_share": 0.25,
            },
            "value": {"count": 1.0, "share": 0.5},
        },
        {
            "metric_name": "ValueDrift(column=wind_speed_10m,method=ks p_value,threshold=0.05)",
            "config": {
                "type": "evidently:metric_v2:ValueDrift",
                "column": "wind_speed_10m",
                "method": "ks p_value",
                "threshold": 0.05,
            },
            "value": 0.01,
        },
        {
            "metric_name": "ValueDrift(column=temperature_2m,method=ks p_value,threshold=0.05)",
            "config": {
                "type": "evidently:metric_v2:ValueDrift",
                "column": "temperature_2m",
                "method": "ks p_value",
                "threshold": 0.05,
            },
            "value": 0.6,
        },
    ]


def test_detect_data_drift_uses_config_threshold_and_parses_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        reference_frame: pd.DataFrame,
        current_frame: pd.DataFrame,
        threshold: float,
    ) -> list[dict[str, object]]:
        captured["reference_columns"] = list(reference_frame.columns)
        captured["current_columns"] = list(current_frame.columns)
        captured["threshold"] = threshold
        return _sample_evidently_metrics()

    monkeypatch.setattr(drift, "_run_evidently_data_drift", fake_run)
    monkeypatch.setattr(
        drift,
        "get_monitoring_config",
        lambda: {"drift_threshold": 0.25, "evaluation_window_days": 30},
    )

    reference_df = pd.DataFrame(
        {"wind_speed_10m": [1.0, 2.0], "temperature_2m": [5.0, 6.0]}
    )
    current_df = pd.DataFrame(
        {"wind_speed_10m": [8.0, 9.0], "temperature_2m": [7.0, 8.0]}
    )
    current_df.attrs.update({"dataset_name": "silvaplana", "dataset_version": "train"})

    report = drift.detect_data_drift(reference_df, current_df)

    assert captured["reference_columns"] == ["wind_speed_10m", "temperature_2m"]
    assert captured["current_columns"] == ["wind_speed_10m", "temperature_2m"]
    assert captured["threshold"] == 0.25
    assert report.dataset_name == "silvaplana"
    assert report.dataset_version == "train"
    assert report.threshold == 0.25
    assert report.drifted_column_count == 1
    assert report.share_of_drifted_columns == 0.5
    assert report.dataset_drift is True
    assert report.metrics[0].column_name == "wind_speed_10m"
    assert report.metrics[0].drift_detected is True
    assert report.metrics[1].drift_detected is False


def test_detect_prediction_drift_uses_recent_window_and_prediction_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, pd.DataFrame] = {}

    def fake_run(
        reference_frame: pd.DataFrame,
        current_frame: pd.DataFrame,
        threshold: float,
    ) -> list[dict[str, object]]:
        captured["reference"] = reference_frame.copy()
        captured["current"] = current_frame.copy()
        captured["threshold"] = pd.DataFrame({"threshold": [threshold]})
        return _sample_evidently_metrics()

    monkeypatch.setattr(drift, "_run_evidently_data_drift", fake_run)
    monkeypatch.setattr(
        drift,
        "get_monitoring_config",
        lambda: {"drift_threshold": 0.2, "evaluation_window_days": 7},
    )

    predictions_log = pd.DataFrame(
        {
            "prediction_timestamp": pd.to_datetime(
                [
                    "2026-05-01T00:00:00Z",
                    "2026-05-02T00:00:00Z",
                    "2026-05-10T00:00:00Z",
                    "2026-05-11T00:00:00Z",
                ]
            ),
            "prediction": [0.1, 0.2, 0.9, 0.95],
            "spot_id": ["silvaplana", "silvaplana", "urnersee", "urnersee"],
        }
    )
    predictions_log.attrs.update(
        {"dataset_name": "online_predictions", "dataset_version": "serve_v1"}
    )

    report = drift.detect_prediction_drift(predictions_log)

    assert list(captured["reference"].columns) == ["prediction"]
    assert list(captured["current"].columns) == ["prediction"]
    assert list(captured["reference"]["prediction"]) == [0.1, 0.2]
    assert list(captured["current"]["prediction"]) == [0.9, 0.95]
    assert report.report_kind == "prediction"
    assert report.dataset_name == "online_predictions"
    assert report.dataset_version == "serve_v1"
    assert report.threshold == 0.2


def test_push_drift_metrics_sends_statsd_gauges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Isolate the persisted-report side effect so the fixture does not leak into
    # the shared airflow/reports store (where the Prometheus exporter would then
    # render it forever).
    monkeypatch.setenv("FOEHNCAST_PIPELINE_REPORT_DIR", str(tmp_path))
    sent: list[tuple[str, tuple[str, int]]] = []

    class FakeSocket:
        def __enter__(self) -> "FakeSocket":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def sendto(self, payload: bytes, address: tuple[str, int]) -> None:
            sent.append((payload.decode("utf-8"), address))

    monkeypatch.setenv("FOEHNCAST_STATSD_HOST", "127.0.0.1")
    monkeypatch.setenv("FOEHNCAST_STATSD_PORT", "8125")
    monkeypatch.setenv("FOEHNCAST_STATSD_PREFIX", "drift.metrics")
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: FakeSocket())

    report = drift.DriftReport(
        report_kind="data",
        dataset_name="forecast features",
        dataset_version="v1",
        threshold=0.15,
        reference_row_count=48,
        current_row_count=24,
        column_count=2,
        drifted_column_count=1,
        share_of_drifted_columns=0.5,
        dataset_drift=True,
        generated_at="2026-05-11T10:00:00+00:00",
        metrics=(
            drift.DriftMetric(
                column_name="wind_speed_10m",
                drift_score=0.01,
                drift_detected=True,
                threshold=0.05,
                method="ks p_value",
            ),
        ),
    )

    drift.push_drift_metrics(report)

    payloads = [payload for payload, _ in sent]
    assert all(address == ("127.0.0.1", 8125) for _, address in sent)
    assert (
        "drift_metrics.forecast_features.v1.dataset.share_of_drifted_columns:0.5|g"
        in payloads
    )
    assert "drift_metrics.forecast_features.v1.dataset.dataset_drift:1.0|g" in payloads
    assert (
        "drift_metrics.forecast_features.v1.wind_speed_10m.drift_score:0.01|g"
        in payloads
    )


def test_detect_data_drift_rejects_disjoint_columns() -> None:
    with pytest.raises(ValueError, match="share no comparable columns"):
        drift.detect_data_drift(
            pd.DataFrame({"wind_speed_10m": [1.0, 2.0]}),
            pd.DataFrame({"temperature_2m": [3.0, 4.0]}),
            threshold=0.15,
        )


def test_detect_model_feature_drift_restricts_to_configured_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        reference_frame: pd.DataFrame,
        current_frame: pd.DataFrame,
        threshold: float,
    ) -> list[dict[str, object]]:
        captured["reference_columns"] = list(reference_frame.columns)
        return _sample_evidently_metrics()

    monkeypatch.setattr(drift, "_run_evidently_data_drift", fake_run)
    monkeypatch.setattr(
        drift,
        "get_monitoring_config",
        lambda: {"drift_threshold": 0.15, "evaluation_window_days": 30},
    )

    # "cape" is configured but absent from the data; "spot_id" is present but not
    # a model feature. Only the shared model features should be compared.
    reference_df = pd.DataFrame(
        {
            "wind_speed_10m": [1.0, 2.0],
            "temperature_2m": [5.0, 6.0],
            "spot_id": ["a", "b"],
        }
    )
    current_df = pd.DataFrame(
        {
            "wind_speed_10m": [8.0, 9.0],
            "temperature_2m": [7.0, 8.0],
            "spot_id": ["a", "b"],
        }
    )

    report = drift.detect_model_feature_drift(
        reference_df,
        current_df,
        ["wind_speed_10m", "temperature_2m", "cape"],
        dataset_name="forecast features",
        dataset_version="v1",
    )

    assert report is not None
    assert captured["reference_columns"] == ["wind_speed_10m", "temperature_2m"]
    assert report.dataset_name == "forecast features"
    assert report.dataset_version == "v1"
    assert report.column_count == 2


def test_detect_model_feature_drift_backward_compatible_with_narrow_frames() -> None:
    # No configured feature is present in the frames -> nothing comparable.
    assert (
        drift.detect_model_feature_drift(
            pd.DataFrame({"legacy_only": [1.0, 2.0]}),
            pd.DataFrame({"legacy_only": [3.0, 4.0]}),
            ["wind_speed_10m", "temperature_2m"],
            dataset_name="forecast features",
            dataset_version="v1",
        )
        is None
    )
    # An empty frame is skipped rather than raising.
    assert (
        drift.detect_model_feature_drift(
            pd.DataFrame(),
            pd.DataFrame({"wind_speed_10m": [3.0, 4.0]}),
            ["wind_speed_10m"],
            dataset_name="forecast features",
            dataset_version="v1",
        )
        is None
    )


def test_detect_model_feature_drift_share_over_widened_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feature_columns = [
        "wind_speed_10m",
        "wind_speed_80m",
        "wind_gusts_10m",
        "temperature_2m",
        "relative_humidity_2m",
        "hour_of_day_sin",
        "hour_of_day_cos",
        "day_of_year_sin",
        "day_of_year_cos",
        "wind_direction_10m_sin",
        "wind_direction_10m_cos",
        "wind_steadiness",
        "gust_excess_10m",
        "shore_alignment",
    ]

    def fake_run(
        reference_frame: pd.DataFrame,
        current_frame: pd.DataFrame,
        threshold: float,
    ) -> list[dict[str, object]]:
        # One column drifts (p_value below threshold); no DriftedColumnsCount, so
        # the share is computed as drifted / widened column count.
        return [
            {
                "config": {
                    "type": "evidently:metric_v2:ValueDrift",
                    "column": column,
                    "method": "ks p_value",
                    "threshold": 0.05,
                },
                "value": 0.01 if index == 0 else 0.6,
            }
            for index, column in enumerate(feature_columns)
        ]

    monkeypatch.setattr(drift, "_run_evidently_data_drift", fake_run)
    monkeypatch.setattr(
        drift,
        "get_monitoring_config",
        lambda: {"drift_threshold": 0.15, "evaluation_window_days": 30},
    )

    values = {column: [1.0, 2.0] for column in feature_columns}
    report = drift.detect_model_feature_drift(
        pd.DataFrame(values),
        pd.DataFrame(values),
        feature_columns,
        dataset_name="forecast features",
        dataset_version="v1",
    )

    assert report is not None
    assert report.column_count == 14
    assert report.drifted_column_count == 1
    assert report.share_of_drifted_columns == pytest.approx(1 / 14, abs=1e-4)
    assert report.dataset_drift is False
