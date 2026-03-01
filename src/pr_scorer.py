"""PR quality scorer for Awake.

Scores every open (or recently closed) pull request on a set of weighted
criteria and produces a ranked list with pass/fail badges.

Scoring dimensions
------------------
- Title quality     : length, conventional-commit prefix, issue reference
- Description       : has body, length, checklist, screenshots/links
- Size              : lines changed (penalise giant PRs)
- CI status         : all checks passed vs failing/pending
- Review activity   : number of approvals, change requests
- Labels            : labelled vs unlabelled
- Staleness         : days since last update

CLI
---
    awake score-prs                # Score all open PRs
    awake score-prs --json         # Emit JSON
    awake score-prs --top 10       # Show top-10
    awake score-prs --pr 42        # Score a specific PR
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PRRecord:
    """A single pull request with metadata and computed score."""

    number: int
    title: str
    body: str
    author: str
    state: str           # open / closed / merged
    draft: bool
    lines_added: int
    lines_deleted: int
    ci_status: str       # success / failure / pending / none
    approvals: int
    changes_requested: int
    labels: list[str]
    created_at: str
    updated_at: str
    score: float = 0.0
    grade: str = ""
    badges: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def lines_changed(self) -> int:
        """Return the total number of lines changed (added + deleted)."""
        return self.lines_added + self.lines_deleted

    def to_dict(self) -> dict:
        """Return a dictionary representation of the PR record."""
        return asdict(self)


@dataclass
class PRScoreReport:
    """Aggregate report: ranked PRs with summary statistics."""

    repo_path: str
    total_prs: int = 0
    avg_score: float = 0.0
    grade: str = ""
    prs: list[PRRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the PR score report."""
        return {
            "repo_path": self.repo_path,
            "total_prs": self.total_prs,
            "avg_score": round(self.avg_score, 1),
            "grade": self.grade,
            "prs": [p.to_dict() for p in self.prs],
        }

    def to_markdown(self) -> str:
        """Render the report as a Markdown table."""
        lines = [
            "## PR Quality Scores",
            "",
            f"| Metric | Value |",
            f"|--------|-------|]",
            f"| Total PRs | {self.total_prs} |",
            f"| Avg score | {self.avg_score:.1f} |",
            f"| Grade | {self.grade} |",
            "",
            "| PR | Title | Score | Grade | CI | Approvals |",
            "|-----|-------|-------|-------|----|-----------|]",
        ]
        for p in self.prs:
            title = p.title[:50] + "..." if len(p.title) > 50 else p.title
            lines.append(
                f"| #{p.number} | {title} | {p.score:.1f} "
                f"| {p.grade} | {p.ci_status} | {p.approvals} |"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------


def _score_title(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score the PR title and return (points, issues, badges)."""
    points = 0.0
    issues: list[str] = []
    badges: list[str] = []
    title = pr.title.strip()

    if len(title) < 10:
        issues.append("title too short")
    elif len(title) <= 72:
        points += 10
        badges.append("good-title-length")
    else:
        issues.append("title too long")
        points += 3

    cc = re.match(
        r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?(!)?:\s+",
        title, re.IGNORECASE,
    )
    if cc:
        points += 15
        badges.append("conventional-commit")
    else:
        issues.append("no conventional-commit prefix")

    if re.search(r"(#\d+|closes\s+#\d+|fixes\s+#\d+)", title, re.I):
        points += 5
        badges.append("has-issue-ref")

    return points, issues, badges


def _score_description(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score the PR description and return (points, issues, badges)."""
    points = 0.0
    issues: list[str] = []
    badges: list[str] = []
    body = pr.body.strip()

    if not body:
        issues.append("no description")
        return points, issues, badges

    points += 10
    badges.append("has-description")

    if len(body) >= 100:
        points += 5
        badges.append("detailed-description")

    if re.search(r"^\s*-\s*\[[ xX]\]", body, re.MULTILINE):
        points += 5
        badges.append("has-checklist")

    if re.search(r"(https?://|!\.jpg|!\.png|!\.gif|screenshot)", body, re.I):
        points += 3
        badges.append("has-media")

    if re.search(r"(#\d+|closes\s+#\d+|fixes\s+#\d+)", body, re.I):
        points += 3
        badges.append("references-issue")

    return points, issues, badges


def _score_size(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score the PR size and return (points, issues, badges)."""
    lc = pr.lines_changed
    if lc <= 50:
        return 15.0, [], ["tiny-pr"]
    if lc <= 200:
        return 10.0, [], ["small-pr"]
    if lc <= 500:
        return 5.0, [], ["medium-pr"]
    if lc <= 1000:
        return 2.0, ["large PR"], ["large-pr"]
    return 0.0, ["very large PR"], ["huge-pr"]


def _score_ci(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score the CI status and return (points, issues, badges)."""
    if pr.ci_status == "success":
        return 20.0, [], ["ci-green"]
    if pr.ci_status == "pending":
        return 5.0, ["CI pending"], ["ci-pending"]
    if pr.ci_status == "failure":
        return 0.0, ["CI failing"], ["ci-red"]
    return 5.0, ["no CI"], ["no-ci"]


def _score_reviews(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score review activity and return (points, issues, badges)."""
    points = 0.0
    issues: list[str] = []
    badges: list[str] = []
    if pr.approvals >= 2:
        points += 15
        badges.append("2-approvals")
    elif pr.approvals == 1:
        points += 8
        badges.append("1-approval")
    else:
        issues.append("no approvals")
    if pr.changes_requested:
        points -= 5
        issues.append(f"{pr.changes_requested} changes requested")
    return points, issues, badges


def _score_labels(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score label usage and return (points, issues, badges)."""
    if pr.labels:
        return 5.0, [], ["labelled"]
    return 0.0, ["no labels"], []


def _score_staleness(pr: PRRecord) -> tuple[float, list[str], list[str]]:
    """Score staleness based on days since last update and return (points, issues, badges)."""
    try:
        updated = datetime.fromisoformat(pr.updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = (now - updated).days
    except Exception:
        return 5.0, [], []

    if days <= 1:
        return 10.0, [], ["fresh"]
    if days <= 7:
        return 7.0, [], ["recent"]
    if days <= 30:
        return 3.0, [], []
    return 0.0, [f"stale ({days}d)"], ["stale"]


def score_pr(pr: PRRecord) -> PRRecord:
    """Compute and attach quality score + grade to a PRRecord."""
    total = 0.0
    all_issues: list[str] = []
    all_badges: list[str] = []

    for fn in (
        _score_title,
        _score_description,
        _score_size,
        _score_ci,
        _score_reviews,
        _score_labels,
        _score_staleness,
    ):
        pts, iss, bdg = fn(pr)
        total += pts
        all_issues.extend(iss)
        all_badges.extend(bdg)

    if pr.draft:
        total *= 0.5
        all_issues.append("draft PR")

    pr.score = round(min(100.0, max(0.0, total)), 1)
    pr.grade = _letter_grade(pr.score)
    pr.badges = all_badges
    pr.issues = all_issues
    return pr


def _letter_grade(score: float) -> str:
    """Map a numeric score to a letter grade."""
    if score >= 90: return "A+"
    if score >= 85: return "A"
    if score >= 80: return "A-"
    if score >= 75: return "B+"
    if score >= 70: return "B"
    if score >= 65: return "B-"
    if score >= 60: return "C+"
    if score >= 55: return "C"
    if score >= 50: return "C-"
    if score >= 45: return "D"
    return "F"


# ---------------------------------------------------------------------------
# GitHub PR reader
# ---------------------------------------------------------------------------


def _load_prs_from_file(repo_root: Path) -> list[PRRecord]:
    """Load PR records from a JSON cache file (awake_prs.json), if present."""
    cache = repo_root / "awake_prs.json"
    if not cache.exists():
        return []
    try:
        raw = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return []
    records = []
    for item in raw:
        try:
            records.append(
                PRRecord(
                    number=item["number"],
                    title=item.get("title", ""),
                    body=item.get("body", "") or "",
                    author=item.get("author", ""),
                    state=item.get("state", "open"),
                    draft=item.get("draft", False),
                    lines_added=item.get("lines_added", 0),
                    lines_deleted=item.get("lines_deleted", 0),
                    ci_status=item.get("ci_status", "none"),
                    approvals=item.get("approvals", 0),
                    changes_requested=item.get("changes_requested", 0),
                    labels=item.get("labels", []),
                    created_at=item.get("created_at", ""),
                    updated_at=item.get("updated_at", ""),
                )
            )
        except (KeyError, TypeError):
            continue
    return records


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def score_all_prs(repo_root: Path) -> PRScoreReport:
    """Score all PRs found in the repository."""
    prs = _load_prs_from_file(repo_root)

    if not prs:
        # Return empty report
        return PRScoreReport(
            repo_path=str(repo_root),
            total_prs=0,
            avg_score=0.0,
            grade="N/A",
        )

    scored = [score_pr(p) for p in prs]
    scored.sort(key=lambda p: p.score, reverse=True)

    avg = sum(p.score for p in scored) / len(scored)
    return PRScoreReport(
        repo_path=str(repo_root),
        total_prs=len(scored),
        avg_score=round(avg, 1),
        grade=_letter_grade(avg),
        prs=scored,
    )
