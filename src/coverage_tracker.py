"""Coverage tracker for Nightshift.

Runs pytest with --cov and parses coverage output to track test coverage
percentage over time. Stores per-session snapshots in a lightweight JSON
file (docs/coverage_history.json) and renders trend data as Markdown for
embedding in reports or NIGHTSHIFT_LOG.md.

Coverage is collected via pytest-cov (already installed as a dev dependency).
The module is intentionally subprocess-based so it works with any test runner
that supports --cov, without importing pytest internals.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CoverageSnapshot:
    """Coverage measurement for a single session."""

    session: int
    timestamp: str
    total_coverage: float       # 0.0–100.0
    files: dict[str, float] = field(default_factory=dict)   # path -> coverage %
    lines_covered: int = 0
    lines_total: int = 0
    missing_lines: int = 0

    def to_dict(self) -> dict:
        """Return a dictionary representation of the coverage snapshot"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CoverageSnapshot":
        """Construct a CoverageSnapshot from a dictionary"""
        return cls(**d)

    @property
    def coverage_badge(self) -> str:
        """Return a color-coded badge string for the coverage level."""
        pct = self.total_coverage
        if pct >= 90:
            return f"🟢 {pct:.1f}%"
        elif pct >= 70:
            return f"🟡 {pct:.1f}%"
        else:
            return f"🔴 {pct:.1f}%"


@dataclass
class CoverageHistory:
    """Append-only history of coverage snapshots."""

    snapshots: list[CoverageSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the coverage history"""
        return {"snapshots": [s.to_dict() for s in self.snapshots]}

    @classmethod
    def from_dict(cls, d: dict) -> "CoverageHistory":
        """Construct a CoverageHistory from a dictionary"""
        snapshots = [CoverageSnapshot.from_dict(s) for s in d.get("snapshots", [])]
        return cls(snapshots=snapshots)

    def append(self, snapshot: CoverageSnapshot) -> None:
        """Add a new snapshot. Replaces any existing snapshot for same session."""
        self.snapshots = [s for s in self.snapshots if s.session != snapshot.session]
        self.snapshots.append(snapshot)
        self.snapshots.sort(key=lambda s: s.session)

    def latest(self) -> Optional[CoverageSnapshot]:
        """Return the most recent snapshot, or None if empty."""
        if not self.snapshots:
            return None
        return max(self.snapshots, key=lambda s: s.session)

    def trend(self) -> list[tuple[int, float]]:
        """Return (session, coverage) pairs sorted by session."""
        return [(s.session, s.total_coverage) for s in sorted(self.snapshots, key=lambda s: s.session)]

    def to_markdown(self) -> str:
        """Render coverage history as a Markdown table."""
        if not self.snapshots:
            return "*No coverage data recorded yet.*\n"

        lines = [
            "| Session | Coverage | Lines | Trend |",
            "|---------|----------|-------|-------|",
        ]

        trend_data = self.trend()
        for i, snapshot in enumerate(sorted(self.snapshots, key=lambda s: s.session)):
            # Compute trend arrow vs previous session
            if i == 0:
                trend_arrow = "—"
            else:
                prev_cov = trend_data[i - 1][1]
                diff = snapshot.total_coverage - prev_cov
                if diff > 0:
                    trend_arrow = f"↑ +{diff:.1f}%"
                elif diff < 0:
                    trend_arrow = f"↓ {diff:.1f}%"
                else:
                    trend_arrow = "→ 0%"

            lines.append(
                f"| {snapshot.session} | {snapshot.coverage_badge} | "
                f"{snapshot.lines_covered}/{snapshot.lines_total} | {trend_arrow} |"
            )

        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Coverage running and parsing
# ---------------------------------------------------------------------------

# Matches: TOTAL   1234    45    96%
TOTAL_PATTERN = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%", re.MULTILINE)
# Matches per-file lines: src/stats.py   217    5   98%
FILE_PATTERN = re.compile(r"^(src/\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%", re.MULTILINE)


def run_coverage(
    repo_path: Optional[Path] = None,
    *,
    timeout: int = 120,
) -> str:
    """Run pytest with --cov and return the coverage report as a string.

    Returns empty string if pytest or pytest-cov is not available.
    """
    root = repo_path or Path.cwd()
    try:
        result = subprocess.run(
            [
                "python", "-m", "pytest",
                "tests/",
                "--cov=src",
                "--cov-report=term-missing",
                "-q",
                "--tb=no",
            ],
            capture_output=True,
            text=True,
            cwd=root,
            timeout=timeout,
        )
        return result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def parse_coverage_output(output: str) -> dict:
    """Parse the text output of pytest-cov into structured data.

    Returns a dict with keys:
        total_coverage: float (0.0–100.0)
        lines_total: int
        lines_covered: int
        missing_lines: int
        files: dict[str, float]
    """
    result: dict = {
        "total_coverage": 0.0,
        "lines_total": 0,
        "lines_covered": 0,
        "missing_lines": 0,
        "files": {},
    }

    total_match = TOTAL_PATTERN.search(output)
    if total_match:
        lines_total = int(total_match.group(1))
        lines_missing = int(total_match.group(2))
        coverage_pct = int(total_match.group(3))
        result["lines_total"] = lines_total
        result["missing_lines"] = lines_missing
        result["lines_covered"] = lines_total - lines_missing
        result["total_coverage"] = float(coverage_pct)

    for file_match in FILE_PATTERN.finditer(output):
        filepath = file_match.group(1)
        file_cov = int(file_match.group(4))
        result["files"][filepath] = float(file_cov)

    return result


def load_coverage_history(history_path: Path) -> CoverageHistory:
    """Load coverage history from a JSON file."""
    if not history_path.exists():
        return CoverageHistory()
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
        return CoverageHistory.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return CoverageHistory()


def save_coverage_history(history: CoverageHistory, history_path: Path) -> None:
    """Save coverage history to a JSON file."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(history.to_dict(), indent=2),
        encoding="utf-8",
    )


def record_coverage(
    session: int,
    repo_path: Optional[Path] = None,
    *,
    history_path: Optional[Path] = None,
    timestamp: str = "",
) -> CoverageSnapshot:
    """Run coverage, parse results, append to history, and save.

    Args:
        session: Current session number.
        repo_path: Path to the git repository root. Defaults to CWD.
        history_path: Path to save the JSON history file.
        timestamp: Override timestamp for the snapshot.

    Returns:
        The newly created CoverageSnapshot.
    """
    root = repo_path or Path.cwd()
    hp = history_path or (root / "docs" / "coverage_history.json")
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output = run_coverage(root)
    parsed = parse_coverage_output(output)

    snapshot = CoverageSnapshot(
        session=session,
        timestamp=ts,
        total_coverage=parsed["total_coverage"],
        files=parsed["files"],
        lines_covered=parsed["lines_covered"],
        lines_total=parsed["lines_total"],
        missing_lines=parsed["missing_lines"],
    )

    history = load_coverage_history(hp)
    history.append(snapshot)
    save_coverage_history(history, hp)

    return snapshot
