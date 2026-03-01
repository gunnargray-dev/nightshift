"""Utilities for enforcing coverage thresholds in CI.

This module keeps coverage enforcement logic out of the GitHub Actions YAML
so it can be tested and reused.

The preferred integration is via pytest-cov's JSON report:
    pytest --cov=src --cov-report=json

Then run:
    python -m src.coverage_gate --min 80

Exit codes:
- 0: pass
- 1: fail
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read_total_coverage_percent(coverage_json_path: Path) -> float:
    """Return total coverage percentage from a pytest-cov JSON report."""
    data = json.loads(coverage_json_path.read_text(encoding="utf-8"))

    # pytest-cov JSON schema: https://pytest-cov.readthedocs.io/
    total = data.get("totals", {})
    pct = total.get("percent_covered")
    if pct is None:
        raise ValueError("coverage JSON missing totals.percent_covered")

    return float(pct)


def enforce_coverage_gate(
    *,
    min_percent: float,
    coverage_json_path: Path = Path("coverage.json"),
) -> int:
    """Return process exit code for the coverage gate."""
    pct = read_total_coverage_percent(coverage_json_path)

    if pct < min_percent:
        print(
            f"Coverage gate failed: {pct:.1f}% < {min_percent:.1f}%",
            file=sys.stderr,
        )
        return 1

    print(f"Coverage gate passed: {pct:.1f}% >= {min_percent:.1f}%")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nightshift-coverage-gate")
    parser.add_argument(
        "--min",
        dest="min_percent",
        type=float,
        default=80.0,
        help="Minimum allowed total coverage percent (default: 80)",
    )
    parser.add_argument(
        "--json",
        dest="coverage_json_path",
        default="coverage.json",
        help="Path to pytest-cov JSON report (default: coverage.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    return enforce_coverage_gate(
        min_percent=args.min_percent,
        coverage_json_path=Path(args.coverage_json_path),
    )


if __name__ == "__main__":
    raise SystemExit(main())
