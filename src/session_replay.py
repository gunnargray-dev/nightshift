"""Session replay module for Nightshift.

Reconstructs a complete picture of what any past session did, sourced
entirely from NIGHTSHIFT_LOG.md.  Given a session number, ``replay()``
returns a ``SessionReplay`` object with:

- Session metadata (date, operator, session number)
- List of tasks completed with their PR references
- List of pull requests opened
- Key decisions made
- Stats snapshot
- A plain-English "what happened" narrative

Usage::

    from src.session_replay import replay, replay_all
    r = replay(log_path=Path("NIGHTSHIFT_LOG.md"), session_number=3)
    print(r.to_markdown())

    all_sessions = replay_all(log_path=Path("NIGHTSHIFT_LOG.md"))
    for s in all_sessions:
        print(s.session_number, s.task_count, s.pr_count)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ReplayedPR:
    """A single PR as recorded in the session log."""

    number: int
    title: str
    url: str
    branch: str

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "branch": self.branch,
        }


@dataclass
class ReplayedTask:
    """A single completed task as recorded in the session log."""

    name: str
    description: str
    status: str  # "completed" | "partial" | "skipped"
    pr_number: Optional[int]
    pr_url: str

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
        }


@dataclass
class SessionReplay:
    """Complete reconstruction of a single past session."""

    session_number: int
    date: str
    operator: str
    tasks: list[ReplayedTask]
    prs: list[ReplayedPR]
    decisions: list[str]
    stats_snapshot: dict
    notes: str
    raw_section: str

    @property
    def task_count(self) -> int:
        """Number of completed tasks in this session."""
        return len([t for t in self.tasks if t.status == "completed"])

    @property
    def pr_count(self) -> int:
        """Number of PRs opened in this session."""
        return len(self.prs)

    @property
    def modules_added(self) -> list[str]:
        """Extract module file names mentioned in task descriptions."""
        modules = []
        for task in self.tasks:
            found = re.findall(r"`?(src/\w+\.py)`?", task.description)
            modules.extend(found)
        return list(dict.fromkeys(modules))

    def narrative(self) -> str:
        """Generate a plain-English summary of what this session did."""
        lines = [f"Session {self.session_number} ran on {self.date}.", ""]

        if self.tasks:
            completed = [t for t in self.tasks if t.status == "completed"]
            partial = [t for t in self.tasks if t.status == "partial"]
            skipped = [t for t in self.tasks if t.status == "skipped"]

            task_parts = []
            if completed:
                task_parts.append(f"completed {len(completed)} task(s)")
            if partial:
                task_parts.append(f"partially completed {len(partial)} task(s)")
            if skipped:
                task_parts.append(f"skipped {len(skipped)} task(s)")

            lines.append("Computer " + " and ".join(task_parts) + ":")
            for task in completed:
                pr_ref = f" (PR #{task.pr_number})" if task.pr_number else ""
                lines.append(f"  - {task.name}{pr_ref}: {task.description[:100]}")

        if self.prs:
            lines += ["", f"Opened {len(self.prs)} PR(s):"]
            for pr in self.prs:
                lines.append(f"  - PR #{pr.number}: {pr.title}")

        modules = self.modules_added
        if modules:
            lines += ["", f"New modules added: {', '.join(modules)}"]

        if self.stats_snapshot:
            lines += ["", "Stats at end of session:"]
            for k, v in self.stats_snapshot.items():
                lines.append(f"  - {k.replace('_', ' ').title()}: {v}")

        if self.notes:
            lines += ["", f"Notes: {self.notes}"]

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the replay as a Markdown document."""
        lines = [
            f"# Session {self.session_number} Replay",
            "",
            f"**Date:** {self.date}  ",
            f"**Operator:** {self.operator}  ",
            f"**Tasks completed:** {self.task_count}  ",
            f"**PRs opened:** {self.pr_count}  ",
            "",
        ]

        if self.tasks:
            lines += ["## Tasks", ""]
            for task in self.tasks:
                icon = {"completed": "✅", "partial": "⚠️", "skipped": "⏭️"}.get(
                    task.status, "❓"
                )
                pr_ref = ""
                if task.pr_number:
                    if task.pr_url:
                        pr_ref = f" → [PR #{task.pr_number}]({task.pr_url})"
                    else:
                        pr_ref = f" → PR #{task.pr_number}"
                lines.append(f"- {icon} **{task.name}**{pr_ref}: {task.description}")

        if self.prs:
            lines += ["", "## Pull Requests", ""]
            for pr in self.prs:
                url_part = f"[#{pr.number}]({pr.url})" if pr.url else f"#{pr.number}"
                branch_part = f" (`{pr.branch}`)" if pr.branch else ""
                lines.append(f"- {url_part} — {pr.title}{branch_part}")

        if self.decisions:
            lines += ["", "## Key Decisions", ""]
            for d in self.decisions:
                lines.append(f"- {d}")

        if self.stats_snapshot:
            lines += ["", "## Stats Snapshot", ""]
            for k, v in self.stats_snapshot.items():
                lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")

        modules = self.modules_added
        if modules:
            lines += ["", "## Modules Added", ""]
            for m in modules:
                lines.append(f"- `{m}`")

        lines += ["", "## Narrative", "", self.narrative()]
        lines += ["", "---", "", "*Replayed from NIGHTSHIFT_LOG.md by `src/session_replay.py`.*"]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "session_number": self.session_number,
            "date": self.date,
            "operator": self.operator,
            "task_count": self.task_count,
            "pr_count": self.pr_count,
            "tasks": [t.to_dict() for t in self.tasks],
            "prs": [p.to_dict() for p in self.prs],
            "decisions": self.decisions,
            "stats_snapshot": self.stats_snapshot,
            "modules_added": self.modules_added,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def replay(log_path: Path, session_number: int) -> SessionReplay:
    """Replay a single session from NIGHTSHIFT_LOG.md."""
    log_text = log_path.read_text(encoding="utf-8")
    sections = _split_sessions(log_text)
    for s in sections:
        if s[0] == session_number:
            return _parse_session_section(s[1], session_number)

    raise ValueError(f"Session {session_number} not found in log")


def replay_all(log_path: Path) -> list[SessionReplay]:
    """Replay all sessions in chronological order."""
    log_text = log_path.read_text(encoding="utf-8")
    sections = _split_sessions(log_text)
    out = []
    for session_number, section_text in sections:
        out.append(_parse_session_section(section_text, session_number))
    return out


# ---------------------------------------------------------------------------
# Parsing logic
# ---------------------------------------------------------------------------

def _split_sessions(log_text: str) -> list[tuple[int, str]]:
    """Split the full log into individual session sections."""
    # Session headings are: "## Session N — ..."
    # Using a capturing group to keep the session number.
    parts = re.split(r"^##\s+Session\s+(\d+)\b", log_text, flags=re.MULTILINE)

    # re.split returns: [prefix, num1, section1, num2, section2, ...]
    out: list[tuple[int, str]] = []
    it = iter(parts[1:])
    for num_str, section_body in zip(it, it):
        num = int(num_str)
        section_text = f"## Session {num_str}{section_body}"
        out.append((num, section_text))
    return out


def _parse_session_section(section_text: str, session_number: int) -> SessionReplay:
    """Parse a session section into a SessionReplay."""
    # Header: "## Session N — Month Day, Year"
    header_match = re.search(r"^##\s+Session\s+\d+\s+—\s+(.+)$", section_text, re.MULTILINE)
    date = header_match.group(1).strip() if header_match else ""

    operator_match = re.search(r"\*\*Operator:\*\*\s*(.+)$", section_text, re.MULTILINE)
    operator = operator_match.group(1).strip() if operator_match else ""

    tasks: list[ReplayedTask] = []
    tasks_section = re.search(
        r"\*\*Tasks completed:\*\*\s*\n(.*?)(?:\n\*\*|\Z)",
        section_text,
        re.DOTALL,
    )
    if tasks_section:
        task_text = tasks_section.group(1)
        for line in task_text.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue

            # Expected format:
            # - ✅ **Task name** → [PR #12](url) — description
            status = "completed"
            if "⚠️" in line:
                status = "partial"
            if "⏭️" in line:
                status = "skipped"

            name_match = re.search(r"\*\*(.+?)\*\*", line)
            name = name_match.group(1).strip() if name_match else "Unknown"

            pr_match = re.search(r"\[PR\s+#(\d+)\]\((https?://[^\)]+)\)", line)
            pr_number = int(pr_match.group(1)) if pr_match else None
            pr_url = pr_match.group(2) if pr_match else ""

            desc_match = re.search(r"\u2014\s*(.+)$", line)
            description = desc_match.group(1).strip() if desc_match else ""

            tasks.append(ReplayedTask(
                name=name,
                description=description,
                status=status,
                pr_number=pr_number,
                pr_url=pr_url,
            ))

    prs: list[ReplayedPR] = []
    prs_section = re.search(
        r"\*\*Pull requests:\*\*\s*\n(.*?)(?:\n\*\*|\Z)",
        section_text,
        re.DOTALL,
    )
    if prs_section:
        pr_text = prs_section.group(1)
        for line in pr_text.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            pr_match = re.search(r"\[#(\d+)\]\((https?://[^\)]+)\)", line)
            number_only = re.search(r"#(\d+)", line)
            pr_num = int(pr_match.group(1)) if pr_match else (
                int(number_only.group(1)) if number_only else 0
            )
            pr_url = pr_match.group(2) if pr_match else ""

            title_match = re.search(r"\u2014\s*(.+?)(?:\s*\(`.+`\))?$", line)
            pr_title = title_match.group(1).strip() if title_match else line[:60]

            # Branch is usually recorded as: — title (`branch-name`)
            # but some older logs embedded the branch inside the title, e.g.:
            #   — [nightshift] feat: ... (`nightshift/session-1-foo`))
            # so we try both patterns.
            branch_match = re.search(r"\(`([^`]+)`\)\s*$", line)
            if branch_match:
                branch = branch_match.group(1).strip("() ")
            else:
                branch_match = re.search(r"\(`([^`]+)`\)\)+\s*$", line)
                branch = branch_match.group(1).strip("() ") if branch_match else ""

            if pr_num:
                prs.append(ReplayedPR(
                    number=pr_num,
                    title=pr_title,
                    url=pr_url,
                    branch=branch,
                ))

    decisions: list[str] = []
    decisions_section = re.search(
        r"\*\*Decisions & rationale:\*\*\s*\n(.*?)(?:\n\*\*|\Z)",
        section_text,
        re.DOTALL,
    )
    if decisions_section:
        for line in decisions_section.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                decisions.append(line[2:])

    stats: dict = {}
    stats_section = re.search(
        r"\*\*Stats snapshot:\*\*\s*\n(.*?)(?:\n\*\*|\Z)",
        section_text,
        re.DOTALL,
    )
    if stats_section:
        for line in stats_section.group(1).splitlines():
            line = line.strip()
            if ": " in line and line.startswith("- "):
                key, _, val = line[2:].partition(": ")
                stats[key.strip().lower().replace(" ", "_")] = val.strip()

    notes_match = re.search(r"\*\*Notes:\*\*\s*(.+?)(?:\n---|\Z)", section_text, re.DOTALL)
    notes = notes_match.group(1).strip() if notes_match else ""

    return SessionReplay(
        session_number=session_number,
        date=date,
        operator=operator,
        tasks=tasks,
        prs=prs,
        decisions=decisions,
        stats_snapshot=stats,
        notes=notes,
        raw_section=section_text,
    )
