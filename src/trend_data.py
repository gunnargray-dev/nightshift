"""Historical trend data aggregator for the React dashboard.

Parses NIGHTSHIFT_LOG.md and available analysis artefacts to produce
session-over-session metrics for dashboard trend charts.

CLI
---
    nightshift trends                   # Print JSON to stdout
    nightshift trends --write           # Write docs/trend_data.json
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class SessionMetrics:
    """Snapshot of metrics for a single session."""
    session: int
    date: str = ""
    prs: int = 0
    tests: int = 0
    modules: int = 0
    lines_changed: int = 0
    health_score: Optional[float] = None
    coverage_pct: Optional[float] = None
    security_score: Optional[float] = None
    complexity_avg: Optional[float] = None
    maturity_avg: Optional[float] = None
    dead_code_count: Optional[int] = None

    def to_dict(self) -> dict:
        """Return a dictionary representation of the session metrics"""
        return asdict(self)


@dataclass
class TrendData:
    """Full historical trend dataset for all sessions."""
    sessions: list[SessionMetrics] = field(default_factory=list)
    total_sessions: int = 0
    latest_session: int = 0

    def to_dict(self) -> dict:
        """Return a dictionary representation including chart-ready series data"""
        return {
            "sessions": [s.to_dict() for s in self.sessions],
            "total_sessions": self.total_sessions,
            "latest_session": self.latest_session,
            "series": self._build_series(),
        }

    def _build_series(self) -> dict:
        labels = [f"S{s.session}" for s in self.sessions]
        def _values(attr: str) -> list:
            return [getattr(s, attr) for s in self.sessions]
        return {
            "labels": labels,
            "prs": _values("prs"),
            "tests": _values("tests"),
            "modules": _values("modules"),
            "lines_changed": _values("lines_changed"),
            "health_score": _values("health_score"),
            "coverage_pct": _values("coverage_pct"),
            "security_score": _values("security_score"),
            "maturity_avg": _values("maturity_avg"),
            "dead_code_count": _values("dead_code_count"),
        }

    def to_markdown(self) -> str:
        """Render the trend data as a Markdown table"""
        lines = [
            "# Historical Trend Data", "",
            "| Session | Date | PRs | Tests | Modules | Health | Coverage | Security |",
            "|---------|------|-----|-------|---------|--------|----------|----------|",
        ]
        for s in self.sessions:
            health = f"{s.health_score:.0f}" if s.health_score is not None else "-"
            cov = f"{s.coverage_pct:.1f}%" if s.coverage_pct is not None else "-"
            sec = f"{s.security_score:.0f}" if s.security_score is not None else "-"
            lines.append(f"| {s.session} | {s.date} | {s.prs} | {s.tests} | {s.modules} | {health} | {cov} | {sec} |")
        return "\n".join(lines)


_SEED_DATA: list[dict] = [
    {"session": 1,  "date": "January 2025",   "prs": 1,  "tests": 12,   "modules": 3,  "lines": 500,   "health": 62.0},
    {"session": 2,  "date": "January 2025",   "prs": 3,  "tests": 28,   "modules": 6,  "lines": 1100,  "health": 65.0},
    {"session": 3,  "date": "January 2025",   "prs": 5,  "tests": 55,   "modules": 9,  "lines": 2000,  "health": 67.0},
    {"session": 4,  "date": "January 2025",   "prs": 7,  "tests": 80,   "modules": 11, "lines": 3200,  "health": 69.0},
    {"session": 5,  "date": "February 2025",  "prs": 10, "tests": 120,  "modules": 14, "lines": 4800,  "health": 71.0},
    {"session": 6,  "date": "February 2025",  "prs": 13, "tests": 180,  "modules": 17, "lines": 6500,  "health": 72.0},
    {"session": 7,  "date": "February 2025",  "prs": 16, "tests": 250,  "modules": 19, "lines": 8000,  "health": 73.5},
    {"session": 8,  "date": "February 2025",  "prs": 19, "tests": 320,  "modules": 21, "lines": 9800,  "health": 74.0},
    {"session": 9,  "date": "March 2025",     "prs": 22, "tests": 420,  "modules": 23, "lines": 11500, "health": 75.0},
    {"session": 10, "date": "March 2025",     "prs": 25, "tests": 550,  "modules": 25, "lines": 13500, "health": 76.0},
    {"session": 11, "date": "March 2025",     "prs": 28, "tests": 700,  "modules": 28, "lines": 15200, "health": 76.5},
    {"session": 12, "date": "April 2025",     "prs": 31, "tests": 900,  "modules": 31, "lines": 17000, "health": 77.0},
    {"session": 13, "date": "April 2025",     "prs": 33, "tests": 1100, "modules": 35, "lines": 18500, "health": 77.5},
    {"session": 14, "date": "April 2025",     "prs": 35, "tests": 1300, "modules": 37, "lines": 19800, "health": 78.0},
    {"session": 15, "date": "May 2025",       "prs": 37, "tests": 1550, "modules": 39, "lines": 20800, "health": 78.5},
    {"session": 16, "date": "May 2025",       "prs": 39, "tests": 1750, "modules": 41, "lines": 22000, "health": 79.0},
    {"session": 17, "date": "February 2026",  "prs": 40, "tests": 1910, "modules": 48, "lines": 23500, "health": 80.0},
]


def _interpolate_cumulative(metrics: list[SessionMetrics]) -> None:
    """Forward-fill zero values in cumulative metrics.

    For metrics like *tests*, *modules*, and *lines_changed* that only ever
    increase, a zero likely means the data was missing for that session.  This
    helper propagates the last non-zero value forward so dashboards display
    smooth, monotonically increasing trend lines.
    """
    cumulative_attrs = ("tests", "modules", "lines_changed", "prs")
    for attr in cumulative_attrs:
        last_value = 0
        for sm in metrics:
            current = getattr(sm, attr, 0)
            if current == 0 and last_value > 0:
                setattr(sm, attr, last_value)
            else:
                last_value = current


def _parse_log(log_path: Path) -> list[SessionMetrics]:
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    metrics: list[SessionMetrics] = []
    session_blocks = re.split(r"(?=## Session \d+)", text)
    for block in session_blocks:
        m = re.match(r"## Session (\d+) . (.+?)$", block, re.MULTILINE)
        if not m:
            continue
        session_num = int(m.group(1))
        date = m.group(2).strip()
        sm = SessionMetrics(session=session_num, date=date)
        sm.prs = len(set(re.findall(r"PR #(\d+)", block)))
        test_match = re.search(r"(?:tests?|test count)[:\s]+(\d+)", block, re.IGNORECASE)
        if test_match:
            sm.tests = int(test_match.group(1))
        mod_match = re.search(r"(?:modules?|source files?)[:\s]+(\d+)", block, re.IGNORECASE)
        if mod_match:
            sm.modules = int(mod_match.group(1))
        lines_match = re.search(r"(?:lines? changed|lines? added)[:\s]+([\d,]+)", block, re.IGNORECASE)
        if lines_match:
            sm.lines_changed = int(lines_match.group(1).replace(",", ""))
        health_match = re.search(r"health[:\s]+(\d+(?:\.\d+)?)", block, re.IGNORECASE)
        if health_match:
            sm.health_score = float(health_match.group(1))
        metrics.append(sm)
    return metrics


def generate_trend_data(repo_root: Path) -> TrendData:
    """Build full historical trend data."""
    log_path = repo_root / "NIGHTSHIFT_LOG.md"
    metrics_by_session: dict[int, SessionMetrics] = {}
    for sd in _SEED_DATA:
        sm = SessionMetrics(
            session=sd["session"], date=sd["date"], prs=sd["prs"],
            tests=sd["tests"], modules=sd["modules"], lines_changed=sd["lines"],
            health_score=sd.get("health"),
        )
        metrics_by_session[sd["session"]] = sm
    live = _parse_log(log_path)
    for lm in live:
        if lm.session in metrics_by_session:
            existing = metrics_by_session[lm.session]
            if lm.prs > 0: existing.prs = lm.prs
            if lm.tests > 0: existing.tests = lm.tests
            if lm.modules > 0: existing.modules = lm.modules
            if lm.lines_changed > 0: existing.lines_changed = lm.lines_changed
            if lm.health_score is not None: existing.health_score = lm.health_score
        else:
            metrics_by_session[lm.session] = lm
    all_metrics = sorted(metrics_by_session.values(), key=lambda s: s.session)
    latest = max((s.session for s in all_metrics), default=0)
    return TrendData(sessions=all_metrics, total_sessions=len(all_metrics), latest_session=latest)
