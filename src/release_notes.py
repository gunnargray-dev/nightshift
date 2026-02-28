"""Enhanced changelog generator with --release flag for GitHub Releases.

Extends the existing src/changelog.py module to produce polished, GitHub
Releases-compatible release notes in Markdown.

CLI
---
    nightshift changelog --release              # Generate release notes to stdout
    nightshift changelog --release --write      # Write RELEASE_NOTES.md
    nightshift changelog --release --version v0.17.0
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_SECTION_MAP = {
    "feat":     ("Features", 1),
    "fix":      ("Bug Fixes", 2),
    "perf":     ("Performance", 3),
    "refactor": ("Code Quality", 4),
    "test":     ("Tests", 5),
    "docs":     ("Documentation", 6),
    "ci":       ("CI / Build", 7),
    "build":    ("CI / Build", 7),
    "chore":    ("Chores", 8),
    "style":    ("Style", 9),
    "revert":   ("Reverts", 10),
}

_NIGHTSHIFT_PATTERN = re.compile(
    r"(\[nightshift\]|nightshift session \d+|autonomous)", re.IGNORECASE
)


@dataclass
class ReleaseEntry:
    sha: str
    subject: str
    cc_type: str
    scope: str
    description: str
    is_breaking: bool
    is_nightshift: bool
    pr_refs: list[str]
    author: str

    def format_line(self) -> str:
        scope_str = f"**{self.scope}:** " if self.scope else ""
        breaking = " **BREAKING**" if self.is_breaking else ""
        pr_str = " ".join(f"({r})" for r in self.pr_refs)
        ns_badge = " [nightshift]" if self.is_nightshift else ""
        return f"- {scope_str}{self.description}{breaking}{ns_badge} {pr_str}".rstrip()


@dataclass
class ReleaseSection:
    title: str
    order: int
    entries: list[ReleaseEntry] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"### {self.title}", ""]
        for e in sorted(self.entries, key=lambda x: (not x.is_breaking, x.scope)):
            lines.append(e.format_line())
        return "\n".join(lines)


@dataclass
class ReleaseNotes:
    version: str
    date: str
    repo_url: str
    sections: list[ReleaseSection] = field(default_factory=list)
    breaking_changes: list[ReleaseEntry] = field(default_factory=list)
    contributors: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    previous_version: str = ""
    nightshift_session: int = 0

    def to_markdown(self) -> str:
        lines = [f"# Release {self.version}", "", f"> **Released:** {self.date}", ""]
        if self.nightshift_session:
            lines += [f"> **Nightshift Session:** {self.nightshift_session}", "> Built autonomously by Perplexity Computer", ""]
        if self.stats:
            lines += ["## Release Stats", "", "| Metric | Value |", "|--------|-------|"]
            for k, v in self.stats.items():
                lines.append(f"| {k} | **{v}** |")
            lines.append("")
        if self.breaking_changes:
            lines += ["## Breaking Changes", "", "> **These changes may require action before upgrading.**", ""]
            for bc in self.breaking_changes:
                lines.append(f"- {bc.description}")
            lines.append("")
        for sec in sorted(self.sections, key=lambda s: s.order):
            if sec.entries:
                lines += [sec.to_markdown(), ""]
        if self.previous_version and self.repo_url:
            compare_url = f"{self.repo_url}/compare/{self.previous_version}...{self.version}"
            lines += ["## Full Changelog", "", f"**{self.previous_version} -> {self.version}:** {compare_url}", ""]
        if self.contributors:
            lines += ["## Contributors", ""]
            for c in sorted(set(self.contributors)):
                lines.append(f"- @{c}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "date": self.date,
            "sections": {s.title: [e.format_line() for e in s.entries] for s in self.sections if s.entries},
            "stats": self.stats,
            "previous_version": self.previous_version,
            "nightshift_session": self.nightshift_session,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")


def _git_log_range(repo_root: Path, since_tag: Optional[str] = None, max_count: int = 200) -> list[dict]:
    sep = "\x1e"
    fmt = f"{sep}%H{sep}%s{sep}%b{sep}%an{sep}%ae"
    cmd = ["git", "log", f"--format={fmt}"]
    if since_tag:
        cmd.append(f"{since_tag}..HEAD")
    else:
        cmd += [f"--max-count={max_count}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root), timeout=30)
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    commits = []
    raw = result.stdout.split(sep)[1:]
    it = iter(raw)
    for sha, subject, body, author_name, author_email in zip(it, it, it, it, it):
        commits.append({"sha": sha.strip(), "subject": subject.strip(), "body": body.strip(), "author": author_name.strip(), "email": author_email.strip()})
    return commits


def _latest_tag(repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], capture_output=True, text=True, cwd=str(repo_root), timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _repo_url(repo_root: Path) -> str:
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, cwd=str(repo_root), timeout=10)
        if result.returncode == 0:
            url = result.stdout.strip()
            url = re.sub(r"git@github\.com:(.+?)\.git", r"https://github.com/\1", url)
            return url.rstrip(".git")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "https://github.com/gunnargray-dev/nightshift"


_CC_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|wip)(\([^)]+\))?(!)?:\s+(.+)$",
    re.IGNORECASE,
)
_PR_RE = re.compile(r"#(\d+)")


def _parse_commit(raw: dict) -> Optional[ReleaseEntry]:
    subject = raw["subject"]
    m = _CC_RE.match(subject)
    if not m:
        return None
    cc_type = m.group(1).lower()
    scope = (m.group(2) or "").strip("()")
    is_breaking = bool(m.group(3)) or "BREAKING CHANGE" in raw.get("body", "")
    description = m.group(4)
    pr_refs = [f"#{n}" for n in _PR_RE.findall(subject + " " + raw.get("body", ""))]
    is_ns = bool(_NIGHTSHIFT_PATTERN.search(subject + " " + raw.get("body", "")))
    return ReleaseEntry(sha=raw["sha"], subject=subject, cc_type=cc_type, scope=scope, description=description, is_breaking=is_breaking, is_nightshift=is_ns, pr_refs=pr_refs, author=raw.get("author", ""))


def generate_release_notes(repo_root: Path, version: Optional[str] = None, since_tag: Optional[str] = None) -> ReleaseNotes:
    """Generate polished GitHub-Releases-ready release notes."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    latest_tag = _latest_tag(repo_root)
    prev_version = since_tag or latest_tag or "v0.0.0"
    if version is None:
        pp = repo_root / "pyproject.toml"
        if pp.exists():
            m = re.search(r'version\s*=\s*"([^"]+)"', pp.read_text())
            version = m.group(1) if m else "0.17.0"
        else:
            version = "0.17.0"
    if not version.startswith("v"):
        version = f"v{version}"
    repo_url_val = _repo_url(repo_root)
    log_path = repo_root / "NIGHTSHIFT_LOG.md"
    session_num = 0
    if log_path.exists():
        matches = re.findall(r"## Session (\d+)", log_path.read_text())
        session_num = int(matches[-1]) if matches else 0
    raw_commits = _git_log_range(repo_root, since_tag=since_tag, max_count=300)
    sections_map: dict = {}
    for title, order in _SECTION_MAP.values():
        sections_map[title] = ReleaseSection(title=title, order=order)
    breaking: list = []
    contributors: list = []
    nightshift_count = 0
    for raw in raw_commits:
        entry = _parse_commit(raw)
        if not entry:
            continue
        if entry.is_breaking:
            breaking.append(entry)
        if entry.author and entry.author not in contributors:
            contributors.append(entry.author)
        if entry.is_nightshift:
            nightshift_count += 1
        title, order = _SECTION_MAP.get(entry.cc_type, ("Chores", 8))
        if title not in sections_map:
            sections_map[title] = ReleaseSection(title=title, order=order)
        sections_map[title].entries.append(entry)
    total_commits = len(raw_commits)
    parsed_commits = sum(1 for s in sections_map.values() for _ in s.entries)
    stats = {"Commits in release": total_commits, "Conventional Commits": parsed_commits, "Breaking changes": len(breaking), "Nightshift contributions": nightshift_count, "Contributors": len(set(contributors))}
    return ReleaseNotes(version=version, date=now, repo_url=repo_url_val, sections=list(sections_map.values()), breaking_changes=breaking, contributors=contributors, stats=stats, previous_version=prev_version, nightshift_session=session_num)
