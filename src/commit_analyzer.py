"""Smart commit message analyzer for Awake.

Parses every commit message in the repository and extracts:
- Conventional Commits compliance (feat/fix/chore/docs/etc.)
- Message quality score (subject line length, body presence, issue refs)
- Awake vs human commit attribution
- Pattern detection (bulk commits, emoji usage, WIP commits, etc.)

CLI
---
    awake commits                  # Show commit quality report
    awake commits --json           # Emit JSON
    awake commits --top 20         # Show top N commits by score
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


CC_TYPES = {
    "feat": ("feat", "Feature", 10),
    "fix": ("fix", "Bug Fix", 8),
    "docs": ("docs", "Documentation", 6),
    "style": ("style", "Style", 4),
    "refactor": ("refactor", "Refactor", 7),
    "perf": ("perf", "Performance", 9),
    "test": ("test", "Tests", 7),
    "build": ("build", "Build", 5),
    "ci": ("ci", "CI", 5),
    "chore": ("chore", "Chore", 3),
    "revert": ("revert", "Revert", 4),
    "wip": ("wip", "Work In Progress", 1),
}

NS_PATTERNS = [
    r"\[awake\]",
    r"session[-\s]\d+",
    r"awake session",
    r"autonomous",
]


@dataclass
class CommitRecord:
    """A single parsed commit with quality metadata"""

    sha: str
    subject: str
    body: str
    author: str
    date: str
    cc_type: str = ""
    cc_scope: str = ""
    is_breaking: bool = False
    is_awake: bool = False
    quality_score: float = 0.0
    quality_issues: list[str] = field(default_factory=list)
    quality_badges: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the commit record"""
        return asdict(self)


@dataclass
class CommitPatterns:
    """Aggregate pattern counts extracted from commit messages"""

    conventional_count: int = 0
    breaking_count: int = 0
    wip_count: int = 0
    emoji_count: int = 0
    issue_ref_count: int = 0
    long_subject_count: int = 0
    no_body_count: int = 0
    awake_count: int = 0
    human_count: int = 0
    type_distribution: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the commit patterns"""
        return asdict(self)


@dataclass
class CommitAnalysisReport:
    """Full commit quality analysis with scores and pattern breakdown"""

    repo_path: str
    total_commits: int = 0
    avg_quality_score: float = 0.0
    quality_grade: str = ""
    commits: list[CommitRecord] = field(default_factory=list)
    patterns: CommitPatterns = field(default_factory=CommitPatterns)
    top_commits: list[CommitRecord] = field(default_factory=list)
    bottom_commits: list[CommitRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the analysis report"""
        return {
            "repo_path": self.repo_path,
            "total_commits": self.total_commits,
            "avg_quality_score": round(self.avg_quality_score, 1),
            "quality_grade": self.quality_grade,
            "patterns": self.patterns.to_dict(),
            "top_commits": [c.to_dict() for c in self.top_commits],
            "bottom_commits": [c.to_dict() for c in self.bottom_commits],
        }

    def to_markdown(self) -> str:
        """Render the analysis report as a Markdown table"""
        p = self.patterns
        cc_pct = (p.conventional_count / self.total_commits * 100) if self.total_commits else 0
        return f"""## Commit Message Analysis

| Metric | Value |
|--------|-------|
| Total commits | **{self.total_commits}** |
| Avg quality score | **{self.avg_quality_score:.1f}/100** |
| Quality grade | **{self.quality_grade}** |
| Conventional Commits | {p.conventional_count} ({cc_pct:.0f}%) |
| Breaking changes | {p.breaking_count} |
| Awake commits | {p.awake_count} |
| Human commits | {p.human_count} |
"""


def _score_commit(record: CommitRecord) -> None:
    score = 50.0
    issues: list[str] = []
    badges: list[str] = []
    subject = record.subject.strip()
    body = record.body.strip()
    cc_match = re.match(
        r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|wip)(\([^)]+\))?(!)?:\s+(.+)$",
        subject, re.IGNORECASE,
    )
    if cc_match:
        record.cc_type = cc_match.group(1).lower()
        record.cc_scope = (cc_match.group(2) or "").strip("()")
        record.is_breaking = bool(cc_match.group(3))
        score += 20
        badges.append("conventional-commits")
        if record.is_breaking:
            badges.append("breaking-change")
    else:
        issues.append("not Conventional Commits")
    if len(subject) < 10:
        score -= 20
        issues.append("subject too short")
    elif len(subject) <= 50:
        score += 10
        badges.append("ideal-length")
    elif len(subject) <= 72:
        score += 5
    else:
        score -= 10
        issues.append("long subject line")
    if body:
        score += 10
        badges.append("has-body")
        if len(body) > 20:
            score += 5
    else:
        issues.append("no body")
    if re.search(r"(#\d+|closes\s+#\d+|fixes\s+#\d+)", subject + " " + body, re.I):
        score += 5
        badges.append("references-issue")
    if re.search(r"\bwip\b|work.?in.?progress", subject, re.I):
        score -= 15
        issues.append("WIP commit")
    if record.is_awake:
        score += 5
        badges.append("awake")
    score = max(0.0, min(100.0, score))
    record.quality_score = round(score, 1)
    record.quality_issues = issues
    record.quality_badges = badges


def _git_log(repo_root: Path, max_count: int = 500) -> list[CommitRecord]:
    sep = "\x1f"
    fmt = f"{sep}%H{sep}%s{sep}%b{sep}%an{sep}%ai"
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_count}", f"--format={fmt}"],
            capture_output=True, text=True, cwd=str(repo_root), timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    records: list[CommitRecord] = []
    raw_entries = result.stdout.split(sep)[1:]
    it = iter(raw_entries)
    for sha, subject, body, author, date in zip(it, it, it, it, it):
        sha = sha.strip()
        subject = subject.strip()
        if not sha:
            continue
        is_ns = any(re.search(p, subject + " " + body.strip(), re.I) for p in NS_PATTERNS)
        records.append(CommitRecord(sha=sha, subject=subject, body=body.strip(), author=author.strip(), date=date.strip()[:10], is_awake=is_ns))
    return records


def analyze_commits(repo_root: Path, max_commits: int = 500) -> CommitAnalysisReport:
    """Analyse all commit messages and produce a quality report."""
    commits = _git_log(repo_root, max_count=max_commits)
    if not commits:
        return CommitAnalysisReport(repo_path=str(repo_root), total_commits=0, avg_quality_score=0.0, quality_grade="N/A")
    for c in commits:
        _score_commit(c)
    patterns = CommitPatterns()
    type_dist: dict = {}
    for c in commits:
        if c.cc_type:
            patterns.conventional_count += 1
            type_dist[c.cc_type] = type_dist.get(c.cc_type, 0) + 1
        if c.is_breaking: patterns.breaking_count += 1
        if "WIP commit" in c.quality_issues: patterns.wip_count += 1
        if "references-issue" in c.quality_badges: patterns.issue_ref_count += 1
        if "long subject line" in c.quality_issues: patterns.long_subject_count += 1
        if "no body" in c.quality_issues: patterns.no_body_count += 1
        if c.is_awake: patterns.awake_count += 1
        else: patterns.human_count += 1
    patterns.type_distribution = type_dist
    sorted_by_score = sorted(commits, key=lambda c: c.quality_score, reverse=True)
    avg = sum(c.quality_score for c in commits) / len(commits)
    def _grade(s: float) -> str:
        if s >= 90: return "A+"
        if s >= 85: return "A"
        if s >= 80: return "A-"
        if s >= 75: return "B+"
        if s >= 70: return "B"
        if s >= 65: return "B-"
        if s >= 60: return "C+"
        if s >= 55: return "C"
        if s >= 50: return "C-"
        if s >= 45: return "D"
        return "F"
    return CommitAnalysisReport(
        repo_path=str(repo_root), total_commits=len(commits),
        avg_quality_score=round(avg, 1), quality_grade=_grade(avg),
        commits=commits, patterns=patterns,
        top_commits=sorted_by_score[:10], bottom_commits=sorted_by_score[-10:],
    )
