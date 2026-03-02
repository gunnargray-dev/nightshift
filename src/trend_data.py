"""Historical trend data aggregator for the React dashboard.

Samples repository health metrics at the current point-in-time and
appends them to a local JSON store (``docs/trend_data.json``).  The React
frontend reads this file to render sparklines and trend charts.

Schema of ``trend_data.json``
-----------------------------
.. code-block:: json

    {
      "samples": [
        {
          "timestamp": "2025-01-15T10:00:00+00:00",
          "health_score": 82.4,
          "docstring_coverage": 0.71,
          "refactor_issues": 14,
          "test_quality": 78.0,
          "open_todos": 5
        }
      ]
    }

Public API
----------
- ``TrendSample``        -- a single metric snapshot
- ``TrendStore``         -- the full time-series store
- ``collect_sample(repo_path)``  -> ``TrendSample``
- ``load_store(store_path)``     -> ``TrendStore``
- ``append_sample(store, sample)``
- ``save_store(store, store_path)``

CLI
---
    awake trend [--collect] [--output PATH]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TrendSample:
    """A point-in-time snapshot of key repository metrics."""

    timestamp: str
    health_score: float = 0.0
    docstring_coverage: float = 0.0
    refactor_issues: int = 0
    test_quality: float = 0.0
    open_todos: int = 0


@dataclass
class TrendStore:
    """The full collection of trend samples persisted to disk."""

    samples: list[TrendSample] = field(default_factory=list)

    def latest(self) -> TrendSample | None:
        """Return the most recent sample, or *None* if the store is empty."""
        if not self.samples:
            return None
        return max(self.samples, key=lambda s: s.timestamp)


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


def _collect_health(root: Path) -> float:
    """Return the overall health score or 0.0 on failure."""
    try:
        from health import scan_repo  # type: ignore[import]

        return scan_repo(root).overall_score
    except Exception:  # noqa: BLE001
        return 0.0


def _collect_docstring_coverage(root: Path) -> float:
    """Return the docstring coverage ratio [0, 1] or 0.0 on failure."""
    try:
        from docstring_gen import scan_missing_docstrings  # type: ignore[import]

        return scan_missing_docstrings(root).coverage
    except Exception:  # noqa: BLE001
        return 0.0


def _collect_refactor_issues(root: Path) -> int:
    """Return the total number of refactor issues or 0 on failure."""
    try:
        from refactor import scan_repo  # type: ignore[import]

        return sum(len(r.issues) for r in scan_repo(root))
    except Exception:  # noqa: BLE001
        return 0


def _collect_test_quality(root: Path) -> float:
    """Return the overall test quality score or 0.0 on failure."""
    try:
        from test_quality import analyze_test_quality  # type: ignore[import]

        return analyze_test_quality(root).overall_score
    except Exception:  # noqa: BLE001
        return 0.0


def _collect_open_todos(root: Path) -> int:
    """Count TODO/FIXME comments across all Python files."""
    import re

    count = 0
    pattern = re.compile(r"#.*\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
    for py_file in root.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
            count += len(pattern.findall(text))
        except OSError:
            pass
    return count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_sample(repo_path: str | Path) -> TrendSample:
    """Collect a metric snapshot for *repo_path* and return a :class:`TrendSample`.

    Parameters
    ----------
    repo_path:
        Root directory of the repository.

    Returns
    -------
    TrendSample
        A snapshot of current repository metrics.
    """
    root = Path(repo_path)
    return TrendSample(
        timestamp=datetime.now(timezone.utc).isoformat(),
        health_score=_collect_health(root),
        docstring_coverage=_collect_docstring_coverage(root),
        refactor_issues=_collect_refactor_issues(root),
        test_quality=_collect_test_quality(root),
        open_todos=_collect_open_todos(root),
    )


def load_store(store_path: str | Path) -> TrendStore:
    """Load a :class:`TrendStore` from *store_path*, or return an empty store.

    Parameters
    ----------
    store_path:
        Path to the JSON store file.

    Returns
    -------
    TrendStore
        The loaded store, or an empty one if the file does not exist.
    """
    path = Path(store_path)
    if not path.exists():
        return TrendStore()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = [
            TrendSample(
                timestamp=s["timestamp"],
                health_score=s.get("health_score", 0.0),
                docstring_coverage=s.get("docstring_coverage", 0.0),
                refactor_issues=s.get("refactor_issues", 0),
                test_quality=s.get("test_quality", 0.0),
                open_todos=s.get("open_todos", 0),
            )
            for s in data.get("samples", [])
        ]
        return TrendStore(samples=samples)
    except (json.JSONDecodeError, KeyError):
        return TrendStore()


def append_sample(store: TrendStore, sample: TrendSample) -> None:
    """Append *sample* to *store* in timestamp order.

    Parameters
    ----------
    store:
        The trend store to update.
    sample:
        The sample to append.
    """
    store.samples.append(sample)
    store.samples.sort(key=lambda s: s.timestamp)


def save_store(store: TrendStore, store_path: str | Path) -> None:
    """Serialise *store* to JSON at *store_path*.

    Parameters
    ----------
    store:
        The trend store to save.
    store_path:
        Destination file path.
    """
    data = {
        "samples": [
            {
                "timestamp": s.timestamp,
                "health_score": s.health_score,
                "docstring_coverage": s.docstring_coverage,
                "refactor_issues": s.refactor_issues,
                "test_quality": s.test_quality,
                "open_todos": s.open_todos,
            }
            for s in store.samples
        ]
    }
    Path(store_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the trend data aggregator.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake trend",
        description="Collect and store repository metric trends.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--collect", action="store_true", help="Collect and store a new sample")
    parser.add_argument(
        "--output",
        "-o",
        default="docs/trend_data.json",
        help="Path to the trend data JSON store (default: docs/trend_data.json)",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    store = load_store(args.output)

    if args.collect:
        sample = collect_sample(root)
        append_sample(store, sample)
        save_store(store, args.output)
        print(f"Sample collected and stored in {args.output}")
        print(f"  health_score:        {sample.health_score:.1f}")
        print(f"  docstring_coverage:  {sample.docstring_coverage:.2%}")
        print(f"  refactor_issues:     {sample.refactor_issues}")
        print(f"  test_quality:        {sample.test_quality:.1f}")
        print(f"  open_todos:          {sample.open_todos}")
    else:
        latest = store.latest()
        if latest:
            print(f"Latest sample: {latest.timestamp}")
            print(f"  health_score:        {latest.health_score:.1f}")
            print(f"  docstring_coverage:  {latest.docstring_coverage:.2%}")
            print(f"  refactor_issues:     {latest.refactor_issues}")
            print(f"  test_quality:        {latest.test_quality:.1f}")
            print(f"  open_todos:          {latest.open_todos}")
        else:
            print("No trend data collected yet. Run with --collect to start.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
