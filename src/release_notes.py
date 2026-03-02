"""Enhanced changelog generator with --release flag for Awake.

Parses Git history to generate structured release notes in Markdown or
JSON.  Supports:

- Conventional Commits categorisation (feat, fix, docs, ...)
- Version bumping suggestions (major / minor / patch) based on commit types
- ``--release`` flag to tag the current HEAD and write a ``CHANGELOG.md``
  entry
- ``--since`` / ``--until`` date filtering

Public API
----------
- ``CommitEntry``         -- a single parsed commit
- ``ReleaseNotes``        -- structured notes for a version range
- ``parse_commits(repo_path, *, since, until)`` -> list of ``CommitEntry``
- ``build_release_notes(commits, version)`` -> ``ReleaseNotes``
- ``format_markdown(notes)`` -> ``str``

CLI
---
    awake changelog [--since DATE] [--until DATE] [--release VERSION] [--json]
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CommitEntry:
    """A single parsed commit from Git history."""

    sha: str
    type: str       # feat | fix | docs | style | refactor | perf | test | chore | other
    scope: str      # may be empty
    breaking: bool
    summary: str
    body: str
    timestamp: str  # ISO-8601 UTC
    author: str


@dataclass
class ReleaseNotes:
    """Structured release notes for a version range."""

    version: str
    date: str
    features: list[CommitEntry] = field(default_factory=list)
    fixes: list[CommitEntry] = field(default_factory=list)
    breaking_changes: list[CommitEntry] = field(default_factory=list)
    other: list[CommitEntry] = field(default_factory=list)
    bump_suggestion: str = "patch"  # "major" | "minor" | "patch"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert)"
    r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s+(?P<summary>.+)",
    re.IGNORECASE,
)
_SEP = "AWAKE_SEP"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_commits(
    repo_path: str | Path,
    *,
    since: str = "",
    until: str = "",
) -> list[CommitEntry]:
    """Parse commits from *repo_path* git history.

    Parameters
    ----------
    repo_path:
        Path to the git repository.
    since:
        Only include commits after this date.
    until:
        Only include commits before this date.

    Returns
    -------
    list[CommitEntry]
        Parsed commit entries.
    """
    root = Path(repo_path)
    fmt = f"--pretty=format:{_SEP}%H|%ae|%ai|%B"
    args = ["log", fmt]
    if since:
        args += [f"--after={since}"]
    if until:
        args += [f"--before={until}"]

    raw = _run_git(args, cwd=str(root))
    entries: list[CommitEntry] = []

    for block in raw.split(_SEP):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if not lines:
            continue
        header = lines[0]
        parts = header.split("|", 3)
        if len(parts) < 4:
            continue
        sha, author, ts_raw, message = parts
        message = message.strip()
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        try:
            dt = datetime.fromisoformat(ts_raw.strip())
            ts = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            ts = ts_raw.strip()

        m = _CONVENTIONAL_RE.match(message)
        if m:
            commit_type = m.group("type").lower()
            scope = m.group("scope") or ""
            breaking = m.group("breaking") == "!"
            summary = m.group("summary")
        else:
            commit_type = "other"
            scope = ""
            breaking = "BREAKING CHANGE" in body.upper()
            summary = message

        entries.append(
            CommitEntry(
                sha=sha.strip(),
                type=commit_type,
                scope=scope,
                breaking=breaking,
                summary=summary,
                body=body,
                timestamp=ts,
                author=author.strip(),
            )
        )

    return entries


# ---------------------------------------------------------------------------
# Notes builder
# ---------------------------------------------------------------------------


def build_release_notes(commits: list[CommitEntry], version: str = "unreleased") -> ReleaseNotes:
    """Build :class:`ReleaseNotes` from a list of commits.

    Parameters
    ----------
    commits:
        List of parsed commits.
    version:
        Version label for the release.

    Returns
    -------
    ReleaseNotes
        Structured release notes.
    """
    from datetime import date

    notes = ReleaseNotes(
        version=version,
        date=date.today().isoformat(),
    )

    has_breaking = False
    has_feat = False

    for commit in commits:
        if commit.breaking:
            has_breaking = True
            notes.breaking_changes.append(commit)
        if commit.type == "feat":
            has_feat = True
            notes.features.append(commit)
        elif commit.type == "fix":
            notes.fixes.append(commit)
        elif commit.type not in ("feat",):
            notes.other.append(commit)

    if has_breaking:
        notes.bump_suggestion = "major"
    elif has_feat:
        notes.bump_suggestion = "minor"
    else:
        notes.bump_suggestion = "patch"

    return notes


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def format_markdown(notes: ReleaseNotes) -> str:
    """Return *notes* formatted as a Markdown changelog section.

    Parameters
    ----------
    notes:
        Release notes to format.

    Returns
    -------
    str
        Markdown-formatted changelog section.
    """
    lines: list[str] = []
    lines.append(f"## [{notes.version}] - {notes.date}")
    lines.append("")

    if notes.breaking_changes:
        lines.append("### Breaking Changes")
        for c in notes.breaking_changes:
            scope = f"**{c.scope}**: " if c.scope else ""
            lines.append(f"- {scope}{c.summary} (`{c.sha[:8]}`)")
        lines.append("")

    if notes.features:
        lines.append("### Features")
        for c in notes.features:
            scope = f"**{c.scope}**: " if c.scope else ""
            lines.append(f"- {scope}{c.summary} (`{c.sha[:8]}`)")
        lines.append("")

    if notes.fixes:
        lines.append("### Bug Fixes")
        for c in notes.fixes:
            scope = f"**{c.scope}**: " if c.scope else ""
            lines.append(f"- {scope}{c.summary} (`{c.sha[:8]}`)")
        lines.append("")

    if notes.other:
        lines.append("### Other Changes")
        for c in notes.other:
            scope = f"**{c.scope}**: " if c.scope else ""
            lines.append(f"- {scope}{c.summary} (`{c.sha[:8]}`)")
        lines.append("")

    lines.append(f"_Suggested version bump: **{notes.bump_suggestion}**_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the changelog generator.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake changelog",
        description="Generate release notes from git history.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--since", default="", help="Include commits after DATE")
    parser.add_argument("--until", default="", help="Include commits before DATE")
    parser.add_argument(
        "--release",
        default="",
        metavar="VERSION",
        help="Tag the current HEAD with VERSION and update CHANGELOG.md",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    commits = parse_commits(root, since=args.since, until=args.until)
    version = args.release or "unreleased"
    notes = build_release_notes(commits, version=version)

    if args.json:
        data = {
            "version": notes.version,
            "date": notes.date,
            "bump_suggestion": notes.bump_suggestion,
            "features": [{"sha": c.sha, "summary": c.summary} for c in notes.features],
            "fixes": [{"sha": c.sha, "summary": c.summary} for c in notes.fixes],
            "breaking_changes": [{"sha": c.sha, "summary": c.summary} for c in notes.breaking_changes],
            "other": [{"sha": c.sha, "summary": c.summary} for c in notes.other],
        }
        print(json.dumps(data, indent=2))
        return 0

    md = format_markdown(notes)

    if args.release:
        changelog_path = root / "CHANGELOG.md"
        existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
        changelog_path.write_text(md + "\n\n" + existing, encoding="utf-8")
        print(f"CHANGELOG.md updated for {version}")
        # Create git tag
        import subprocess as _sp
        _sp.run(["git", "tag", version], cwd=str(root), check=False)
        print(f"Git tag '{version}' created (if not already present)")
    else:
        print(md)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
