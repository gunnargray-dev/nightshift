"""Session Timeline — ASCII art visual timeline of all Nightshift sessions.

Reads NIGHTSHIFT_LOG.md and renders a beautiful horizontal or vertical ASCII
timeline showing every session: date, PR count, key tasks, and cumulative
project growth.

The output is suitable for terminal display, markdown embedding, and
the GitHub Pages dashboard.

Public API
----------
build_timeline(log_path, repo_path) -> Timeline
render_timeline(timeline) -> str
save_timeline(timeline, out_path) -> None
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SessionNode:
    """A single session represented on the timeline."""

    session_number: int
    date: str
    pr_count: int
    task_count: int
    tasks: list[str] = field(default_factory=list)
    prs: list[str] = field(default_factory=list)
    cumulative_prs: int = 0
    cumulative_tests: int = 0
    highlight: str = ""  # Most notable task/achievement

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Timeline:
    """Full timeline of all sessions."""

    sessions: list[SessionNode] = field(default_factory=list)
    total_prs: int = 0
    total_sessions: int = 0
    first_session_date: str = ""
    latest_session_date: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        """Render the timeline as a Markdown document with ASCII art."""
        return render_timeline(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_SESSION_HEADER_RE = re.compile(
    r"^##\s+Session\s+(\d+)\s+[\u2014\u2013-]+\s+(.+)$", re.MULTILINE
)
_PR_LINE_RE = re.compile(r"PR\s*#(\d+)", re.IGNORECASE)
_TASK_ITEM_RE = re.compile(r"^\s*[-*\u2022]\s+.+", re.MULTILINE)
_ARROW_TASK_RE = re.compile(r"\u2192\s*(PR\s*#\d+\s+\u2014\s+)?(.+?)(?:\s*\.|$)")
_CHECKBOX_TASK_RE = re.compile(r"\u2705\s+(.+?)(?:\s+\u2192|\s*$)")


def _extract_highlight(tasks: list[str], prs: list[str]) -> str:
    """Pick the most interesting task for timeline display."""
    if not tasks:
        return prs[0][:50] if prs else "Session completed"
    for task in tasks:
        if any(kw in task.lower() for kw in ["src/", ".py", "module", "engine", "analyzer"]):
            return task[:60]
    return tasks[0][:60]


def _parse_log(log_path: Path) -> list[SessionNode]:
    """Parse NIGHTSHIFT_LOG.md and extract session nodes."""
    if not log_path.exists():
        return []

    text = log_path.read_text(encoding="utf-8")
    sections = _SESSION_HEADER_RE.split(text)

    nodes: list[SessionNode] = []
    i = 1
    while i < len(sections) - 2:
        session_num_str = sections[i].strip()
        date_str = sections[i + 1].strip()
        body = sections[i + 2] if i + 2 < len(sections) else ""

        try:
            session_num = int(session_num_str)
        except ValueError:
            i += 3
            continue

        pr_matches = _PR_LINE_RE.findall(body)
        pr_count = len(set(pr_matches))
        pr_labels = [f"#{n}" for n in sorted(set(pr_matches), key=int)]

        tasks = []
        for m in _CHECKBOX_TASK_RE.finditer(body):
            task = m.group(1).strip()
            if task and len(task) > 3:
                tasks.append(task)

        if not tasks:
            for m in _ARROW_TASK_RE.finditer(body):
                task = m.group(2).strip()
                if task and len(task) > 3 and not task.startswith("#"):
                    tasks.append(task)

        if not tasks:
            for m in _TASK_ITEM_RE.finditer(body):
                line = m.group(0).strip().lstrip("-*\u2022").strip()
                if line and len(line) > 5:
                    tasks.append(line[:80])

        date_clean = date_str.replace("\u2014", "").strip()
        highlight = _extract_highlight(tasks, pr_labels)

        node = SessionNode(
            session_number=session_num,
            date=date_clean,
            pr_count=max(pr_count, 1) if tasks else pr_count,
            task_count=len(tasks),
            tasks=tasks[:5],
            prs=pr_labels[:6],
            highlight=highlight,
        )
        nodes.append(node)
        i += 3

    nodes.sort(key=lambda n: n.session_number)

    cumulative = 0
    for node in nodes:
        cumulative += node.pr_count
        node.cumulative_prs = cumulative

    return nodes


def _shorten_date(date_str: str) -> str:
    """Convert 'February 27, 2026' to 'Feb 27'."""
    months = {
        "January": "Jan", "February": "Feb", "March": "Mar",
        "April": "Apr", "May": "May", "June": "Jun",
        "July": "Jul", "August": "Aug", "September": "Sep",
        "October": "Oct", "November": "Nov", "December": "Dec",
    }
    for full, short in months.items():
        if full in date_str:
            m = re.search(r"(\d{1,2})", date_str)
            if m:
                return f"{short} {m.group(1)}"
            return short
    return date_str[:8].strip()


def render_timeline(timeline: "Timeline") -> str:
    """Render the full ASCII timeline."""
    if not timeline.sessions:
        return "# Session Timeline\n\nNo sessions found in NIGHTSHIFT_LOG.md.\n"

    sessions = timeline.sessions
    total_sessions = len(sessions)
    lines: list[str] = []

    lines.append("# \U0001f319 Nightshift \u2014 Session Timeline")
    lines.append("")
    lines.append(
        f"**{total_sessions} sessions** \u00b7 "
        f"**{timeline.total_prs} total PRs** \u00b7 "
        f"First: {timeline.first_session_date} \u00b7 "
        f"Latest: {timeline.latest_session_date}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    SPACING = 5
    rail_parts: list[str] = []

    for i, s in enumerate(sessions):
        label = f"S{s.session_number}"
        rail_parts.append(label)
        if i < len(sessions) - 1:
            rail_parts.append("\u2500" * SPACING)

    lines.append("```")
    lines.append("Timeline Rail")
    lines.append("")
    lines.append("  " + "".join(rail_parts))

    date_line_parts: list[str] = []
    for i, s in enumerate(sessions):
        short_date = _shorten_date(s.date)
        label_w = len(f"S{s.session_number}")
        date_label = short_date[:label_w + 2]
        date_line_parts.append(date_label.ljust(label_w))
        if i < len(sessions) - 1:
            date_line_parts.append(" " * SPACING)
    lines.append("  " + "".join(date_line_parts))
    lines.append("")

    bar_width = 20
    lines.append("  PRs per session:")
    lines.append("")
    for s in sessions:
        bar = "\u2588" * min(s.pr_count * 3, bar_width)
        count_str = str(s.pr_count).rjust(2)
        lines.append(f"  S{str(s.session_number).ljust(2)}  {count_str} \u2502{bar}")

    lines.append("")
    lines.append("  Cumulative PRs:")
    lines.append("")
    max_cum = max(s.cumulative_prs for s in sessions)
    for s in sessions:
        ratio = s.cumulative_prs / max(max_cum, 1)
        filled = int(ratio * bar_width)
        bar = "\u2593" * filled + "\u2591" * (bar_width - filled)
        lines.append(f"  S{str(s.session_number).ljust(2)} {str(s.cumulative_prs).rjust(3)} \u2502{bar}\u2502")

    lines.append("")
    lines.append("```")
    lines.append("")

    lines.append("## Session Details")
    lines.append("")

    for s in sessions:
        lines.append(f"### Session {s.session_number} \u2014 {s.date}")
        lines.append("")
        pr_str = f"{s.pr_count} PR{'s' if s.pr_count != 1 else ''}"
        task_str = f"{s.task_count} task{'s' if s.task_count != 1 else ''}"
        cum_str = f"cumulative: {s.cumulative_prs} PRs"
        lines.append(f"**{pr_str}** \u00b7 **{task_str}** \u00b7 _{cum_str}_")
        lines.append("")
        if s.highlight:
            lines.append(f"> \u2605 {s.highlight}")
            lines.append("")
        if s.prs:
            lines.append(f"**PRs:** {', '.join(s.prs)}")
            lines.append("")
        if s.tasks:
            lines.append("**Tasks:**")
            for task in s.tasks:
                lines.append(f"- {task}")
            lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(
        f"_Generated by `nightshift timeline` \u00b7 "
        f"{total_sessions} sessions \u00b7 "
        f"{timeline.total_prs} PRs total_"
    )
    lines.append("")

    return "\n".join(lines)


def build_timeline(
    log_path: Optional[Path] = None,
    repo_path: Optional[Path] = None,
) -> Timeline:
    """Parse the NIGHTSHIFT_LOG.md and build a Timeline object."""
    if log_path is None:
        root = repo_path or Path.cwd()
        log_path = root / "NIGHTSHIFT_LOG.md"

    sessions = _parse_log(log_path)
    total_prs = sum(s.pr_count for s in sessions)
    first_date = sessions[0].date if sessions else ""
    latest_date = sessions[-1].date if sessions else ""

    return Timeline(
        sessions=sessions,
        total_prs=total_prs,
        total_sessions=len(sessions),
        first_session_date=first_date,
        latest_session_date=latest_date,
    )


def save_timeline(timeline: Timeline, out_path: Path) -> None:
    """Write the rendered Markdown timeline to *out_path*."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(timeline.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(timeline.to_json(), encoding="utf-8")
