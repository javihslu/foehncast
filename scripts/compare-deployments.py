#!/usr/bin/env python3
"""Compare two running deployments and exit non-zero when they disagree.

Calls /health, /spots, /predict and /rank on both base URLs, diffs the
payloads and the key metrics, and prints every disagreement it finds.

Agreement is only meaningful when both deployments were trained on the same
data, and ``backfill-history.py --start/--end`` is the only knob that spans
both sides. This script does not seed anything, so the window is a required
input it states in its report: pass the same ``--start``/``--end`` that
seeded both deployments. A run over unequal windows measures seeding rather
than agreement.

Usage:
    # Compare a local stack against a deployed service
    uv run python scripts/compare-deployments.py \
        http://127.0.0.1:8000 https://example-service.run.app \
        --start 2025-01-01 --end 2026-05-10

    # Restrict the comparison to a few spots and write a machine-readable report
    uv run python scripts/compare-deployments.py URL_A URL_B \
        --start 2025-01-01 --end 2026-05-10 \
        --spot-id silvaplana --spot-id urnersee --json reports/parity.json

Exit codes: 0 agreement, 1 disagreement, 2 bad arguments or an unreachable API.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

# Ensure the project root is on sys.path so foehncast imports work.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from foehncast._json import write_pretty_json  # noqa: E402
from foehncast.inference_pipeline import parity  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_EXIT_OK = 0
_EXIT_DISAGREEMENT = 1
_EXIT_ERROR = 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("baseline_url", help="Base URL of the reference deployment")
    parser.add_argument("candidate_url", help="Base URL of the deployment under test")
    parser.add_argument(
        "--start",
        required=True,
        help="First day of the training window both deployments were seeded over",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="Last day of that window (backfill-history.py --end)",
    )
    parser.add_argument(
        "--spot-id",
        action="append",
        dest="spot_ids",
        help="Compare only this spot; repeatable. Defaults to every shared spot.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=parity.DEFAULT_TOLERANCE,
        help="Largest numeric gap still counted as agreement",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=parity.DEFAULT_TIMEOUT,
        help="Per-request timeout in seconds",
    )
    parser.add_argument(
        "--json",
        type=Path,
        dest="json_path",
        help="Also write the full report as JSON to this path",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        window = parity.asserted_training_window(args.start, args.end)
    except ValueError as exc:
        logger.error("%s", exc)
        return _EXIT_ERROR

    session = requests.Session()
    try:
        report = parity.run(
            session,
            args.baseline_url,
            args.candidate_url,
            training_window=window,
            spot_ids=args.spot_ids,
            tolerance=args.tolerance,
            timeout=args.timeout,
        )
    except (requests.RequestException, ValueError) as exc:
        logger.error("comparison could not be completed: %s", exc)
        return _EXIT_ERROR

    print(parity.render(report))
    if args.json_path:
        write_pretty_json(args.json_path, report.as_dict())
        logger.info("report written to %s", args.json_path)

    return _EXIT_OK if report.agrees else _EXIT_DISAGREEMENT


if __name__ == "__main__":
    sys.exit(main())
