"""PR quality scorer for Nightshift.

Analyzes pull requests (from GitHub API data or local PR description files)
and scores them across five dimensions:

1. Description quality  -- Has What/Why/How sections? Word count reasonable?
2. Test coverage signal -- Test results block present? Test count mentioned?
3. Code clarity signal  -- Commit message follows convention? Branch name clean?
4. Diff scope           -- Not too large, not empty. Sweet-spot 50-500 lines.
5. Session metadata     -- Session number present? Follows PR template?

Each dimension is scored 0-20, total score is 0-100.
Scores are stored as JSON and rendered as a Markdown leaderboard.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """Score and rationale for a single scoring dimension."""

    name: str
    score: int           # 0-20
    max_score: int = 20
    rationale: str = ""


@dataclass
class PRScore:
    """Full quality score for a single PR."""

    pr_number: int
    title: str
    branch: str
    session: Optional[int]
    dimensions: list[DimensionScore]
    scored_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total(self) -> int:
        return sum(d.score for d in self.dimensions)

    @property
    def max_total(self) -> int:
        return sum(d.max_score for d in self.dimensions)

    @property
    def grade(self) -> str:
        pct = self.total / self.max_total * 100 if self.max_total else 0
        if pct >= 90:
            return "A+"
        elif pct >= 80:
            return "A"
        elif pct >= 70:
            return "B"
        elif pct >= 60:
            return "C"
        elif pct >= 50:
            return "D"
        else:
            return "F"


@dataclass
class Leaderboard:
    """Sorted collection of PR scores."""

    scores: list[PRScore]

    @property
    def ranked(self) -> list[PRScore]:
        return sorted(self.scores, key=lambda s: s.total, reverse=True)

    @property
    def average(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(s.total for s in self.scores) / len(self.scores), 1)

    @property
    def top(self) -> Optional[PRScore]:
        return self.ranked[0] if self.ranked else None


# ---------------------------------------------------------------------------
# Scoring rubric
# ---------------------------------------------------------------------------


def _score_description_quality(body: str) -> DimensionScore:
    """Score the PR description for structure and completeness (0-20)."""
    score = 0
    notes = []

    # Has ## What section
    if re.search(r"^##\s+What", body, re.MULTILINE | re.IGNORECASE):
        score += 5
        notes.append("Has ## What section (+5)")
    else:
        notes.append("Missing ## What section (-5)")

    # Has ## Why section
    if re.search(r"^##\s+Why", body, re.MULTILINE | re.IGNORECASE):
        score += 5
        notes.append("Has ## Why section (+5)")
    else:
        notes.append("Missing ## Why section (-5)")

    # Has ## How section
    if re.search(r"^##\s+How", body, re.MULTILINE | re.IGNORECASE):
        score += 4
        notes.append("Has ## How section (+4)")

    # Word count: 50-500 words is ideal
    word_count = len(body.split())
    if 50 <= word_count <= 500:
        score += 4
        notes.append(f"Good word count ({word_count} words) (+4)")
    elif word_count < 20:
        notes.append(f"Too brief ({word_count} words) (-0)")
    elif word_count > 800:
        score += 2
        notes.append(f"Verbose but detailed ({word_count} words) (+2)")
    else:
        score += 2
        notes.append(f"Acceptable word count ({word_count} words) (+2)")

    # Has Session: N tag
    if re.search(r"[Ss]ession:\s*\d+", body):
        score += 2
        notes.append("Session tag present (+2)")

    return DimensionScore(
        name="Description Quality",
        score=min(score, 20),
        rationale="; ".join(notes),
    )


def _score_test_coverage_signal(body: str) -> DimensionScore:
    """Score the PR for test evidence in the description (0-20)."""
    score = 0
    notes = []

    # Has ## Test Results section
    if re.search(r"^##\s+Test\s+Results?", body, re.MULTILINE | re.IGNORECASE):
        score += 8
        notes.append("Has ## Test Results section (+8)")
    elif re.search(r"test", body, re.IGNORECASE):
        score += 2
        notes.append("Mentions tests (+2)")
    else:
        notes.append("No test mention (-0)")

    # Has actual test output (code block with "passed" or "failed")
    if re.search(r"```[\s\S]*?\d+ passed[\s\S]*?```", body):
        score += 8
        notes.append("Has pytest output in code block (+8)")
    elif re.search(r"\d+ passed", body):
        score += 4
        notes.append("Mentions passing tests (+4)")

    # Mentions test count or coverage
    if re.search(r"\d+\s+test", body, re.IGNORECASE):
        score += 4
        notes.append("Mentions test count (+4)")

    return DimensionScore(
        name="Test Coverage Signal",
        score=min(score, 20),
        rationale="; ".join(notes),
    )


def _score_code_clarity(title: str, branch: str) -> DimensionScore:
    """Score commit message convention and branch naming (0-20)."""
    score = 0
    notes = []

    # Title follows [nightshift] <type>: <description>
    if re.match(r"\[nightshift\]\s+\w+:", title):
        score += 8
        notes.append("Title follows [nightshift] type: desc format (+8)")
    elif re.match(r"\w+:\s+", title):
        score += 4
        notes.append("Title has type prefix (+4)")
    else:
        notes.append("Title missing conventional format (-0)")

    # Branch follows nightshift/session-N-feature pattern
    if re.match(r"nightshift/session-\d+-[\w-]+", branch):
        score += 8
        notes.append("Branch follows nightshift/session-N-feature pattern (+8)")
    elif re.match(r"nightshift/", branch):
        score += 4
        notes.append("Branch has nightshift/ prefix (+4)")
    elif "/" in branch:
        score += 2
        notes.append("Branch has scope prefix (+2)")

    # Title length: 10-80 chars is good
    if 10 <= len(title) <= 80:
        score += 4
        notes.append(f"Good title length ({len(title)} chars) (+4)")
    elif len(title) < 10:
        notes.append("Title too short (-0)")
    else:
        score += 2
        notes.append("Title a bit long (+2)")

    return DimensionScore(
        name="Code Clarity",
        score=min(score, 20),
        rationale="; ".join(notes),
    )


def _score_diff_scope(lines_added: int, lines_deleted: int) -> DimensionScore:
    """Score based on diff size -- prefer focused changes (0-20)."""
    score = 0
    notes = []
    total = lines_added + lines_deleted

    if total == 0:
        notes.append("Empty diff (-0)")
    elif total <= 50:
        score += 10
        notes.append(f"Focused change ({total} total lines) (+10)")
    elif total <= 200:
        score += 20
        notes.append(f"Ideal scope ({total} total lines) (+20)")
    elif total <= 500:
        score += 16
        notes.append(f"Substantial change ({total} total lines) (+16)")
    elif total <= 1000:
        score += 10
        notes.append(f"Large change ({total} total lines) (+10)")
    else:
        score += 5
        notes.append(f"Very large diff ({total} total lines) -- consider splitting (+5)")

    # Bonus for good add/delete balance
    if lines_added > 0 and lines_deleted > 0:
        ratio = lines_deleted / lines_added
        if 0.1 <= ratio <= 0.9:
            score = min(score + 0, 20)
            notes.append(f"Healthy add/delete ratio ({lines_added}+/{lines_deleted}-)")
    elif lines_deleted == 0 and lines_added > 0:
        notes.append("Pure addition -- no deletions")

    return DimensionScore(
        name="Diff Scope",
        score=min(score, 20),
        rationale="; ".join(notes),
    )


def _score_session_metadata(body: str, title: str, branch: str) -> DimensionScore:
    """Score metadata completeness for session tracking (0-20)."""
    score = 0
    notes = []

    # Session number in body
    session_in_body = bool(re.search(r"[Ss]ession:?\s*\d+", body))
    if session_in_body:
        score += 6
        notes.append("Session number in body (+6)")
    else:
        notes.append("No session number in body (-0)")

    # Session number in branch
    session_in_branch = bool(re.search(r"session-\d+", branch))
    if session_in_branch:
        score += 6
        notes.append("Session number in branch (+6)")

    # [nightshift] tag in title
    if "[nightshift]" in title.lower():
        score += 4
        notes.append("[nightshift] tag in title (+4)")

    # Has a proper body
    body_lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    if len(body_lines) >= 5:
        score += 4
        notes.append(f"Detailed body ({len(body_lines)} non-empty lines) (+4)")
    elif len(body_lines) >= 2:
        score += 2
        notes.append(f"Basic body ({len(body_lines)} non-empty lines) (+2)")

    return DimensionScore(
        name="Session Metadata",
        score=min(score, 20),
        rationale="; ".join(notes),
    )


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------


def score_pr(
    pr_number: int,
    title: str,
    body: str,
    branch: str,
    lines_added: int = 0,
    lines_deleted: int = 0,
    session: Optional[int] = None,
) -> PRScore:
    """Score a single PR across all dimensions and return a PRScore."""
    # Extract session from body/branch if not provided
    if session is None:
        # Check body for "Session: N"
        m = re.search(r"[Ss]ession:?\s*(\d+)", body)
        if m:
            session = int(m.group(1))
        else:
            # Check branch for "session-N" pattern
            bm = re.search(r"session-(\d+)", branch)
            if bm:
                session = int(bm.group(1))

    dimensions = [
        _score_description_quality(body),
        _score_test_coverage_signal(body),
        _score_code_clarity(title, branch),
        _score_diff_scope(lines_added, lines_deleted),
        _score_session_metadata(body, title, branch),
    ]

    return PRScore(
        pr_number=pr_number,
        title=title,
        branch=branch,
        session=session,
        dimensions=dimensions,
    )


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def load_scores(storage_path: Path) -> list[PRScore]:
    """Load stored PR scores from a JSON file."""
    if not storage_path.exists():
        return []
    try:
        raw = json.loads(storage_path.read_text(encoding="utf-8"))
        scores = []
        for item in raw:
            dims = [DimensionScore(**d) for d in item.pop("dimensions", [])]
            scores.append(PRScore(**item, dimensions=dims))
        return scores
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


def save_scores(scores: list[PRScore], storage_path: Path) -> None:
    """Persist PR scores to a JSON file."""
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    data = []
    for s in scores:
        d = asdict(s)
        data.append(d)
    storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def upsert_score(score: PRScore, storage_path: Path) -> list[PRScore]:
    """Add or replace a PR score in storage. Returns updated list."""
    scores = load_scores(storage_path)
    scores = [s for s in scores if s.pr_number != score.pr_number]
    scores.append(score)
    save_scores(scores, storage_path)
    return scores


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_leaderboard(leaderboard: Leaderboard) -> str:
    """Render a Markdown leaderboard table from a Leaderboard."""
    lines = ["# PR Quality Leaderboard\n"]
    lines.append(f"**Average score:** {leaderboard.average}/100\n")

    lines.append("| Rank | PR | Title | Session | Score | Grade |")
    lines.append("|------|----|-------|---------|-------|-------|")

    for rank, pr in enumerate(leaderboard.ranked, start=1):
        session_str = str(pr.session) if pr.session else "--"
        lines.append(
            f"| {rank} | #{pr.pr_number} | {pr.title[:50]} | {session_str} "
            f"| {pr.total}/{pr.max_total} | **{pr.grade}** |"
        )

    lines.append("")

    # Dimension breakdown for top PR
    if leaderboard.top:
        top = leaderboard.top
        lines.append(f"## Top PR: #{top.pr_number} -- {top.title}\n")
        lines.append("| Dimension | Score | Rationale |")
        lines.append("|-----------|-------|-----------|")
        for d in top.dimensions:
            lines.append(f"| {d.name} | {d.score}/{d.max_score} | {d.rationale} |")

    return "\n".join(lines)


def render_pr_report(score: PRScore) -> str:
    """Render a detailed Markdown report for a single PR."""
    lines = [f"## PR #{score.pr_number} Quality Report\n"]
    lines.append(f"**Title:** {score.title}")
    lines.append(f"**Branch:** `{score.branch}`")
    lines.append(f"**Session:** {score.session or 'unknown'}")
    lines.append(f"**Total Score:** {score.total}/{score.max_total} (Grade: **{score.grade}**)\n")

    lines.append("| Dimension | Score | Max | Rationale |")
    lines.append("|-----------|-------|-----|-----------|")
    for d in score.dimensions:
        lines.append(f"| {d.name} | {d.score} | {d.max_score} | {d.rationale} |")

    return "\n".join(lines)
