"""Minimal PromQL evaluator for the FoehnCast inference API.

Supports metric{labels} selectors, the scalar literal time(),
aggregations max() / min() / avg() / sum() / sum by (labels)(),
the transformer clamp_max(expr, max), and the binary operators +
and - with scalar broadcasting.  This is *not* a full PromQL
engine — just enough to serve the queries our UI panels issue.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable


def parse_metrics_text(text: str) -> list[dict]:
    """Parse Prometheus exposition text into a list of metric samples."""
    results: list[dict] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(.+?)(\s+\d+)?$", line)
        if not m:
            continue
        name = m.group(1)
        labels_str = m.group(2) or ""
        value = m.group(3)
        labels: dict[str, str] = {"__name__": name}
        if labels_str:
            for lm in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"', labels_str):
                labels[lm.group(1)] = lm.group(2)
        results.append({"metric": labels, "value": [0, value]})
    return results


def match_metric(metric: dict, matchers: list[tuple[str, str, str]]) -> bool:
    """Check whether a metric sample matches all label matchers."""
    for label, op, val in matchers:
        actual = metric["metric"].get(label, "")
        if op == "=" and actual != val:
            return False
        if op == "!=" and actual == val:
            return False
        if op == "=~" and not re.fullmatch(val, actual):
            return False
        if op == "!~" and re.fullmatch(val, actual):
            return False
    return True


def find_top_level_binary_op(expr: str) -> int | None:
    """Find the rightmost top-level ``+`` or ``-`` operator position.

    Skips operators inside parentheses or braces.  Returns ``None`` when the
    expression has no top-level binary arithmetic.  Unary signs at the start
    of the expression (``-foo`` or ``+foo``) are ignored.
    """
    depth = 0
    last: int | None = None
    for i, ch in enumerate(expr):
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif depth == 0 and ch in "+-" and i > 0:
            prev = expr[i - 1]
            if prev in "eE" and i >= 2 and expr[i - 2].isdigit():
                continue
            if prev in "+-*/(":
                continue
            last = i
    return last


def binary_op(lhs: list[dict], rhs: list[dict], op: str, now: float) -> list[dict]:
    """Apply ``+`` or ``-`` between two evaluated samples with scalar broadcast."""
    if not lhs or not rhs:
        return []

    def is_scalar(samples: list[dict]) -> bool:
        return len(samples) == 1 and samples[0]["metric"] == {}

    def apply(a: float, b: float) -> float:
        return a + b if op == "+" else a - b

    if is_scalar(lhs) and is_scalar(rhs):
        a = float(lhs[0]["value"][1])
        b = float(rhs[0]["value"][1])
        return [{"metric": {}, "value": [now, str(apply(a, b))]}]
    if is_scalar(lhs):
        scalar = float(lhs[0]["value"][1])
        return [
            {
                "metric": s["metric"],
                "value": [now, str(apply(scalar, float(s["value"][1])))],
            }
            for s in rhs
        ]
    if is_scalar(rhs):
        scalar = float(rhs[0]["value"][1])
        return [
            {
                "metric": s["metric"],
                "value": [now, str(apply(float(s["value"][1]), scalar))],
            }
            for s in lhs
        ]

    def _match_key(metric: dict) -> tuple:
        return tuple(sorted((k, v) for k, v in metric.items() if k != "__name__"))

    by_labels = {_match_key(s["metric"]): s for s in rhs}
    out: list[dict] = []
    for s in lhs:
        key = _match_key(s["metric"])
        if key in by_labels:
            a = float(s["value"][1])
            b = float(by_labels[key]["value"][1])
            merged = {k: v for k, v in s["metric"].items() if k != "__name__"}
            out.append({"metric": merged, "value": [now, str(apply(a, b))]})
    return out


def eval_instant_query(expr: str, metrics_text_fn: Callable[[], str]) -> list[dict]:
    """Evaluate a simple PromQL instant query against the metrics payload."""
    now = time.time()
    expr = expr.strip()

    # Strip redundant outer parentheses.
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        balanced_outer = True
        for i, ch in enumerate(expr[:-1]):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                balanced_outer = False
                break
        if not balanced_outer:
            break
        expr = expr[1:-1].strip()

    # Binary ``+`` / ``-`` at the top level.
    op_pos = find_top_level_binary_op(expr)
    if op_pos is not None:
        op = expr[op_pos]
        lhs = eval_instant_query(expr[:op_pos], metrics_text_fn)
        rhs = eval_instant_query(expr[op_pos + 1 :], metrics_text_fn)
        return binary_op(lhs, rhs, op, now)

    # Scalar literal.
    scalar = re.match(r"^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$", expr)
    if scalar:
        return [{"metric": {}, "value": [now, expr]}]

    # ``time()`` returns the current Unix timestamp as a scalar.
    if expr == "time()":
        return [{"metric": {}, "value": [now, str(now)]}]

    # ``clamp_max(<expr>, <max>)``
    clamp = re.match(r"^clamp_max\((.+),\s*(\d+(?:\.\d+)?)\)$", expr)
    if clamp:
        inner = eval_instant_query(clamp.group(1), metrics_text_fn)
        cap = float(clamp.group(2))
        for s in inner:
            s["value"] = [now, str(min(float(s["value"][1]), cap))]
        return inner

    # ``max(<expr>)``, ``min(<expr>)`` and ``avg(<expr>)``: scalar reduction.
    agg = re.match(r"^(max|min|avg)\((.+)\)$", expr)
    if agg:
        inner = eval_instant_query(agg.group(2), metrics_text_fn)
        if not inner:
            return []
        if agg.group(1) == "avg":
            total = sum(float(s["value"][1]) for s in inner)
            return [{"metric": {}, "value": [now, str(total / len(inner))]}]
        chooser = max if agg.group(1) == "max" else min
        best = chooser(inner, key=lambda s: float(s["value"][1]))
        return [{"metric": {}, "value": [now, best["value"][1]]}]

    # ``sum(<expr>)`` and ``sum by (label,...) (<expr>)``.
    sum_match = re.match(
        r"^sum\s*(?:by\s*\(([^)]*)\)\s*)?\((.+)\)$", expr, flags=re.DOTALL
    )
    if sum_match:
        by_labels = [
            s.strip() for s in (sum_match.group(1) or "").split(",") if s.strip()
        ]
        inner = eval_instant_query(sum_match.group(2), metrics_text_fn)
        if not inner:
            return []
        if not by_labels:
            total = sum(float(s["value"][1]) for s in inner)
            return [{"metric": {}, "value": [now, str(total)]}]
        groups: dict[tuple, float] = {}
        for s in inner:
            key = tuple((label, s["metric"].get(label, "")) for label in by_labels)
            groups[key] = groups.get(key, 0.0) + float(s["value"][1])
        return [
            {"metric": dict(key), "value": [now, str(val)]}
            for key, val in groups.items()
        ]

    # Base case: metric_name or metric_name{...}
    text = metrics_text_fn()
    all_samples = parse_metrics_text(text)
    m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{.*\})?$", expr)
    if not m:
        return []

    name = m.group(1)
    label_sel = m.group(2) or ""

    matchers: list[tuple[str, str, str]] = [("__name__", "=", name)]
    if label_sel:
        for lm in re.finditer(
            r'([a-zA-Z_][a-zA-Z0-9_]*)\s*(=~|!~|!=|=)\s*"([^"]*)"', label_sel
        ):
            matchers.append((lm.group(1), lm.group(2), lm.group(3)))

    return [
        {"metric": s["metric"], "value": [now, s["value"][1]]}
        for s in all_samples
        if match_metric(s, matchers)
    ]
