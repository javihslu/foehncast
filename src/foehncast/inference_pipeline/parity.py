"""Compare two running deployments endpoint by endpoint.

Two deployments only answer the same way when they were trained on the same
data, so every comparison carries the training window the caller asserts. The
comparison itself is pure: fetching is separate from diffing, so the diff can
be exercised on fixtures without a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from foehncast.http_client import ca_bundle

DEFAULT_TOLERANCE = 1e-6
DEFAULT_TIMEOUT = 60.0
DEFAULT_LABELS = ("baseline", "candidate")

_SPOT_FIELDS = ("name", "lat", "lon", "shore_orientation_deg")
_RANK_FIELDS = (
    "quality_index",
    "drive_minutes",
    "session_hours",
    "ride_drive_ratio",
    "score",
)
# Each deployment reads its own model registry, so a version mismatch is
# reported as context rather than counted as a disagreement.
_CONTEXT_FIELDS = ("status", "model_alias", "model_version")


class HttpSession(Protocol):
    """The slice of requests.Session this module uses."""

    def get(self, url: str, **kwargs: Any) -> Any: ...

    def post(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(slots=True)
class ParityReport:
    """What two deployments agreed and disagreed on."""

    training_window: str
    labels: tuple[str, str] = DEFAULT_LABELS
    differences: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def agrees(self) -> bool:
        return not self.differences

    def as_dict(self) -> dict[str, Any]:
        return {
            "training_window": self.training_window,
            "labels": list(self.labels),
            "agrees": self.agrees,
            "differences": self.differences,
            "metrics": self.metrics,
            "context": self.context,
        }


def asserted_training_window(start: str, end: str) -> str:
    """Return the training window both deployments are asserted to share.

    ``backfill-history.py --start/--end`` is the only knob that spans both
    sides, so the window is an input this comparison states rather than one it
    controls. Comparing deployments seeded over different windows measures
    seeding, not agreement, which is why the window has no default.
    """
    first = _parse_day(start, "--start")
    last = _parse_day(end, "--end")
    if first > last:
        raise ValueError(f"training window starts after it ends: {start} > {end}")
    return f"{start}..{end}"


def _parse_day(value: str, option: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{option} must be YYYY-MM-DD, got {value!r}") from exc


def _differs(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left != right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) > tolerance
    return left != right


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _get(session: HttpSession, base_url: str, path: str, timeout: float) -> Any:
    response = session.get(_url(base_url, path), timeout=timeout, verify=ca_bundle())
    response.raise_for_status()
    return response.json()


def _post(
    session: HttpSession, base_url: str, path: str, body: dict[str, Any], timeout: float
) -> Any:
    response = session.post(
        _url(base_url, path), json=body, timeout=timeout, verify=ca_bundle()
    )
    response.raise_for_status()
    return response.json()


def fetch_spots(
    session: HttpSession, base_url: str, *, timeout: float = DEFAULT_TIMEOUT
) -> list[dict[str, Any]]:
    """Return the spots one deployment serves."""
    return _get(session, base_url, "/spots", timeout)


def fetch_payloads(
    session: HttpSession,
    base_url: str,
    spot_ids: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Call /health, /predict and /rank on one deployment for the given spots."""
    body: dict[str, Any] = {"spot_ids": list(spot_ids)}
    return {
        "health": _get(session, base_url, "/health", timeout),
        "predict": _post(session, base_url, "/predict", body, timeout),
        "rank": _post(session, base_url, "/rank", body, timeout),
    }


def compare_health(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    labels: tuple[str, str] = DEFAULT_LABELS,
) -> list[str]:
    """Compare serving status. Model version is context, not a disagreement."""
    if left.get("status") == right.get("status"):
        return []
    return [
        f"/health status: {labels[0]}={left.get('status')!r} "
        f"{labels[1]}={right.get('status')!r}"
    ]


def compare_spots(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    labels: tuple[str, str] = DEFAULT_LABELS,
) -> tuple[list[str], list[str]]:
    """Compare the spot catalogues and return the ids both deployments serve."""
    by_left = {spot["id"]: spot for spot in left}
    by_right = {spot["id"]: spot for spot in right}
    differences = [
        f"/spots {spot_id} served by {labels[0]} only"
        for spot_id in sorted(set(by_left) - set(by_right))
    ]
    differences += [
        f"/spots {spot_id} served by {labels[1]} only"
        for spot_id in sorted(set(by_right) - set(by_left))
    ]

    common = sorted(set(by_left) & set(by_right))
    for spot_id in common:
        for name in _SPOT_FIELDS:
            left_value = by_left[spot_id].get(name)
            right_value = by_right[spot_id].get(name)
            if _differs(left_value, right_value, tolerance):
                differences.append(
                    f"/spots {spot_id}.{name}: {left_value!r} vs {right_value!r}"
                )
    return differences, common


def compare_predictions(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    labels: tuple[str, str] = DEFAULT_LABELS,
) -> tuple[list[str], dict[str, Any]]:
    """Compare forecast series on the hours both deployments cover.

    The forecast horizon rolls with the clock, so hours only one side returned
    are counted and reported rather than treated as a disagreement. A spot with
    no shared hour is a disagreement: nothing was actually compared.
    """
    by_left = {item["spot_id"]: item for item in left.get("predictions", [])}
    by_right = {item["spot_id"]: item for item in right.get("predictions", [])}
    differences = [
        f"/predict {spot_id} returned by {labels[0]} only"
        for spot_id in sorted(set(by_left) - set(by_right))
    ]
    differences += [
        f"/predict {spot_id} returned by {labels[1]} only"
        for spot_id in sorted(set(by_right) - set(by_left))
    ]

    common = sorted(set(by_left) & set(by_right))
    hours_compared = 0
    max_delta = 0.0
    unmatched = {labels[0]: 0, labels[1]: 0}
    for spot_id in common:
        series_left = _series(by_left[spot_id])
        series_right = _series(by_right[spot_id])
        shared = set(series_left) & set(series_right)
        unmatched[labels[0]] += len(set(series_left) - shared)
        unmatched[labels[1]] += len(set(series_right) - shared)
        if not shared:
            differences.append(
                f"/predict {spot_id}: no forecast hour covered by both deployments"
            )
            continue

        spot_delta = max(abs(series_left[hour] - series_right[hour]) for hour in shared)
        hours_compared += len(shared)
        max_delta = max(max_delta, spot_delta)
        if spot_delta > tolerance:
            differences.append(
                f"/predict {spot_id}.quality_index differs by up to "
                f"{spot_delta:.6g} over {len(shared)} shared hours"
            )

    metrics = {
        "spots_compared": len(common),
        "hours_compared": hours_compared,
        "max_quality_index_delta": max_delta,
        "unmatched_hours": unmatched,
    }
    return differences, metrics


def _series(prediction: dict[str, Any]) -> dict[str, float]:
    return {
        hour["time"]: float(hour["quality_index"])
        for hour in prediction.get("forecast", [])
    }


def compare_rankings(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    labels: tuple[str, str] = DEFAULT_LABELS,
) -> tuple[list[str], dict[str, Any]]:
    """Compare the ranked order and each ranked spot's metrics."""
    left_spots = left.get("ranked_spots", [])
    right_spots = right.get("ranked_spots", [])
    order_left = [item["spot_id"] for item in left_spots]
    order_right = [item["spot_id"] for item in right_spots]

    differences = []
    if order_left != order_right:
        differences.append(
            f"/rank order: {labels[0]}={order_left} {labels[1]}={order_right}"
        )

    by_left = {item["spot_id"]: item for item in left_spots}
    by_right = {item["spot_id"]: item for item in right_spots}
    common = sorted(set(by_left) & set(by_right))
    max_deltas: dict[str, float] = {}
    for spot_id in common:
        for name in _RANK_FIELDS:
            left_value = by_left[spot_id].get(name)
            right_value = by_right[spot_id].get(name)
            if isinstance(left_value, (int, float)) and isinstance(
                right_value, (int, float)
            ):
                delta = abs(float(left_value) - float(right_value))
                max_deltas[name] = max(max_deltas.get(name, 0.0), delta)
            if _differs(left_value, right_value, tolerance):
                differences.append(
                    f"/rank {spot_id}.{name}: {left_value!r} vs {right_value!r}"
                )

    metrics = {"spots_ranked": len(common), "max_deltas": max_deltas}
    return differences, metrics


def run(
    session: HttpSession,
    left_url: str,
    right_url: str,
    *,
    training_window: str,
    spot_ids: list[str] | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    timeout: float = DEFAULT_TIMEOUT,
    labels: tuple[str, str] = DEFAULT_LABELS,
) -> ParityReport:
    """Compare two deployments and report every disagreement found.

    Both deployments are asked about the same spots, so the diff cannot be
    confounded by one of them serving a longer catalogue.
    """
    spots_left = fetch_spots(session, left_url, timeout=timeout)
    spots_right = fetch_spots(session, right_url, timeout=timeout)
    differences, common = compare_spots(
        spots_left, spots_right, tolerance=tolerance, labels=labels
    )

    requested = list(spot_ids) if spot_ids else common
    if not requested:
        raise ValueError("no spot is served by both deployments")

    left = fetch_payloads(session, left_url, requested, timeout=timeout)
    right = fetch_payloads(session, right_url, requested, timeout=timeout)

    differences += compare_health(left["health"], right["health"], labels=labels)
    predict_differences, predict_metrics = compare_predictions(
        left["predict"], right["predict"], tolerance=tolerance, labels=labels
    )
    rank_differences, rank_metrics = compare_rankings(
        left["rank"], right["rank"], tolerance=tolerance, labels=labels
    )
    differences += predict_differences + rank_differences

    return ParityReport(
        training_window=training_window,
        labels=labels,
        differences=differences,
        metrics={
            "spots_requested": requested,
            "predict": predict_metrics,
            "rank": rank_metrics,
        },
        context={
            labels[0]: _health_context(left["health"]),
            labels[1]: _health_context(right["health"]),
        },
    )


def _health_context(health: dict[str, Any]) -> dict[str, Any]:
    return {name: health.get(name) for name in _CONTEXT_FIELDS}


def render(report: ParityReport) -> str:
    """Render the report for a terminal."""
    left_label, right_label = report.labels
    lines = [
        f"Deployment parity: {left_label} vs {right_label}",
        f"Training window asserted by the caller: {report.training_window}",
        "Both deployments must have been seeded over this window with",
        "backfill-history.py --start/--end. An unequal window measures seeding,",
        "not agreement.",
        "",
    ]
    for label in report.labels:
        context = report.context.get(label, {})
        lines.append(
            f"{label}: status={context.get('status')} "
            f"model={context.get('model_version')} alias={context.get('model_alias')}"
        )

    predict = report.metrics.get("predict", {})
    rank = report.metrics.get("rank", {})
    lines += [
        "",
        f"spots compared: {predict.get('spots_compared', 0)}",
        f"forecast hours compared: {predict.get('hours_compared', 0)} "
        f"(unmatched {predict.get('unmatched_hours', {})})",
        f"largest quality_index gap: {predict.get('max_quality_index_delta', 0.0):.6g}",
        f"largest ranking gaps: {rank.get('max_deltas', {})}",
        "",
    ]

    if report.agrees:
        lines.append("VERDICT: deployments agree")
    else:
        lines.append(f"VERDICT: {len(report.differences)} disagreement(s)")
        lines += [f"  - {difference}" for difference in report.differences]
    return "\n".join(lines)
