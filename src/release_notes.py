"""Release notes generator for awake sessions."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ReleaseEntry:
    """A single line item in the release notes."""

    category: str  # e.g. 'feat', 'fix', 'chore'
    scope: Optional[str]  # e.g. 'api', 'dashboard'
    description: str
    pr_number: Optional[int] = None
    breaking: bool = False


@dataclass
class ReleaseNotes:
    """Structured release notes for one version."""

    version: str
    release_date: date
    entries: list[ReleaseEntry] = field(default_factory=list)
    intro: Optional[str] = None


# ---------------------------------------------------------------------------
# Conventional-commit parser
# ---------------------------------------------------------------------------

_CC_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$"
)

_CATEGORY_ORDER = [
    "feat",
    "fix",
    "perf",
    "refactor",
    "test",
    "docs",
    "chore",
    "ci",
    "build",
    "style",
]

_CATEGORY_LABELS: dict[str, str] = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "perf": "Performance",
    "refactor": "Refactoring",
    "test": "Tests",
    "docs": "Documentation",
    "chore": "Chores",
    "ci": "CI / Build",
    "build": "CI / Build",
    "style": "Style",
}


def parse_commit(
    message: str,
    pr_number: Optional[int] = None,
) -> Optional[ReleaseEntry]:
    """
    Parse a conventional-commit message into a ReleaseEntry.

    Args:
        message: The commit message (first line).
        pr_number: Optional PR number to attach.

    Returns:
        A ReleaseEntry, or None if the message doesn't match.
    """
    m = _CC_RE.match(message.strip())
    if not m:
        return None
    return ReleaseEntry(
        category=m.group("type"),
        scope=m.group("scope"),
        description=m.group("desc").strip(),
        pr_number=pr_number,
        breaking=bool(m.group("breaking")),
    )


def parse_commits(
    messages: list[str],
    pr_numbers: Optional[list[Optional[int]]] = None,
) -> list[ReleaseEntry]:
    """
    Parse a list of commit messages.

    Args:
        messages: List of commit message strings.
        pr_numbers: Parallel list of optional PR numbers.

    Returns:
        List of successfully parsed ReleaseEntry objects.
    """
    if pr_numbers is None:
        pr_numbers = [None] * len(messages)

    entries = []
    for msg, pr in zip(messages, pr_numbers):
        entry = parse_commit(msg, pr_number=pr)
        if entry:
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_markdown(
    notes: ReleaseNotes,
    *,
    include_date: bool = True,
    link_prs: Optional[str] = None,
) -> str:
    """
    Render a ReleaseNotes object to a Markdown string.

    Args:
        notes: The ReleaseNotes to render.
        include_date: Whether to include the release date in the heading.
        link_prs: Base URL for PR links, e.g. 'https://github.com/owner/repo/pull'.
                  If None, PR numbers are rendered as plain text.

    Returns:
        Markdown-formatted release notes.
    """
    lines = []
    date_str = f" ({notes.release_date.isoformat()})" if include_date else ""
    lines.append(f"## {notes.version}{date_str}")

    if notes.intro:
        lines.append("")
        lines.append(notes.intro)

    # Group by category
    buckets: dict[str, list[ReleaseEntry]] = {}
    for entry in notes.entries:
        buckets.setdefault(entry.category, []).append(entry)

    # Render in canonical order, then any unknown categories alphabetically
    known = [c for c in _CATEGORY_ORDER if c in buckets]
    unknown = sorted(c for c in buckets if c not in _CATEGORY_ORDER)

    for cat in known + unknown:
        label = _CATEGORY_LABELS.get(cat, cat.title())
        lines.append("")
        lines.append(f"### {label}")
        for entry in buckets[cat]:
            scope_str = f"**{entry.scope}:** " if entry.scope else ""
            breaking_str = " **(BREAKING)**" if entry.breaking else ""
            pr_str = ""
            if entry.pr_number:
                if link_prs:
                    pr_str = f" ([#{entry.pr_number}]({link_prs}/{entry.pr_number}))"
                else:
                    pr_str = f" (#{entry.pr_number})"
            lines.append(f"- {scope_str}{entry.description}{breaking_str}{pr_str}")

    return "\n".join(lines) + "\n"


def generate_release_notes(
    version: str,
    commit_messages: list[str],
    *,
    release_date: Optional[date] = None,
    pr_numbers: Optional[list[Optional[int]]] = None,
    intro: Optional[str] = None,
    link_prs: Optional[str] = None,
    include_date: bool = True,
) -> str:
    """
    High-level helper: parse commits and render Markdown release notes.

    Args:
        version: Semantic version string, e.g. '1.2.0'.
        commit_messages: Raw commit message strings.
        release_date: Release date (defaults to today).
        pr_numbers: Optional parallel list of PR numbers.
        intro: Optional introductory paragraph.
        link_prs: Base URL for PR hyperlinks.
        include_date: Whether to show the date in the heading.

    Returns:
        Markdown release notes string.
    """
    entries = parse_commits(commit_messages, pr_numbers=pr_numbers)
    notes = ReleaseNotes(
        version=version,
        release_date=release_date or date.today(),
        entries=entries,
        intro=intro,
    )
    return render_markdown(notes, link_prs=link_prs, include_date=include_date)
