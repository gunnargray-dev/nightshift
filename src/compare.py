"""Session comparison module for Nightshift.

Compares two Nightshift sessions side-by-side and produces a structured diff
showing what changed between them: tasks added/removed, PR counts, duration,
and any numeric metric deltas rendered with ▲ / ▼ / = symbols.

CLI usage
---------
    nightshift compare 3 5

This module is named ``compare.py`` so that the CLI can import it as
``from src.compare import compare_sessions``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionSnapshot:
    """A condensed snapshot of a single session extracted from the log."""

    session_number: int
    date: str = ""
    task_count: int = 0
    pr_count: int = 0
    tasks: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeltaMetric:
    """A single metric with its value in both sessions and the delta."""

    name: str
    value_a: int | float
    value_b: int | float

    @property
    def delta(self) -> int | float:
        return self.value_b - self.value_a

    @property
    def symbol(self) -> str:
        """Return ▲, ▼, or = based on the delta direction."""
        if self.delta > 0:
            return "▲"
        if self.delta < 0:
            return "▼"
        return "="

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "delta": self.delta,
            "symbol": self.symbol,
        }


@dataclass
class SessionComparison:
    """Full comparison result between two sessions."""

    session_a: SessionSnapshot
    session_b: SessionSnapshot
    metrics: list[DeltaMetric] = field(default_factory=list)
    tasks_added: list[str] = field(default_factory=list)
    tasks_removed: list[str] = field(default_factory=list)
    tasks_common: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_a": self.session_a.to_dict(),
            "session_b": self.session_b.to_dict(),
            "metrics": [m.to_dict() for m in self.metrics],
            "tasks_added": self.tasks_added,
            "tasks_removed": self.tasks_removed,
            "tasks_common": self.tasks_common,
        }

    def to_markdown(self) -> str:
        """Render a side-by-side Markdown comparison table."""
        a = self.session_a
        b = self.session_b

        lines = [
            f"# Session Comparison: Session {a.session_number} vs Session {b.session_number}",
            "",
            "## Overview",
            "",
            f"| Metric | Session {a.session_number} ({a.date}) | Session {b.session_number} ({b.date}) | Delta |",
            f"|--------|─{'\u2500' * 29}|─{'\u2500' * 29}|-------|",
        ]

        for m in self.metrics:
            delta_str = f"{m.symbol} {abs(m.delta)}" if m.delta != 0 else m.symbol
            lines.append(
                f"| {m.name} | {m.value_a} | {m.value_b} | {delta_str} |"
            )

        # Tasks
        if self.tasks_added or self.tasks_removed or self.tasks_common:
            lines += ["", "## Tasks", ""]

        if self.tasks_added:
            lines += [f"### ▲ New in Session {b.session_number}", ""]
            for t in self.tasks_added:
                lines.append(f"- {t}")
            lines.append("")

        if self.tasks_removed:
            lines += [f"### ▼ Only in Session {a.session_number}", ""]
            for t in self.tasks_removed:
                lines.append(f"- {t}")
            lines.append("")

        if self.tasks_common:
            lines += ["### = Present in both", ""]
            for t in self.tasks_common:
                lines.append(f"- {t}")
            lines.append("")

        # Decisions
        if b.decisions:
            lines += [f"## Decisions in Session {b.session_number}", ""]
            for d in b.decisions:
                lines.append(f"- {d}")
            lines.append("")

        lines += ["---", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _extract_session(log_content: str, session_number: int) -> Optional[SessionSnapshot]:
    """Extract a SessionSnapshot for the given session number from log content."""
    # Split into session blocks
    blocks = re.split(r"(?=^## Session \d+)", log_content, flags=re.MULTILINE)
    for block in blocks:
        header = re.match(r"## Session (\d+)\s*[—-]\s*(.+?)$", block, flags=re.MULTILINE)
        if not header:
            continue
        if int(header.group(1)) != session_number:
            continue

        date = header.group(2).strip()
        snap = SessionSnapshot(session_number=session_number, date=date)

        # Extract task names from bold items in "Tasks completed" section
        tasks_section = re.search(
            r"\*\*Tasks completed:\*\*\s*(.*?)(?=\n\*\*|\Z)", block, flags=re.DOTALL
        )
        if tasks_section:
            task_names = re.findall(r"\*\*([^*]+)\*\*", tasks_section.group(1))
            snap.tasks = [t.strip() for t in task_names if t.strip()]
            snap.task_count = len(snap.tasks)

        # Count PRs — match both "PR #N" style and "[#N](url)" link style
        pr_matches = re.findall(r"(?:PR\s+#|\[#)(\d+)", block)
        snap.pr_count = len(set(pr_matches))

        # Extract decisions
        decisions_section = re.search(
            r"\*\*Decisions.*?:\*\*\s*(.*?)(?=\n\*\*|\Z)", block, flags=re.DOTALL
        )
        if decisions_section:
            lines = decisions_section.group(1).strip().splitlines()
            snap.decisions = [
                ln.strip().lstrip("-").strip()
                for ln in lines
                if ln.strip().lstrip("-").strip()
            ]

        # Extract notes
        notes_match = re.search(r"\*\*Notes:\*\*\s*(.+?)$", block, flags=re.MULTILINE)
        if notes_match:
            snap.notes = notes_match.group(1).strip()

        return snap

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compare_sessions(
    log_path: Path,
    session_a: int,
    session_b: int,
) -> SessionComparison:
    """Compare two sessions from a NIGHTSHIFT_LOG.md file.

    Args:
        log_path: Path to the NIGHTSHIFT_LOG.md file.
        session_a: First (typically older) session number.
        session_b: Second (typically newer) session number.

    Returns:
        SessionComparison with deltas and side-by-side metrics.
    """
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
    else:
        content = ""

    snap_a = _extract_session(content, session_a) or SessionSnapshot(
        session_number=session_a, date="not found"
    )
    snap_b = _extract_session(content, session_b) or SessionSnapshot(
        session_number=session_b, date="not found"
    )

    # Build metrics list
    metrics = [
        DeltaMetric("Tasks", snap_a.task_count, snap_b.task_count),
        DeltaMetric("PRs", snap_a.pr_count, snap_b.pr_count),
        DeltaMetric("Decisions", len(snap_a.decisions), len(snap_b.decisions)),
    ]

    # Task set comparison
    set_a = set(snap_a.tasks)
    set_b = set(snap_b.tasks)
    tasks_added = sorted(set_b - set_a)
    tasks_removed = sorted(set_a - set_b)
    tasks_common = sorted(set_a & set_b)

    return SessionComparison(
        session_a=snap_a,
        session_b=snap_b,
        metrics=metrics,
        tasks_added=tasks_added,
        tasks_removed=tasks_removed,
        tasks_common=tasks_common,
    )
