"""Semantic versioning automation — Session 16.

``nightshift semver`` analyses commit messages since the last git tag (or all
commits if no tags exist), classifies them by Conventional Commits convention,
determines the appropriate semver bump (major / minor / patch), bumps the
version in ``pyproject.toml``, and emits a ready-to-paste CHANGELOG release
entry.

Conventional Commits mapping
-----------------------------
feat!  / BREAKING CHANGE  → major bump
feat                       → minor bump
fix / refactor / perf / ...→ patch bump
docs / style / test / chore → patch (or no bump if patch_only_commits is False)

This module uses only stdlib — no semver or packaging library required.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Conventional Commits patterns
# ---------------------------------------------------------------------------

_BREAKING_RE = re.compile(r"BREAKING[- ]CHANGE|^.+!:", re.IGNORECASE)
_TYPE_RE = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert)"
    r"(\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<desc>.+)$",
    re.IGNORECASE,
)

BUMP_PRIORITY = {"major": 3, "minor": 2, "patch": 1, "none": 0}
TYPE_BUMP = {
    "feat": "minor",
    "fix": "patch",
    "refactor": "patch",
    "perf": "patch",
    "docs": "patch",
    "style": "patch",
    "test": "patch",
    "chore": "patch",
    "build": "patch",
    "ci": "patch",
    "revert": "patch",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CommitInfo:
    """Represent a single parsed commit with its conventional-commits classification"""

    sha: str
    message: str
    commit_type: str          # "feat" | "fix" | "chore" | "unknown" | …
    scope: Optional[str]
    description: str
    is_breaking: bool
    bump: str                 # "major" | "minor" | "patch" | "none"

    def to_dict(self) -> dict:
        """Return a dictionary representation of the commit info"""
        return asdict(self)


@dataclass
class SemverBump:
    """Hold the result of a semver analysis including bump type, commits, and changelog"""

    current_version: str
    next_version: str
    bump_type: str            # "major" | "minor" | "patch" | "none"
    commits: list[CommitInfo]
    since_ref: str            # tag or SHA we compared from
    changelog_entry: str      # ready-to-paste markdown block

    # grouped views
    @property
    def breaking(self) -> list[CommitInfo]:
        """Return commits classified as breaking changes"""
        return [c for c in self.commits if c.is_breaking]

    @property
    def features(self) -> list[CommitInfo]:
        """Return non-breaking commits of type feat"""
        return [c for c in self.commits if c.commit_type == "feat" and not c.is_breaking]

    @property
    def fixes(self) -> list[CommitInfo]:
        """Return commits of type fix"""
        return [c for c in self.commits if c.commit_type == "fix"]

    @property
    def other(self) -> list[CommitInfo]:
        """Return commits that are neither feat, fix, nor breaking"""
        return [
            c for c in self.commits
            if c.commit_type not in ("feat", "fix") and not c.is_breaking
        ]

    def to_dict(self) -> dict:
        """Return a dictionary representation with grouped commit counts"""
        d = asdict(self)
        d["breaking_count"] = len(self.breaking)
        d["feature_count"] = len(self.features)
        d["fix_count"] = len(self.fixes)
        d["other_count"] = len(self.other)
        return d

    def to_json(self) -> str:
        """Serialize the semver bump result to a JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render the semver analysis as a Markdown report"""
        lines: list[str] = []
        bump_emoji = {"major": "🚨", "minor": "✨", "patch": "🐛", "none": "📝"}.get(self.bump_type, "")
        lines.append(f"# Semantic Version Analysis\n")
        lines.append(f"**Current version:** `{self.current_version}`")
        lines.append(f"**Recommended bump:** {bump_emoji} **{self.bump_type.upper()}**")
        lines.append(f"**Next version:** `{self.next_version}`")
        lines.append(f"**Commits analysed:** {len(self.commits)} (since `{self.since_ref}`)\n")

        if self.breaking:
            lines.append(f"### ⚠️  Breaking Changes ({len(self.breaking)})\n")
            for c in self.breaking:
                lines.append(f"- `{c.sha[:7]}` {c.description}")
            lines.append("")

        if self.features:
            lines.append(f"### ✨ Features ({len(self.features)})\n")
            for c in self.features:
                scope = f"({c.scope}) " if c.scope else ""
                lines.append(f"- `{c.sha[:7]}` {scope}{c.description}")
            lines.append("")

        if self.fixes:
            lines.append(f"### 🐛 Bug Fixes ({len(self.fixes)})\n")
            for c in self.fixes:
                scope = f"({c.scope}) " if c.scope else ""
                lines.append(f"- `{c.sha[:7]}` {scope}{c.description}")
            lines.append("")

        if self.other:
            lines.append(f"### 📦 Other Changes ({len(self.other)})\n")
            for c in self.other:
                lines.append(f"- `{c.sha[:7]}` [{c.commit_type}] {c.description}")
            lines.append("")

        lines.append("---")
        lines.append("## CHANGELOG Entry Preview\n")
        lines.append("```markdown")
        lines.append(self.changelog_entry)
        lines.append("```")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, cwd=str(cwd), timeout=30,
    )
    return result.stdout.strip()


def _get_latest_tag(repo_path: Path) -> Optional[str]:
    """Return the most recent annotated or lightweight tag, or None."""
    tag = _run_git(["describe", "--tags", "--abbrev=0"], repo_path)
    return tag if tag else None


def _get_commits_since(ref: Optional[str], repo_path: Path) -> list[tuple[str, str]]:
    """Return list of (sha, subject) since *ref* (or all commits if None)."""
    if ref:
        log_range = f"{ref}..HEAD"
    else:
        log_range = "HEAD"
    out = _run_git(["log", log_range, "--format=%H|%s"], repo_path)
    if not out:
        return []
    result = []
    for line in out.splitlines():
        if "|" in line:
            sha, subject = line.split("|", 1)
            result.append((sha.strip(), subject.strip()))
    return result


def _parse_version(version: str) -> tuple[int, int, int]:
    """Parse 'X.Y.Z' into a tuple."""
    parts = version.strip().split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except (ValueError, IndexError):
        return (0, 1, 0)


def _bump_version(current: str, bump_type: str) -> str:
    """Apply a bump to a semver string."""
    major, minor, patch = _parse_version(current)
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    if bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return current  # "none" — no bump


def _classify_commit(sha: str, message: str) -> CommitInfo:
    """Parse a commit message and return a CommitInfo."""
    is_breaking = bool(_BREAKING_RE.search(message))
    m = _TYPE_RE.match(message)
    if m:
        ctype = m.group("type").lower()
        scope = m.group("scope")
        desc = m.group("desc")
        breaking_bang = bool(m.group("breaking"))
        is_breaking = is_breaking or breaking_bang
        bump = "major" if is_breaking else TYPE_BUMP.get(ctype, "patch")
    else:
        ctype = "unknown"
        scope = None
        desc = message
        bump = "patch" if not is_breaking else "major"

    return CommitInfo(
        sha=sha,
        message=message,
        commit_type=ctype,
        scope=scope,
        description=desc,
        is_breaking=is_breaking,
        bump=bump,
    )


def _read_current_version(repo_path: Path) -> str:
    """Read version from pyproject.toml."""
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return "0.1.0"
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*["\'](\S+?)["\']', text, re.MULTILINE)
    return m.group(1) if m else "0.1.0"


def _build_changelog_entry(
    version: str,
    commits: list[CommitInfo],
    breaking: list[CommitInfo],
    features: list[CommitInfo],
    fixes: list[CommitInfo],
    other: list[CommitInfo],
) -> str:
    import datetime
    today = datetime.date.today().isoformat()
    lines = [f"## [{version}] — {today}\n"]

    if breaking:
        lines.append("### ⚠ BREAKING CHANGES\n")
        for c in breaking:
            lines.append(f"- {c.description} ({c.sha[:7]})")
        lines.append("")

    if features:
        lines.append("### Features\n")
        for c in features:
            scope = f"**{c.scope}:** " if c.scope else ""
            lines.append(f"- {scope}{c.description} ({c.sha[:7]})")
        lines.append("")

    if fixes:
        lines.append("### Bug Fixes\n")
        for c in fixes:
            scope = f"**{c.scope}:** " if c.scope else ""
            lines.append(f"- {scope}{c.description} ({c.sha[:7]})")
        lines.append("")

    if other:
        lines.append("### Other Changes\n")
        for c in other:
            lines.append(f"- [{c.commit_type}] {c.description} ({c.sha[:7]})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_semver(repo_path: Path) -> SemverBump:
    """Analyse commits and compute the recommended semver bump."""
    latest_tag = _get_latest_tag(repo_path)
    since_ref = latest_tag or "beginning of history"
    raw_commits = _get_commits_since(latest_tag, repo_path)

    parsed = [_classify_commit(sha, msg) for sha, msg in raw_commits]

    # Determine highest bump needed
    highest = "none"
    for c in parsed:
        if BUMP_PRIORITY.get(c.bump, 0) > BUMP_PRIORITY.get(highest, 0):
            highest = c.bump
        if highest == "major":
            break

    current = _read_current_version(repo_path)
    next_ver = _bump_version(current, highest)

    # Group for changelog
    breaking = [c for c in parsed if c.is_breaking]
    features = [c for c in parsed if c.commit_type == "feat" and not c.is_breaking]
    fixes = [c for c in parsed if c.commit_type == "fix"]
    other = [c for c in parsed if c.commit_type not in ("feat", "fix") and not c.is_breaking]

    changelog_entry = _build_changelog_entry(next_ver, parsed, breaking, features, fixes, other)

    return SemverBump(
        current_version=current,
        next_version=next_ver,
        bump_type=highest,
        commits=parsed,
        since_ref=since_ref,
        changelog_entry=changelog_entry,
    )


def apply_version_bump(bump: SemverBump, repo_path: Path) -> bool:
    """Write the new version into pyproject.toml. Returns True if modified."""
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return False
    text = pyproject.read_text(encoding="utf-8")
    old = f'version = "{bump.current_version}"'
    new = f'version = "{bump.next_version}"'
    if old not in text:
        # Try single quotes
        old = f"version = '{bump.current_version}'"
        new = f"version = '{bump.next_version}'"
    if old not in text:
        return False
    pyproject.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def prepend_changelog_entry(bump: SemverBump, repo_path: Path) -> None:
    """Prepend the release entry to CHANGELOG.md (or create it)."""
    changelog = repo_path / "CHANGELOG.md"
    if changelog.exists():
        existing = changelog.read_text(encoding="utf-8")
        changelog.write_text(bump.changelog_entry + "\n---\n\n" + existing, encoding="utf-8")
    else:
        header = "# Changelog\n\nAll notable changes are documented here.\n\n"
        changelog.write_text(header + bump.changelog_entry, encoding="utf-8")
