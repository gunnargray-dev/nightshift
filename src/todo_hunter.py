"""Stale TODO/FIXME hunter for Nightshift.

Scans every Python file in ``src/`` for TODO, FIXME, HACK, XXX, and NOTE
comments.  Maps each annotation to the session when it was introduced (via
``git log``), computes its age in sessions, and flags items that have been
sitting unresolved for more than ``threshold`` sessions.

Output:

- A list of ``TodoItem`` objects with file, line, text, session age
- A Markdown report suitable for filing as a GitHub issue or pasting into
  the session log
- Optional JSON export for integration with brain.py

Usage::

    from src.todo_hunter import hunt, render_todo_report, save_todo_report
    items = hunt(src_path=Path("src"), current_session=10, threshold=2)
    print(render_todo_report(items, current_session=10))
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

TODO_PATTERN = re.compile(
    r"#\s*(TODO|FIXME|HACK|XXX|NOTE)\s*[:\-]?\s*(.*)",
    re.IGNORECASE,
)

SEVERITY_ORDER = {"FIXME": 0, "HACK": 1, "XXX": 1, "TODO": 2, "NOTE": 3}


@dataclass
class TodoItem:
    """A single TODO/FIXME/HACK/XXX annotation found in a source file."""

    file: str           # relative path e.g. "src/health.py"
    line: int           # 1-based line number
    tag: str            # "TODO", "FIXME", "HACK", "XXX", or "NOTE"
    text: str           # The comment text after the tag
    introduced_session: Optional[int]  # Session when this line was first committed
    age_sessions: int   # current_session - introduced_session (0 if unknown)
    is_stale: bool      # True if age_sessions >= threshold

    @property
    def severity(self) -> int:
        """Lower = more severe.  FIXME=0, HACK/XXX=1, TODO=2, NOTE=3."""
        return SEVERITY_ORDER.get(self.tag.upper(), 9)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "file": self.file,
            "line": self.line,
            "tag": self.tag,
            "text": self.text,
            "introduced_session": self.introduced_session,
            "age_sessions": self.age_sessions,
            "is_stale": self.is_stale,
        }


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout; return '' on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=10, cwd=str(cwd),
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _session_from_commit(commit_sha: str, repo_root: Path) -> Optional[int]:
    """Extract the Nightshift session number from a commit's log message.

    Looks for patterns like 'Session: 3' or '[nightshift] ... session-4-...'
    in the commit subject + body.
    """
    if not commit_sha:
        return None
    log = _run_git(["log", "--format=%s%n%b", "-n", "1", commit_sha], repo_root)
    m = re.search(r"[Ss]ession[:\s]+(\d+)", log)
    if m:
        return int(m.group(1))
    # Try branch name pattern: nightshift/session-4-something
    m2 = re.search(r"nightshift/session-(\d+)", log, re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    return None


def _blame_line(file_path: Path, line_number: int, repo_root: Path) -> Optional[str]:
    """Return the commit SHA responsible for *line_number* in *file_path*."""
    rel = str(file_path.relative_to(repo_root))
    out = _run_git(
        ["blame", "-L", f"{line_number},{line_number}", "--porcelain", rel],
        repo_root,
    )
    if not out:
        return None
    # First line of porcelain blame output is: <sha> <orig_line> <final_line> ...
    sha = out.split()[0] if out.split() else None
    if sha and len(sha) >= 7 and sha != "0" * 40:
        return sha
    return None


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def _find_repo_root(start: Path) -> Path:
    """Walk up from *start* to find the git repo root."""
    current = start.resolve()
    for _ in range(10):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start.resolve()


def hunt(
    src_path: Path,
    current_session: int,
    threshold: int = 2,
) -> list[TodoItem]:
    """Scan *src_path* for stale TODO/FIXME/HACK/XXX annotations.

    Args:
        src_path: Path to the ``src/`` directory.
        current_session: The current session number (used to compute age).
        threshold: Items older than this many sessions are flagged as stale.

    Returns:
        List of TodoItem sorted by (severity, age_sessions desc, file, line).
    """
    repo_root = _find_repo_root(src_path)
    items: list[TodoItem] = []

    py_files = sorted(src_path.glob("*.py"))
    for py_file in py_files:
        try:
            lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for lineno, line_text in enumerate(lines, start=1):
            m = TODO_PATTERN.search(line_text)
            if not m:
                continue

            tag = m.group(1).upper()
            text = m.group(2).strip()

            # Try to get the blame commit for this line
            sha = _blame_line(py_file, lineno, repo_root)
            introduced = _session_from_commit(sha, repo_root) if sha else None

            if introduced is not None:
                age = max(0, current_session - introduced)
            else:
                age = 0

            items.append(TodoItem(
                file=str(py_file.relative_to(repo_root)),
                line=lineno,
                tag=tag,
                text=text,
                introduced_session=introduced,
                age_sessions=age,
                is_stale=age >= threshold,
            ))

    # Sort: severity asc, age desc, then file/line
    items.sort(key=lambda i: (i.severity, -i.age_sessions, i.file, i.line))
    return items


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_todo_report(
    items: list[TodoItem],
    current_session: int,
    threshold: int = 2,
) -> str:
    """Render TODO items as a Markdown report.

    Args:
        items: List of TodoItem (typically from ``hunt()``).
        current_session: Current session number for context.
        threshold: Sessions threshold used to classify items as stale.

    Returns:
        Markdown string.
    """
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stale = [i for i in items if i.is_stale]
    fresh = [i for i in items if not i.is_stale]

    lines: list[str] = [
        "# TODO / FIXME Hunter Report",
        "",
        f"*Generated {generated_at}  |  Session {current_session}  |  Stale threshold: {threshold} sessions*",
        "",
        f"**Total annotations:** {len(items)}  "
        f"**Stale (>= {threshold} sessions old):** {len(stale)}  "
        f"**Recent:** {len(fresh)}",
        "",
    ]

    if stale:
        lines += ["## Stale Annotations", ""]
        lines += [
            "| File | Line | Tag | Text | Introduced | Age |",
            "|------|------|-----|------|------------|-----|",
        ]
        for item in stale:
            intro = f"Session {item.introduced_session}" if item.introduced_session is not None else "unknown"
            age_str = f"{item.age_sessions}s" if item.introduced_session is not None else "?"
            lines.append(
                f"| `{item.file}` | {item.line} | **{item.tag}** "
                f"| {item.text[:60]} | {intro} | {age_str} |"
            )
        lines.append("")

    if fresh:
        lines += ["## Recent Annotations", ""]
        lines += [
            "| File | Line | Tag | Text | Introduced |",
            "|------|------|-----|------|------------|",
        ]
        for item in fresh:
            intro = f"Session {item.introduced_session}" if item.introduced_session is not None else "unknown"
            lines.append(
                f"| `{item.file}` | {item.line} | {item.tag} "
                f"| {item.text[:60]} | {intro} |"
            )
        lines.append("")

    if not items:
        lines += ["✅ No TODO/FIXME/HACK/XXX annotations found.", ""]

    lines.append("---")
    lines.append("")
    lines.append("*Generated by `src/todo_hunter.py` — Nightshift autonomous development system.*")

    return "\n".join(lines)


def save_todo_report(
    items: list[TodoItem],
    out_path: Path,
    current_session: int,
    threshold: int = 2,
) -> None:
    """Write the TODO report to *out_path* and a JSON sidecar.

    Args:
        items: List of TodoItem.
        out_path: Where to write the Markdown report.
        current_session: Current session number.
        threshold: Stale threshold in sessions.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_todo_report(items, current_session, threshold),
        encoding="utf-8",
    )

    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "current_session": current_session,
                "threshold": threshold,
                "total": len(items),
                "stale_count": sum(1 for i in items if i.is_stale),
                "items": [i.to_dict() for i in items],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
