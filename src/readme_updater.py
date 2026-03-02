"""Automated README updater for awake sessions."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class SessionSummary:
    """Summary of a single awake session."""

    date: str  # ISO-8601, e.g. '2025-03-01'
    features: list[str]
    tests_added: int
    prs_merged: int
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_SECTION_HEADER_RE = re.compile(
    r"^#{1,3}\s+Session\s+Log",
    re.IGNORECASE | re.MULTILINE,
)

_SESSION_BLOCK_RE = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2})\b",
    re.MULTILINE,
)


def _find_section_bounds(content: str) -> tuple[int, int]:
    """
    Return (start, end) character offsets for the 'Session Log' section.

    'start' points to the '#' of the header line.
    'end' points to the start of the next same-or-higher-level section,
    or end-of-string if none exists.
    """
    m = _SECTION_HEADER_RE.search(content)
    if not m:
        return len(content), len(content)  # section not found

    start = m.start()
    header_hashes = re.match(r"^(#+)", content[start:]).group(1)
    level = len(header_hashes)

    # Find next heading of equal or higher importance
    next_section_re = re.compile(
        rf"^#{{1,{level}}}(?!#)\s",
        re.MULTILINE,
    )
    nxt = next_section_re.search(content, m.end())
    end = nxt.start() if nxt else len(content)
    return start, end


def parse_session_log(content: str) -> list[SessionSummary]:
    """
    Parse the 'Session Log' section of a README and return a list of sessions.

    Args:
        content: Full README text.

    Returns:
        List of SessionSummary objects, newest-first.
    """
    start, end = _find_section_bounds(content)
    section = content[start:end]

    entries = []
    for m in _SESSION_BLOCK_RE.finditer(section):
        date = m.group(1)
        # Collect lines until next session block or end
        block_start = m.end()
        nxt = _SESSION_BLOCK_RE.search(section, block_start)
        block_end = nxt.start() if nxt else len(section)
        block = section[block_start:block_end]

        features = re.findall(r"^-\s+(.+)", block, re.MULTILINE)
        tests_m = re.search(r"(\d+)\s+test", block, re.IGNORECASE)
        prs_m = re.search(r"(\d+)\s+PR", block, re.IGNORECASE)
        notes_m = re.search(r"Notes?:\s*(.+)", block, re.IGNORECASE)

        entries.append(
            SessionSummary(
                date=date,
                features=features,
                tests_added=int(tests_m.group(1)) if tests_m else 0,
                prs_merged=int(prs_m.group(1)) if prs_m else 0,
                notes=notes_m.group(1).strip() if notes_m else None,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_session_block(session: SessionSummary) -> str:
    lines = [f"### {session.date}"]
    for feat in session.features:
        lines.append(f"- {feat}")
    meta_parts = []
    if session.tests_added:
        meta_parts.append(f"{session.tests_added} tests added")
    if session.prs_merged:
        meta_parts.append(f"{session.prs_merged} PRs merged")
    if meta_parts:
        lines.append("\n" + ", ".join(meta_parts))
    if session.notes:
        lines.append(f"\nNotes: {session.notes}")
    return "\n".join(lines) + "\n"


def render_session_log(sessions: list[SessionSummary]) -> str:
    """
    Render a sorted 'Session Log' section from a list of sessions.

    Args:
        sessions: List of SessionSummary objects (any order).

    Returns:
        Markdown string for the entire section.
    """
    sorted_sessions = sorted(sessions, key=lambda s: s.date, reverse=True)
    lines = ["## Session Log\n"]
    for session in sorted_sessions:
        lines.append(_render_session_block(session))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# High-level update helpers
# ---------------------------------------------------------------------------


def update_readme(
    readme_path: str,
    new_session: SessionSummary,
    *,
    create_section_if_missing: bool = True,
) -> str:
    """
    Insert or update a session entry in a README file.

    Args:
        readme_path: Path to the README.md file.
        new_session: Session to add or replace.
        create_section_if_missing: If True, append a new section when none exists.

    Returns:
        The updated README content as a string.
    """
    path = Path(readme_path)
    content = path.read_text(encoding="utf-8") if path.exists() else ""

    start, end = _find_section_bounds(content)
    section_exists = start < len(content)

    if section_exists:
        section_content = content[start:end]
        existing = parse_session_log(content)
        # Remove duplicate if same date
        sessions = [s for s in existing if s.date != new_session.date]
        sessions.append(new_session)
        new_section = render_session_log(sessions)
        content = content[:start] + new_section + content[end:]
    elif create_section_if_missing:
        content = content.rstrip() + "\n\n" + render_session_log([new_session]) + "\n"

    return content


def write_readme(
    readme_path: str,
    new_session: SessionSummary,
    *,
    create_section_if_missing: bool = True,
) -> None:
    """
    Update the README file in-place with a new session entry.

    Args:
        readme_path: Path to the README.md file.
        new_session: Session to add or replace.
        create_section_if_missing: If True, create the section when absent.
    """
    updated = update_readme(
        readme_path,
        new_session,
        create_section_if_missing=create_section_if_missing,
    )
    Path(readme_path).write_text(updated, encoding="utf-8")
