"""Health trend visualization for Awake.

Tracks code health scores across sessions and renders sparklines,
tables, and trend summaries to the terminal.

CLI: awake health-trend [--json] [--sessions N] [--sparkline]
API: GET /api/health-trend
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_PATH = Path(".awake/health_log.json")
DEFAULT_SESSIONS = 10

# Unicode block characters for sparkline rendering
_SPARK_CHARS = " ▁▂▃▄▅▆▇█"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HealthSnapshot:
    """A single health score observation."""

    session: int
    date: str               # ISO-8601 date
    score: int              # 0–100
    grade: str              # A / B / C / D / F
    total_files: int
    total_lines: int
    long_files: int
    long_functions: int
    todo_density: float
    test_coverage_ratio: float


@dataclass
class TrendReport:
    """Multi-session health trend report."""

    snapshots: List[HealthSnapshot]
    first_score: int
    last_score: int
    min_score: int
    max_score: int
    mean_score: float
    delta: int              # last_score - first_score
    trend: str              # IMPROVING / DECLINING / STABLE
    sparkline: str
    summary: str


# ---------------------------------------------------------------------------
# Log I/O
# ---------------------------------------------------------------------------

def _load_log(path: Path = LOG_PATH) -> list[dict]:
    """Load the health log JSON array, returning [] on any error."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def append_snapshot(snapshot: HealthSnapshot, path: Path = LOG_PATH) -> None:
    """Append a health snapshot to the persistent log."""
    log = _load_log(path)
    # Avoid duplicate session entries — update if session already present
    existing = {entry.get("session"): i for i, entry in enumerate(log)}
    entry = asdict(snapshot)
    if snapshot.session in existing:
        log[existing[snapshot.session]] = entry
    else:
        log.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Sparkline renderer
# ---------------------------------------------------------------------------

def _sparkline(values: list[int]) -> str:
    """Render a list of 0-100 integers as a Unicode block sparkline."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    chars = []
    for v in values:
        idx = round((v - lo) / span * (len(_SPARK_CHARS) - 1))
        chars.append(_SPARK_CHARS[idx])
    return "".join(chars)


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

def _classify_trend(delta: int, n: int) -> str:
    """Classify overall trend based on delta and number of observations."""
    if n < 2:
        return "STABLE"
    if delta >= 3:
        return "IMPROVING"
    if delta <= -3:
        return "DECLINING"
    return "STABLE"


def generate_trend_report(
    sessions: int = DEFAULT_SESSIONS,
    log_path: Path = LOG_PATH,
) -> TrendReport:
    """Generate a health trend report from the persistent log."""
    raw = _load_log(log_path)

    # Parse and sort by session number
    snapshots: list[HealthSnapshot] = []
    for entry in raw:
        try:
            snapshots.append(HealthSnapshot(
                session=int(entry["session"]),
                date=str(entry.get("date", "")),
                score=int(entry["score"]),
                grade=str(entry.get("grade", "?")),
                total_files=int(entry.get("total_files", 0)),
                total_lines=int(entry.get("total_lines", 0)),
                long_files=int(entry.get("long_files", 0)),
                long_functions=int(entry.get("long_functions", 0)),
                todo_density=float(entry.get("todo_density", 0.0)),
                test_coverage_ratio=float(entry.get("test_coverage_ratio", 0.0)),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    snapshots.sort(key=lambda s: s.session)
    # Limit to the last N sessions
    snapshots = snapshots[-sessions:]

    if not snapshots:
        return TrendReport(
            snapshots=[],
            first_score=0,
            last_score=0,
            min_score=0,
            max_score=0,
            mean_score=0.0,
            delta=0,
            trend="STABLE",
            sparkline="",
            summary="No health data recorded yet. Run `awake health` to capture a snapshot.",
        )

    scores = [s.score for s in snapshots]
    first_score = scores[0]
    last_score = scores[-1]
    min_score = min(scores)
    max_score = max(scores)
    mean_score = sum(scores) / len(scores)
    delta = last_score - first_score
    trend = _classify_trend(delta, len(scores))
    spark = _sparkline(scores)

    trend_icon = {"IMPROVING": "↑", "DECLINING": "↓", "STABLE": "→"}.get(trend, "")
    summary = (
        f"{len(snapshots)} sessions tracked. "
        f"Current score: {last_score} (Grade {snapshots[-1].grade}). "
        f"Trend: {trend} {trend_icon} (Δ{delta:+d}). "
        f"Range: {min_score}–{max_score}. "
        f"Mean: {mean_score:.1f}."
    )

    return TrendReport(
        snapshots=snapshots,
        first_score=first_score,
        last_score=last_score,
        min_score=min_score,
        max_score=max_score,
        mean_score=round(mean_score, 2),
        delta=delta,
        trend=trend,
        sparkline=spark,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _trend_badge(trend: str) -> str:
    return {"IMPROVING": "↑ IMPROVING", "DECLINING": "↓ DECLINING", "STABLE": "→ STABLE"}.get(
        trend, trend
    )


def _grade_icon(grade: str) -> str:
    return {"A": "✅", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}.get(grade, "")


def format_trend_report(report: TrendReport, show_sparkline: bool = True) -> str:
    """Render a TrendReport as a human-readable string."""

    lines = [
        "═" * 70,
        "  AWAKE — HEALTH TREND REPORT",
        "═" * 70,
        f"  Sessions tracked : {len(report.snapshots)}",
        f"  Current score    : {report.last_score}  (was {report.first_score})",
        f"  Trend            : {_trend_badge(report.trend)}  (Δ{report.delta:+d})",
        f"  Range            : {report.min_score} – {report.max_score}  (mean {report.mean_score:.1f})",
        f"  Summary          : {report.summary}",
        "",
    ]

    if show_sparkline and report.sparkline:
        lines += [
            "─" * 70,
            "  SPARKLINE (older → newer)",
            "─" * 70,
            f"  {report.sparkline}",
            "",
        ]

    if report.snapshots:
        lines += [
            "─" * 70,
            "  SESSION HISTORY",
            "─" * 70,
            f"  {'Sess':>4}  {'Date':>10}  {'Score':>5}  {'Grade':>5}  "
            f"{'Files':>5}  {'Lines':>6}  {'TODOd':>6}  {'Cov':>5}",
            "  " + "-" * 60,
        ]
        for s in report.snapshots:
            icon = _grade_icon(s.grade)
            lines.append(
                f"  {s.session:>4}  {s.date:>10}  {s.score:>5}  "
                f"{s.grade:>4}{icon}  "
                f"{s.total_files:>5}  {s.total_lines:>6}  "
                f"{s.todo_density:>6.1f}  {s.test_coverage_ratio:>5.0%}"
            )
        lines.append("")

    lines.append("═" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(args=None) -> int:
    """CLI entry point for `awake health-trend`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="awake health-trend",
        description="Show health score trend across sessions",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--sessions", type=int, default=DEFAULT_SESSIONS,
        help=f"Number of sessions to display (default: {DEFAULT_SESSIONS})",
    )
    parser.add_argument("--sparkline", action="store_true", help="Show Unicode sparkline")

    parsed = parser.parse_args(args)

    report = generate_trend_report(sessions=parsed.sessions)

    if parsed.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_trend_report(report, show_sparkline=parsed.sparkline))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
