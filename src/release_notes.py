"""Enhanced changelog generator with --release flag for GitHub Releases.

Extends the base changelog module to produce:
- Structured release notes in Markdown
- GitHub Release API payloads (JSON)
- Tag-based version detection

CLI
---
    awake release-notes                    # Preview to stdout
    awake release-notes --write            # Write docs/release_notes.md
    awake release-notes --github           # Produce JSON for GH Releases API
    awake release-notes --tag v1.2.3       # Target a specific tag
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReleaseEntry:
    """A single change entry for a release."""
    kind: str    # "feat" | "fix" | "chore" | "docs" | "refactor" | "test" | "perf" | "other"
    scope: str
    message: str
    sha: str = ""
    pr_number: Optional[int] = None
    breaking: bool = False

    def to_markdown(self, repo_url: str = "") -> str:
        """Render the entry as a Markdown list item."""
        pr_link = ""
        if self.pr_number and repo_url:
            pr_link = f" ([#{self.pr_number}]({repo_url}/pull/{self.pr_number}))"
        sha_link = ""
        if self.sha and repo_url:
            short = self.sha[:7]
            sha_link = f" [`{short}`]({repo_url}/commit/{self.sha})"
        scope_str = f"**{self.scope}**: " if self.scope else ""
        breaking_str = " **BREAKING CHANGE**" if self.breaking else ""
        return f"- {scope_str}{self.message}{breaking_str}{pr_link}{sha_link}"


@dataclass
class ReleaseNotes:
    """Structured release notes for one version."""
    tag: str
    previous_tag: str = ""
    repo_url: str = ""
    features: list[ReleaseEntry] = field(default_factory=list)
    fixes: list[ReleaseEntry] = field(default_factory=list)
    chores: list[ReleaseEntry] = field(default_factory=list)
    breaking_changes: list[ReleaseEntry] = field(default_factory=list)
    other: list[ReleaseEntry] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the release notes as Markdown."""
        lines = [f"## {self.tag}"]
        compare_url = ""
        if self.previous_tag and self.repo_url:
            compare_url = f"{self.repo_url}/compare/{self.previous_tag}...{self.tag}"
            lines.append(f"\n**Full Changelog**: [{self.previous_tag}...{self.tag}]({compare_url})")
        lines.append("")

        if self.breaking_changes:
            lines.append("### Breaking Changes")
            for e in self.breaking_changes:
                lines.append(e.to_markdown(self.repo_url))
            lines.append("")
        if self.features:
            lines.append("### Features")
            for e in self.features:
                lines.append(e.to_markdown(self.repo_url))
            lines.append("")
        if self.fixes:
            lines.append("### Bug Fixes")
            for e in self.fixes:
                lines.append(e.to_markdown(self.repo_url))
            lines.append("")
        if self.chores:
            lines.append("### Maintenance")
            for e in self.chores:
                lines.append(e.to_markdown(self.repo_url))
            lines.append("")
        if self.other:
            lines.append("### Other")
            for e in self.other:
                lines.append(e.to_markdown(self.repo_url))
            lines.append("")

        return "\n".join(lines)

    def to_github_payload(self, draft: bool = False, prerelease: bool = False) -> dict:
        """Build a GitHub Releases API payload dict."""
        return {
            "tag_name": self.tag,
            "name": self.tag,
            "body": self.to_markdown(),
            "draft": draft,
            "prerelease": prerelease,
        }


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout, or empty string on error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _get_latest_tag(repo_path: Path) -> str:
    """Return the most recent git tag, or empty string."""
    return _run_git(["describe", "--tags", "--abbrev=0"], repo_path)


def _get_previous_tag(repo_path: Path, current_tag: str) -> str:
    """Return the tag before *current_tag*, or empty string."""
    tags = _run_git(["tag", "--sort=-version:refname"], repo_path).splitlines()
    try:
        idx = tags.index(current_tag)
        return tags[idx + 1] if idx + 1 < len(tags) else ""
    except ValueError:
        return ""


def _get_commits_since(repo_path: Path, since_tag: str, until_tag: str = "HEAD") -> list[str]:
    """Return a list of ``HASH SUBJECT`` strings between two refs."""
    ref_range = f"{since_tag}..{until_tag}" if since_tag else until_tag
    log = _run_git(["log", ref_range, "--pretty=format:%H %s"], repo_path)
    return [line for line in log.splitlines() if line]


def _get_repo_url(repo_path: Path) -> str:
    """Try to infer the GitHub repo URL from the git remote."""
    remote = _run_git(["remote", "get-url", "origin"], repo_path)
    if not remote:
        return ""
    # Convert SSH to HTTPS
    remote = re.sub(r"git@github\.com:", "https://github.com/", remote)
    remote = re.sub(r"\.git$", "", remote)
    return remote


# ---------------------------------------------------------------------------
# Commit parser
# ---------------------------------------------------------------------------

_COMMIT_RE = re.compile(
    r"^(?P<sha>[0-9a-f]{7,40})\s+"
    r"(?P<type>feat|fix|chore|docs|refactor|test|perf|style|build|ci|revert)?"
    r"(?:\((?P<scope>[^)]+)\))?:?\s*"
    r"(?P<breaking>!)?\s*(?P<msg>.+)$",
    re.IGNORECASE,
)


def _parse_commit(line: str) -> Optional[ReleaseEntry]:
    """Parse a ``HASH SUBJECT`` log line into a ``ReleaseEntry``."""
    m = _COMMIT_RE.match(line)
    if not m:
        # Fallback: treat the whole subject as 'other'
        parts = line.split(" ", 1)
        if len(parts) == 2:
            return ReleaseEntry(kind="other", scope="", message=parts[1], sha=parts[0])
        return None
    kind = (m.group("type") or "other").lower()
    return ReleaseEntry(
        kind=kind,
        scope=m.group("scope") or "",
        message=m.group("msg").strip(),
        sha=m.group("sha"),
        breaking=bool(m.group("breaking")),
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_release_notes(
    repo_path: str | Path,
    tag: Optional[str] = None,
) -> ReleaseNotes:
    """Build ``ReleaseNotes`` from git history.

    Parameters
    ----------
    repo_path:
        Path to the repository root.
    tag:
        Target tag; auto-detected from the latest tag if not provided.

    Returns
    -------
    ReleaseNotes
    """
    repo = Path(repo_path).expanduser().resolve()
    current_tag = tag or _get_latest_tag(repo) or "HEAD"
    previous_tag = _get_previous_tag(repo, current_tag) if current_tag != "HEAD" else ""
    repo_url = _get_repo_url(repo)

    commits = _get_commits_since(repo, previous_tag, current_tag)
    notes = ReleaseNotes(
        tag=current_tag,
        previous_tag=previous_tag,
        repo_url=repo_url,
    )

    for line in commits:
        entry = _parse_commit(line)
        if not entry:
            continue
        if entry.breaking:
            notes.breaking_changes.append(entry)
        kind = entry.kind
        if kind in ("feat",):
            notes.features.append(entry)
        elif kind in ("fix",):
            notes.fixes.append(entry)
        elif kind in ("chore", "build", "ci", "style", "test", "docs"):
            notes.chores.append(entry)
        else:
            notes.other.append(entry)

    return notes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for release notes generation."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-release-notes")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--tag", default=None, help="Target tag (default: latest)")
    p.add_argument("--write", action="store_true", help="Write docs/release_notes.md")
    p.add_argument("--github", action="store_true", help="Output GitHub Releases API payload (JSON)")
    p.add_argument("--draft", action="store_true", help="Mark as draft release")
    p.add_argument("--prerelease", action="store_true", help="Mark as pre-release")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    notes = build_release_notes(repo_path, tag=args.tag)

    if args.github:
        payload = notes.to_github_payload(draft=args.draft, prerelease=args.prerelease)
        print(json.dumps(payload, indent=2))
        return 0

    md = notes.to_markdown()

    if args.write:
        docs = repo_path / "docs"
        docs.mkdir(exist_ok=True)
        out_path = docs / "release_notes.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"  Wrote {out_path}")
        return 0

    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
