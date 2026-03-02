"""CI helper for enforcing Nightshift quality gates.

This module is intentionally small and dependency-free so it can run in
GitHub Actions without requiring additional installation steps.

Currently supported gates:
- Health score floor (based on src.health.generate_health_report)

Usage:
    python -m src.ci_gates health --min-score 80

Exit codes:
- 0: gate passed
- 1: gate failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.health import generate_health_report


def _cmd_health(args: argparse.Namespace) -> int:
    report = generate_health_report(Path(args.repo))
    score = report.overall_health_score

    if score < args.min_score:
        print(
            f"Health score gate failed: {score:.1f} < {args.min_score:.1f}",
            file=sys.stderr,
        )
        return 1

    print(f"Health score gate passed: {score:.1f} >= {args.min_score:.1f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nightshift-ci")
    sub = parser.add_subparsers(dest="command", required=True)

    health = sub.add_parser("health", help="Fail if overall health score < threshold")
    health.add_argument(
        "--repo",
        default=".",
        help="Path to repo root (default: .)",
    )
    health.add_argument(
        "--min-score",
        type=float,
        default=80.0,
        help="Minimum allowed health score (default: 80)",
    )
    health.set_defaults(func=_cmd_health)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
