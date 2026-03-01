"""Session logger for Awake.

Generates structured, append-only entries for AWAKE_LOG.md at the end
of each autonomous development session. Records decisions, outcomes, and
metadata that make the log machine-readable and human-meaningful.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import re


@dataclass
class PRRecord:
    """Record of a single pull request opened during a session."""

    number: int
    title: str
    branch: str
    url: str = ""
    status: str = "open"  # open | merged | closed

    def to_dict(self) -> dict:
        """Return a dictionary representation of the PR record"""
        return asdict(self)


@dataclass
class TaskRecord:
    """Record of a single task completed during a session."""

    name: str
    description: str
    status: str = "completed"  # completed | partial | skipped
    pr: Optional[PRRecord] = None

    def to_dict(self) -> dict:
        """Return a dictionary representation of the task record"""
        d = asdict(self)
        return d


@dataclass
class SessionEntry:
    """Full record of one autonomous development session."""

    session_number: int
    date: str = ""
    operator: str = "Computer (autonomous)"
    tasks: list[TaskRecord] = field(default_factory=list)
    prs: list[PRRecord] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    stats_snapshot: dict = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self):
        if not self.date:
            self.date = datetime.now(timezone.utc).strftime("%B %d, %Y")

    def to_dict(self) -> dict:
        """Return a dictionary representation of the session entry"""
        return asdict(self)

    def to_markdown(self) -> str:
        """Render the session entry as a Markdown section for AWAKE_LOG.md."""
        lines = [
            f"## Session {self.session_number} — {self.date}",
            "",
            f"**Operator:** {self.operator}  ",
        ]

        # Tasks
        if self.tasks:
            lines += ["", "**Tasks completed:**", ""]
            for task in self.tasks:
                status_icon = {"completed": "✅", "partial": "⚠️", "skipped": "⏭️"}.get(
                    task.status, "❓"
                )
                pr_ref = ""
                if task.pr:
                    pr_ref = f" → PR #{task.pr.number}"
                    if task.pr.url:
                        pr_ref = f" → [PR #{task.pr.number}]({task.pr.url})"
                lines.append(f"- {status_icon} **{task.name}**{pr_ref} — {task.description}")

        # PRs
        if self.prs:
            lines += ["", "**Pull requests:**", ""]
            for pr in self.prs:
                url_part = f"[#{pr.number}]({pr.url})" if pr.url else f"#{pr.number}"
                lines.append(f"- {url_part} — {pr.title} (`{pr.branch}`))"

        # Decisions
        if self.decisions:
            lines += ["", "**Decisions & rationale:**", ""]
            for decision in self.decisions:
                lines.append(f"- {decision}")

        # Stats snapshot
        if self.stats_snapshot:
            lines += ["", "**Stats snapshot:**", ""]
            for key, val in self.stats_snapshot.items():
                label = key.replace("_", " ").title()
                lines.append(f"- {label}: {val}")

        # Notes
        if self.notes:
            lines += ["", f"**Notes:** {self.notes}"]

        lines += ["", "---", ""]
        return "\n".join(lines)


def append_session_to_log(
    log_path: Path,
    entry: SessionEntry,
    *,
    dry_run: bool = False,
) -> str:
    """Append a session entry to AWAKE_LOG.md.

    Args:
        log_path: Path to the log file.
        entry: The SessionEntry to append.
        dry_run: If True, return the new content without writing.

    Returns:
        The full new log content.
    """
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
    else:
        existing = "# Awake Log\n\nAppend-only record of every autonomous development session.\n\n---\n\n"

    new_section = entry.to_markdown()

    # Insert before the final "Next entry" footer line if present
    footer_pattern = r"\n\*Next entry will be written autonomously by Computer\.\*\s*$"
    if re.search(footer_pattern, existing):
        updated = re.sub(footer_pattern, f"\n{new_section}", existing)
    else:
        # Append after the last --- separator
        updated = existing.rstrip() + f"\n\n{new_section}"

    if not dry_run:
        log_path.write_text(updated, encoding="utf-8")

    return updated


def load_session_history(log_path: Path) -> list[dict]:
    """Extract minimal session metadata from the log file for history tracking."""
    if not log_path.exists():
        return []

    content = log_path.read_text(encoding="utf-8")
    sessions = []

    for match in re.finditer(
        r"## Session (\d+) — (.+?)$", content, flags=re.MULTILINE
    ):
        sessions.append(
            {
                "session": int(match.group(1)),
                "date": match.group(2).strip(),
            }
        )

    return sessions


def format_session_json(entry: SessionEntry) -> str:
    """Serialize a SessionEntry to compact JSON for machine consumption."""
    return json.dumps(entry.to_dict(), indent=2, default=str)
