"""Health trend visualization for Nightshift.

Tracks code health scores across sessions and renders sparklines and
trend tables in Markdown.  Stores history in ``docs/health_history.json``
alongside the existing ``docs/coverage_history.json`` pattern.

Health trend data is collected at the end of each session by running
``generate_health_report()`` from ``src/health.py`` and appending the
per-file and aggregate scores to the history file.

Sparklines use Unicode block characters (▁▂▃▄▅▆▇█) so they render
inline in any Markdown viewer or terminal that supports UTF-8.

Session summary includes:
- Overall health score (0-100)
- Per-file scores
- Delta vs previous session
- 8-point sparkline of the last 8 sessions
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Sparkline helper
# ---------------------------------------------------------------------------

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: Optional[int] = None) -> str:
    """Render a list of floats as a Unicode sparkline string.

    Args:
        values: A list of numeric values (0–100 for health scores).
        width: Maximum number of characters. Defaults to len(values).

    Returns:
        A string like ``▂▃▅▇█▆▄▃``.
    """
    if not values:
        return ""
    vals = values[-width:] if width else values
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return _SPARK_CHARS[4] * len(vals)
    buckets = len(_SPARK_CHARS) - 1
    return "".join(
        _SPARK_CHARS[round((v - lo) / (hi - lo) * buckets)]
        for v in vals
    )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileHealthSnapshot:
    """Health score for one file at one point in time."""

    path: str
    score: float          # 0.0–100.0
    lines: int = 0
    docstring_coverage: float = 0.0
    todo_count: int = 0
    long_lines: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FileHealthSnapshot":
        """Deserialize from dictionary."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class HealthSnapshot:
    """Aggregate health measurement for one session."""

    session: int
    timestamp: str
    overall_score: float      # 0.0–100.0
    files: list[FileHealthSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "session": self.session,
            "timestamp": self.timestamp,
            "overall_score": self.overall_score,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HealthSnapshot":
        """Deserialize from dictionary."""
        files = [FileHealthSnapshot.from_dict(f) for f in d.get("files", [])]
        return cls(
            session=d["session"],
            timestamp=d["timestamp"],
            overall_score=d["overall_score"],
            files=files,
        )

    @property
    def health_badge(self) -> str:
        """Color-coded badge for the overall score."""
        s = self.overall_score
        if s >= 90:
            return f"🟢 {s:.1f}"
        elif s >= 70:
            return f"🟡 {s:.1f}"
        else:
            return f"🔴 {s:.1f}"


@dataclass
class HealthTrendHistory:
    """Append-only history of health snapshots."""

    snapshots: list[HealthSnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {"snapshots": [s.to_dict() for s in self.snapshots]}

    @classmethod
    def from_dict(cls, d: dict) -> "HealthTrendHistory":
        """Deserialize from dictionary."""
        snaps = [HealthSnapshot.from_dict(s) for s in d.get("snapshots", [])]
        return cls(snapshots=snaps)

    def append(self, snapshot: HealthSnapshot) -> None:
        """Add a snapshot, replacing any existing entry for the same session."""
        self.snapshots = [s for s in self.snapshots if s.session != snapshot.session]
        self.snapshots.append(snapshot)
        self.snapshots.sort(key=lambda s: s.session)

    def latest(self) -> Optional[HealthSnapshot]:
        """Return the most recent snapshot."""
        return max(self.snapshots, key=lambda s: s.session) if self.snapshots else None

    def scores(self) -> list[tuple[int, float]]:
        """Return (session, overall_score) pairs sorted by session."""
        return [(s.session, s.overall_score) for s in sorted(self.snapshots, key=lambda s: s.session)]

    def to_markdown(self) -> str:
        """Render the health trend as a Markdown table with sparkline."""
        if not self.snapshots:
            return "*No health trend data recorded yet.*\n"

        sorted_snaps = sorted(self.snapshots, key=lambda s: s.session)
        score_values = [s.overall_score for s in sorted_snaps]
        spark = sparkline(score_values)

        lines = [
            f"**Health Trend:** `{spark}`",
            "",
            "| Session | Score | Delta | Files | Spark |",
            "|---------|-------|-------|-------|-------|",
        ]

        for i, snap in enumerate(sorted_snaps):
            delta_str = "—"
            if i > 0:
                delta = snap.overall_score - sorted_snaps[i - 1].overall_score
                delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
            file_count = len(snap.files)
            spark_char = spark[i] if i < len(spark) else "·"
            lines.append(
                f"| {snap.session} | {snap.health_badge} | {delta_str} | {file_count} | {spark_char} |"
            )

        lines.append("")
        return "\n".join(lines)

    def file_trends(self) -> dict[str, list[tuple[int, float]]]:
        """Return per-file trend data: {path: [(session, score), ...]}."""
        trends: dict[str, list[tuple[int, float]]] = {}
        for snap in sorted(self.snapshots, key=lambda s: s.session):
            for fh in snap.files:
                trends.setdefault(fh.path, []).append((snap.session, fh.score))
        return trends

    def to_per_file_markdown(self) -> str:
        """Render per-file trends as a Markdown table."""
        trends = self.file_trends()
        if not trends:
            return "*No per-file data available.*\n"

        sessions = sorted({s.session for s in self.snapshots})
        header = "| File | " + " | ".join(str(s) for s in sessions) + " | Trend |"
        sep = "|------|" + "-------|" * len(sessions) + "-------|"
        lines = [header, sep]

        for file_path in sorted(trends.keys()):
            file_scores = dict(trends[file_path])
            cells = []
            for sess in sessions:
                score = file_scores.get(sess)
                cells.append(f"{score:.0f}" if score is not None else "—")
            score_vals = [file_scores[s] for s in sessions if s in file_scores]
            spark = sparkline(score_vals) if len(score_vals) > 1 else "·"
            short_name = Path(file_path).name
            lines.append(f"| `{short_name}` | " + " | ".join(cells) + f" | `{spark}` |")

        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


def snapshot_from_health_report(session: int, report: object) -> HealthSnapshot:
    """Create a HealthSnapshot from a HealthReport (src/health.py).

    Args:
        session: The current session number.
        report: A ``HealthReport`` instance from ``src/health.py``.

    Returns:
        A HealthSnapshot ready to append to HealthTrendHistory.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    file_snaps = []
    for fh in getattr(report, "files", []):
        file_snaps.append(FileHealthSnapshot(
            path=fh.path,
            score=fh.health_score,
            lines=fh.total_lines,
            docstring_coverage=fh.docstring_coverage,
            todo_count=fh.todo_count,
            long_lines=fh.long_lines,
        ))
    return HealthSnapshot(
        session=session,
        timestamp=ts,
        overall_score=getattr(report, "overall_health_score", 0.0),
        files=file_snaps,
    )


def load_health_history(history_path: Path) -> HealthTrendHistory:
    """Load HealthTrendHistory from JSON file, creating empty if missing."""
    if not history_path.exists():
        return HealthTrendHistory()
    with history_path.open(encoding="utf-8") as f:
        return HealthTrendHistory.from_dict(json.load(f))


def save_health_history(history: HealthTrendHistory, history_path: Path) -> None:
    """Persist HealthTrendHistory to JSON.

    Args:
        history: The history object to save.
        history_path: Destination path (usually docs/health_history.json).
    """
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(history.to_dict(), f, indent=2)


def record_session_health(
    repo_path: Path,
    session: int,
    *,
    history_path: Optional[Path] = None,
) -> HealthTrendHistory:
    """Run health analysis and append snapshot to history.

    Args:
        repo_path: Repository root.
        session: Current session number.
        history_path: Override for docs/health_history.json.

    Returns:
        Updated HealthTrendHistory.
    """
    from src.health import generate_health_report

    hp = history_path or (repo_path / "docs" / "health_history.json")
    history = load_health_history(hp)
    report = generate_health_report(repo_path=repo_path)
    snap = snapshot_from_health_report(session, report)
    history.append(snap)
    save_health_history(history, hp)
    return history
