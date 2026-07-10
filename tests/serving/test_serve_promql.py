"""Unit tests for the mini PromQL engine in ``inference_pipeline.serve``."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from foehncast.inference_pipeline import serve

FAKE_METRICS = b"""# HELP metric_a counter
# TYPE metric_a gauge
metric_a{spot="x",dataset="train"} 5
metric_a{spot="y",dataset="train"} 3
metric_b{dataset="train"} 10
metric_ts 1700000000
"""


def _run(query: str) -> list[dict]:
    with patch.object(serve, "_metrics_payload", return_value=FAKE_METRICS):
        return serve._eval_instant_query(query)


def _value(result: list[dict]) -> float:
    assert len(result) == 1
    return float(result[0]["value"][1])


def test_label_selector_matches_single_sample() -> None:
    result = _run('metric_a{spot="x"}')
    assert _value(result) == 5.0
    assert result[0]["metric"]["spot"] == "x"


def test_regex_label_matcher_matches_multiple_samples() -> None:
    result = _run('metric_a{spot=~".+"}')
    assert {r["metric"]["spot"] for r in result} == {"x", "y"}


def test_max_aggregation_returns_largest_value() -> None:
    assert _value(_run("max(metric_a)")) == 5.0


def test_min_aggregation_returns_smallest_value() -> None:
    assert _value(_run("min(metric_a)")) == 3.0


def test_sum_aggregation_totals_all_samples() -> None:
    assert _value(_run("sum(metric_a)")) == 8.0


def test_sum_by_groups_samples_by_label() -> None:
    result = _run("sum by (dataset) (metric_a)")
    assert _value(result) == 8.0
    assert result[0]["metric"] == {"dataset": "train"}


def test_time_function_returns_current_timestamp() -> None:
    result = _run("time()")
    assert len(result) == 1
    assert float(result[0]["value"][1]) > 1700000000


def test_clamp_max_caps_inner_values() -> None:
    assert _value(_run("clamp_max(max(metric_a), 4)")) == 4.0


def test_scalar_minus_vector_broadcasts() -> None:
    result = _run("1 - clamp_max(max(metric_a), 1)")
    assert _value(result) == 0.0


def test_time_minus_metric_yields_age() -> None:
    result = _run("time() - metric_ts")
    assert _value(result) > 0


def test_vector_plus_vector_matches_on_non_name_labels() -> None:
    result = _run('metric_a{spot="x"} + metric_b{dataset="train"}')
    # metric_a{spot="x"} has labels {spot=x, dataset=train}; metric_b only
    # has {dataset=train}; identical on the matched key (dataset) only when
    # we drop the differing spot label, so this should produce zero rows.
    assert result == []


def test_vector_plus_vector_with_identical_labels() -> None:
    payload = b'a{dataset="train"} 5\nb{dataset="train"} 3\n'
    with patch.object(serve, "_metrics_payload", return_value=payload):
        result = serve._eval_instant_query('a{dataset="train"} + b{dataset="train"}')
    assert _value(result) == 8.0
    assert result[0]["metric"] == {"dataset": "train"}


def test_synthetic_up_metric_is_emitted() -> None:
    payload = serve._metrics_payload()
    assert b'up{job="foehncast_app"} 1' in payload


@pytest.mark.parametrize(
    "query",
    [
        "rate(metric_a[5m])",
        "histogram_quantile(0.95, metric_a)",
        "not_valid_at_all***",
    ],
)
def test_unsupported_query_returns_empty_without_raising(query: str) -> None:
    assert _run(query) == []
