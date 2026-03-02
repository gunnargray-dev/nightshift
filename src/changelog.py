"""Changelog generation utilities."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from .utils import run_cmd

# Conventional-commit prefix -> changelog section
_SECTION_MAP: dict[str, str] = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "perf": "Performance",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "chore": "Chores",
    "ci": "CI",
    "build": "Build",
}

_CC_RE = re.compile(
    r"^(?P<type>[a-z]+)(\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$"
)


@dataclass
class ChangelogEntry:
    commit_hash: str
    type: str
    scope: Optional[str]
    breaking: bool
    description: str
    body: str = ""


@dataclass
class ChangelogRelease:
    version: str
    release_date: date
    entries: list[ChangelogEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def sections(self) -> dict[str, list[ChangelogEntry]]:
        """Group entries by section name."""
        result: dict[str, list[ChangelogEntry]] = {}
        for entry in self.entries:
            section = _SECTION_MAP.get(entry.type, "Other")
            result.setdefault(section, []).append(entry)
        return result

    def breaking_changes(self) -> list[ChangelogEntry]:
        return [e for e in self.entries if e.breaking]


# ---------------------------------------------------------------------------
# Git log parsing
# ---------------------------------------------------------------------------


def _parse_commit_message(raw: str) -> tuple[str, str, Optional[str], bool, str]:
    """Return (type, description, scope, breaking, body)."""
    lines = raw.strip().splitlines()
    subject = lines[0] if lines else ""
    body = "\n".join(lines[2:]) if len(lines) > 2 else ""

    m = _CC_RE.match(subject)
    if not m:
        return "chore", subject, None, False, body

    return (
        m.group("type"),
        m.group("desc"),
        m.group("scope"),
        bool(m.group("breaking")),
        body,
    )


def get_commits_between(
    from_ref: str,
    to_ref: str = "HEAD",
    repo: Optional[Path] = None,
) -> list[ChangelogEntry]:
    cwd = repo or Path(".")
    log = run_cmd(
        [
            "git",
            "log",
            f"{from_ref}..{to_ref}",
            "--pretty=format:%H%x00%B%x00---END---",
        ],
        cwd=cwd,
    )

    entries: list[ChangelogEntry] = []
    for block in log.split("---END---"):
        block = block.strip()
        if not block:
            continue
        parts = block.split("\x00", 2)
        if len(parts) < 2:
            continue
        commit_hash, raw_msg = parts[0].strip(), parts[1]
        ctype, desc, scope, breaking, body = _parse_commit_message(raw_msg)
        entries.append(
            ChangelogEntry(
                commit_hash=commit_hash,
                type=ctype,
                scope=scope,
                breaking=breaking,
                description=desc,
                body=body,
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_SECTION_ORDER = [
    "Features",
    "Bug Fixes",
    "Performance",
    "Refactoring",
    "Documentation",
    "Tests",
    "CI",
    "Build",
    "Chores",
    "Other",
]


def render_markdown(
    release: ChangelogRelease,
    include_hashes: bool = True,
) -> str:
    lines: list[str] = [
        f"## [{release.version}] - {release.release_date.isoformat()}",
        "",
    ]

    breaking = release.breaking_changes()
    if breaking:
        lines += ["### BREAKING CHANGES", ""]
        for e in breaking:
            lines.append(f"- {e.description}")
        lines.append("")

    sections = release.sections()
    for section in _SECTION_ORDER:
        entries = sections.get(section, [])
        if not entries:
            continue
        lines += [f"### {section}", ""]
        for e in entries:
            scope_str = f"**{e.scope}**: " if e.scope else ""
            hash_str = f" ([{e.commit_hash[:7]}](../../commit/{e.commit_hash}))" if include_hashes else ""
            lines.append(f"- {scope_str}{e.description}{hash_str}")
        lines.append("")

    return "\n".join(lines)


def write_changelog(
    release: ChangelogRelease,
    output_path: Path,
    prepend: bool = True,
    include_hashes: bool = True,
) -> None:
    content = render_markdown(release, include_hashes=include_hashes)
    if prepend and output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        content = content + "\n" + existing
    output_path.write_text(content, encoding="utf-8")
