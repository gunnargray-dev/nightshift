"""Release notes generator for Awake.

Builds a structured RELEASE_NOTES.md from the git log, grouping commits
by session and conventional-commit type. Supports:
- Automatic version bump suggestions (major / minor / patch)
- Per-session changelogs with date stamps
- Machine-readable JSON export for downstream tooling
- GitHub-flavoured Markdown output

Run at the end of a session or as part of the CI release pipeline.
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
# Types
# ---------------------------------------------------------------------------


@dataclass
class RawCommit:
    """Parsed fields from a single git log entry."""

    sha: str
    date: str         # ISO-8601 UTC
    subject: str
    body: str


@dataclass
class ConventionalCommit:
    """A commit decoded according to the Awake conventional-commit schema."""

    sha: str
    date: str
    commit_type: str   # feat | fix | refactor | test | ci | docs | meta
    scope: Optional[str]
    description: str
    session: Optional[int]
    breaking: bool


@dataclass
class SessionBlock:
    """All commits belonging to one Awake session."""

    session: int
    date: str
    commits: list[ConventionalCommit]

    # Derived
    feats: list[ConventionalCommit] = field(default_factory=list)
    fixes: list[ConventionalCommit] = field(default_factory=list)
    refactors: list[ConventionalCommit] = field(default_factory=list)
    tests: list[ConventionalCommit] = field(default_factory=list)
    meta: list[ConventionalCommit] = field(default_factory=list)
    other: list[ConventionalCommit] = field(default_factory=list)
    has_breaking: bool = False

    def __post_init__(self) -> None:
        for c in self.commits:
            if c.commit_type == "feat":
                self.feats.append(c)
            elif c.commit_type == "fix":
                self.fixes.append(c)
            elif c.commit_type == "refactor":
                self.refactors.append(c)
            elif c.commit_type == "test":
                self.tests.append(c)
            elif c.commit_type in ("meta", "docs", "ci", "chore"):
                self.meta.append(c)
            else:
                self.other.append(c)
            if c.breaking:
                self.has_breaking = True


@dataclass
class ReleaseNotes:
    """Full release notes structure ready for rendering."""

    project: str
    current_version: str
    suggested_bump: str   # major | minor | patch
    new_version: str
    generated_at: str
    sessions: list[SessionBlock]


# ---------------------------------------------------------------------------
# Git log parsing
# ---------------------------------------------------------------------------


SEP = "|||---|||"
_LOG_FORMAT = f"%h{SEP}%aI{SEP}%s{SEP}%b{SEP}---END---"

_CC_PATTERN = re.compile(
    r"^\[awake\]\s+(?P<type>feat|fix|refactor|test|ci|docs|meta|chore)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<desc>.+)$"
)
_SESSION_RE = re.compile(r"session[\s-]*(\d+)", re.IGNORECASE)


def _fetch_git_log(repo_root: Path) -> list[RawCommit]:
    """Return all commits as RawCommit objects."""
    out = subprocess.run(
        ["git", "log", "--pretty=format:" + _LOG_FORMAT],
        capture_output=True, text=True, cwd=repo_root, check=False
    ).stdout
    commits = []
    for block in out.split("---END---"):
        block = block.strip()
        if not block:
            continue
        parts = block.split(SEP)
        if len(parts) < 4:
            continue
        sha, date, subject, body = parts[0], parts[1], parts[2], parts[3]
        commits.append(RawCommit(sha=sha.strip(), date=date.strip(), subject=subject.strip(), body=body.strip()))
    return commits


def _parse_conventional(raw: RawCommit) -> ConventionalCommit:
    """Attempt to decode subject as a conventional commit."""
    m = _CC_PATTERN.match(raw.subject)
    if m:
        return ConventionalCommit(
            sha=raw.sha,
            date=raw.date,
            commit_type=m.group("type"),
            scope=m.group("scope"),
            description=m.group("desc"),
            session=_extract_session(raw.subject),
            breaking=bool(m.group("breaking")),
        )
    return ConventionalCommit(
        sha=raw.sha,
        date=raw.date,
        commit_type="misc",
        scope=None,
        description=raw.subject,
        session=_extract_session(raw.subject),
        breaking=False,
    )


def _extract_session(text: str) -> Optional[int]:
    m = _SESSION_RE.search(text)
    return int(m.group(1)) if m else None


def _group_by_session(commits: list[ConventionalCommit]) -> list[SessionBlock]:
    """Group commits into SessionBlock objects. Commits without a session go into session 0."""
    buckets: dict[int, list[ConventionalCommit]] = {}
    for c in commits:
        key = c.session if c.session is not None else 0
        buckets.setdefault(key, []).append(c)
    blocks = []
    for session_num in sorted(buckets, reverse=True):
        group = buckets[session_num]
        date = group[0].date[:10] if group else "unknown"
        blocks.append(SessionBlock(session=session_num, date=date, commits=group))
    return blocks


# ---------------------------------------------------------------------------
# Version logic
# ---------------------------------------------------------------------------


def _bump_version(current: str, sessions: list[SessionBlock]) -> tuple[str, str]:
    """Return (bump_type, new_version)."""
    breaking = any(s.has_breaking for s in sessions)
    has_feat = any(c for s in sessions for c in s.feats)
    if breaking:
        parts = current.lstrip("v").split(".")
        major = int(parts[0]) + 1
        return "major", f"{major}.0.0"
    if has_feat:
        parts = current.lstrip("v").split(".")
        minor = int(parts[1]) + 1
        return "minor", f"{parts[0]}.{minor}.0"
    parts = current.lstrip("v").split(".")
    patch = int(parts[2]) + 1
    return "patch", f"{parts[0]}.{parts[1]}.{patch}"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_release_notes(repo_root: Path) -> ReleaseNotes:
    """Collect git log and return a fully populated ReleaseNotes object."""
    raw_commits = _fetch_git_log(repo_root)
    conventional = [_parse_conventional(r) for r in raw_commits]
    sessions = _group_by_session(conventional)

    # Current version from latest git tag
    current_version = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True, cwd=repo_root, check=False
    ).stdout.strip() or "0.1.0"

    bump_type, new_version = _bump_version(current_version, sessions)

    return ReleaseNotes(
        project="Awake",
        current_version=current_version,
        suggested_bump=bump_type,
        new_version=new_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        sessions=sessions,
    )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _render_section(title: str, commits: list[ConventionalCommit]) -> str:
    if not commits:
        return ""
    lines = [f"### {title}", ""]
    for c in commits:
        scope = f"**{c.scope}**: " if c.scope else ""
        breaking = " ⚠ BREAKING" if c.breaking else ""
        lines.append(f"- {scope}{c.description}{breaking} (`{c.sha}`)")
    lines.append("")
    return "\n".join(lines)


def render_markdown(notes: ReleaseNotes) -> str:
    """Render ReleaseNotes as GitHub-flavoured Markdown."""
    lines = [
        f"# {notes.project} Release Notes",
        "",
        f"> Generated {notes.generated_at} · "
        f"suggested bump: **{notes.suggested_bump}** → v{notes.new_version}",
        "",
    ]
    for block in notes.sessions:
        if block.session == 0:
            heading = "## Untagged commits"
        else:
            heading = f"## Session {block.session}  ·  {block.date}"
        lines += [heading, ""]
        lines.append(_render_section("Features", block.feats))
        lines.append(_render_section("Bug fixes", block.fixes))
        lines.append(_render_section("Refactors", block.refactors))
        lines.append(_render_section("Tests", block.tests))
        lines.append(_render_section("Meta / docs / CI", block.meta))
        lines.append(_render_section("Other", block.other))
    return "\n".join(lines)


def render_json(notes: ReleaseNotes) -> str:
    """Render ReleaseNotes as a JSON string for downstream tooling."""
    def _cc_dict(c: ConventionalCommit) -> dict:
        return {
            "sha": c.sha, "date": c.date, "type": c.commit_type,
            "scope": c.scope, "description": c.description,
            "session": c.session, "breaking": c.breaking,
        }
    payload = {
        "project": notes.project,
        "current_version": notes.current_version,
        "suggested_bump": notes.suggested_bump,
        "new_version": notes.new_version,
        "generated_at": notes.generated_at,
        "sessions": [
            {
                "session": b.session,
                "date": b.date,
                "has_breaking": b.has_breaking,
                "commits": [_cc_dict(c) for c in b.commits],
            }
            for b in notes.sessions
        ],
    }
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: python -m src.release_notes [--json]"""
    import sys
    repo_root = Path(__file__).resolve().parent.parent
    notes = build_release_notes(repo_root)
    if "--json" in sys.argv:
        print(render_json(notes))
    else:
        output = render_markdown(notes)
        out_path = repo_root / "RELEASE_NOTES.md"
        out_path.write_text(output, encoding="utf-8")
        print(f"Release notes written to {out_path}")
        print(f"Suggested version bump: {notes.suggested_bump} → v{notes.new_version}")


if __name__ == "__main__":
    main()
