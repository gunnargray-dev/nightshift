"""Trend data tracker for Awake.

Persists per-session metrics to a local JSON store (trend_data.json) and
provides analysis utilities:
- Append a new data point after each session
- Compute rolling averages and deltas
- Detect regressions (metric drops below threshold)
- Export trend tables for the README / reports
- Plot ASCII sparklines for terminal display

The JSON store schema:
  {"sessions": [{"session": N, "date": ..., "metrics": {...}}, ...]}
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass
class MetricPoint:
    """One session's worth of key metrics."""

    session: int
    date: str
    health_score: float
    test_count: int
    tests_passing: bool
    smell_count: int
    quality_score: float
    open_prs: int
    total_lines: int
    roadmap_percent: float


# ---------------------------------------------------------------------------
# Store I/O
# ---------------------------------------------------------------------------


DEFAULT_STORE = Path("trend_data.json")


def load_store(path: Path = DEFAULT_STORE) -> list[MetricPoint]:
    """Load all data points from the JSON store."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    points = []
    for entry in raw.get("sessions", []):
        m = entry.get("metrics", {})
        points.append(MetricPoint(
            session=entry["session"],
            date=entry.get("date", ""),
            health_score=m.get("health_score", 0.0),
            test_count=m.get("test_count", 0),
            tests_passing=m.get("tests_passing", False),
            smell_count=m.get("smell_count", 0),
            quality_score=m.get("quality_score", 0.0),
            open_prs=m.get("open_prs", 0),
            total_lines=m.get("total_lines", 0),
            roadmap_percent=m.get("roadmap_percent", 0.0),
        ))
    return points


def save_store(points: list[MetricPoint], path: Path = DEFAULT_STORE) -> None:
    """Persist all data points to the JSON store."""
    payload = {
        "sessions": [
            {
                "session": p.session,
                "date": p.date,
                "metrics": {
                    "health_score": p.health_score,
                    "test_count": p.test_count,
                    "tests_passing": p.tests_passing,
                    "smell_count": p.smell_count,
                    "quality_score": p.quality_score,
                    "open_prs": p.open_prs,
                    "total_lines": p.total_lines,
                    "roadmap_percent": p.roadmap_percent,
                },
            }
            for p in points
        ]
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_point(point: MetricPoint, path: Path = DEFAULT_STORE) -> None:
    """Add or overwrite the data point for point.session."""
    points = load_store(path)
    # Replace if session already exists
    points = [p for p in points if p.session != point.session]
    points.append(point)
    points.sort(key=lambda p: p.session)
    save_store(points, path)


# ---------------------------------------------------------------------------
# Analysis utilities
# ---------------------------------------------------------------------------


def rolling_average(points: list[MetricPoint], field: str, window: int = 3) -> list[float]:
    """Return a rolling average of *field* over *window* sessions."""
    values = [getattr(p, field) for p in points]
    avgs = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        avgs.append(round(sum(chunk) / len(chunk), 2))
    return avgs


def compute_deltas(points: list[MetricPoint], field: str) -> list[float]:
    """Return session-over-session deltas for *field*."""
    values = [getattr(p, field) for p in points]
    deltas = [0.0]
    for i in range(1, len(values)):
        deltas.append(round(values[i] - values[i - 1], 2))
    return deltas


def detect_regressions(
    points: list[MetricPoint],
    thresholds: dict[str, float] | None = None,
) -> list[tuple[int, str, float, float]]:
    """
    Return (session, field, value, threshold) for each metric that falls
    below its threshold in the most recent session.
    """
    if not points:
        return []
    defaults: dict[str, float] = {
        "health_score": 60.0,
        "quality_score": 60.0,
        "roadmap_percent": 0.0,
    }
    thresholds = {**defaults, **(thresholds or {})}
    latest = points[-1]
    regressions = []
    for field, threshold in thresholds.items():
        value = getattr(latest, field, None)
        if value is not None and value < threshold:
            regressions.append((latest.session, field, value, threshold))
    return regressions


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------


_SPARKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """Render a Unicode sparkline for a list of numeric values."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    rng = hi - lo or 1
    chars = []
    for v in values:
        idx = int((v - lo) / rng * (len(_SPARKS) - 1))
        chars.append(_SPARKS[idx])
    return "".join(chars)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def trend_table(points: list[MetricPoint]) -> str:
    """Render a Markdown table of all sessions and key metrics."""
    header = (
        "| Session | Date | Health | Tests | Smells | Quality | Roadmap % |\n"
        "|---------|------|--------|-------|--------|---------|-----------|\n"
    )
    rows = []
    for p in points:
        rows.append(
            f"| {p.session} | {p.date} | {p.health_score} | "
            f"{p.test_count} | {p.smell_count} | {p.quality_score} | {p.roadmap_percent}% |"
        )
    return header + "\n".join(rows)


def export_csv(points: list[MetricPoint]) -> str:
    """Export all data points as CSV."""
    fields = [
        "session", "date", "health_score", "test_count",
        "tests_passing", "smell_count", "quality_score",
        "open_prs", "total_lines", "roadmap_percent",
    ]
    lines = [",".join(fields)]
    for p in points:
        lines.append(",".join(str(getattr(p, f)) for f in fields))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: python -m src.trend_data [--table] [--csv] [--sparkline FIELD]"""
    import sys
    args = sys.argv[1:]
    store_path = Path("trend_data.json")
    points = load_store(store_path)
    if not points:
        print("No trend data found. Run a session first.")
        return
    if "--table" in args:
        print(trend_table(points))
    elif "--csv" in args:
        print(export_csv(points))
    elif "--sparkline" in args:
        idx = args.index("--sparkline")
        field = args[idx + 1] if idx + 1 < len(args) else "health_score"
        values = [getattr(p, field, 0.0) for p in points]
        print(f"{field}: {sparkline(values)}")
    else:
        regressions = detect_regressions(points)
        if regressions:
            print("Regressions detected:")
            for session, field, val, threshold in regressions:
                print(f"  session {session}: {field} = {val} (threshold {threshold})")
        else:
            print("No regressions. Latest session metrics:")
            p = points[-1]
            print(f"  Health: {p.health_score}  Tests: {p.test_count}  Smells: {p.smell_count}")


if __name__ == "__main__":
    main()
