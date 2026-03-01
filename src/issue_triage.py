"""Issue auto-triage system for Awake.

Reads open GitHub issues (from a JSON export or file), categorizes them by type,
assigns priority scores, and surfaces the highest-priority items for the next
session.  All analysis is pure Python — no external HTTP calls required at
runtime.  The module can be driven by the CLI (``awake triage``) or called
from ``src/brain.py`` for task selection.

Categories
----------
- BUG           — Something is broken or produces wrong output
- FEATURE       — Request for new functionality
- ENHANCEMENT   — Improvement to existing functionality
- QUESTION      — Question about how the system works
- CHORE         — Maintenance/housekeeping task
- UNKNOWN       — Could not classify

Priority
--------
Priority 1-5 (1 = highest).  Computed from:
- human-priority label → +3 points
- bug category → +2 points
- triage:high label → +2 points
- comment count → +1 if ≥ 3 comments
- triage:low label → -2 points
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

CATEGORY_PATTERNS: dict[str, list[str]] = {
    "BUG": [
        r"\bbug\b", r"\bbroken\b", r"\bcrash(es|ed|ing)?\b", r"\berror\b",
        r"\bfail(s|ed|ure)?\b", r"\bexception\b", r"\btraceback\b",
        r"\bregression\b", r"\bnot working\b",
    ],
    "FEATURE": [
        r"\b(add|implement|build|create|new feature)\b", r"\bfeature request\b",
        r"\bwould be (nice|great|useful)\b", r"\bplease add\b", r"\b\[request\]\b",
    ],
    "ENHANCEMENT": [
        r"\bimprove\b", r"\benhance\b", r"\brefactor\b", r"\boptimize\b",
        r"\bperformance\b", r"\bclean(up| up)\b", r"\bbetter\b",
    ],
    "QUESTION": [
        r"\bhow (do|does|can|to)\b", r"\bwhy (does|is|isn'?t)\b", r"\bwhat is\b",
        r"\bquestion\b", r"\bunderstand\b", r"\bconfuse\b", r"\bhelp\b",
    ],
    "CHORE": [
        r"\bdependenc(y|ies)\b", r"\bupgrade\b", r"\bci\b", r"\bdeploy\b",
        r"\bdocument(ation)?\b", r"\bchore\b", r"\bcleanup\b", r"\bmaintain\b",
    ],
}

PRIORITY_LABEL_WEIGHTS = {
    "human-priority": 3,
    "triage:high": 2,
    "bug": 2,
    "enhancement": 1,
    "triage:medium": 0,
    "triage:low": -2,
    "wontfix": -3,
    "duplicate": -3,
}


@dataclass
class TriagedIssue:
    """A single GitHub issue after triage classification."""

    number: int
    title: str
    body: str
    labels: list[str]
    comment_count: int
    created_at: str
    category: str = "UNKNOWN"
    priority: int = 3  # 1 (highest) to 5 (lowest)
    priority_score: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return asdict(self)

    def to_markdown_row(self) -> str:
        """Single table row for the triage report."""
        label_str = ", ".join(f"`{l}`" for l in self.labels) if self.labels else "—"
        p_emoji = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵", 5: "⚪"}.get(self.priority, "⚪")
        return (
            f"| #{self.number} | {self.title[:60]} | {self.category} "
            f"| {p_emoji} P{self.priority} | {label_str} | {self.rationale[:80]} |"
        )


@dataclass
class TriageReport:
    """Full triage report for all open issues."""

    issues: list[TriagedIssue] = field(default_factory=list)
    generated_at: str = ""
    total_open: int = 0

    def __post_init__(self):
        """Set generated_at and total_open if not provided."""
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if not self.total_open:
            self.total_open = len(self.issues)

    def top_n(self, n: int = 5) -> list[TriagedIssue]:
        """Return the top-N highest priority issues (P1 first)."""
        return sorted(self.issues, key=lambda i: (i.priority, -i.priority_score))[:n]

    def by_category(self) -> dict[str, list[TriagedIssue]]:
        """Group issues by category."""
        result: dict[str, list[TriagedIssue]] = {}
        for issue in self.issues:
            result.setdefault(issue.category, []).append(issue)
        return result

    def to_markdown(self) -> str:
        """Render the full triage report as Markdown."""
        lines = [
            "# Issue Triage Report",
            "",
            f"*Generated: {self.generated_at}*  ",
            f"*Open issues: {self.total_open}*",
            "",
        ]

        if not self.issues:
            lines.append("No open issues found. 🎉")
            return "\n".join(lines)

        # Top priority issues
        top = self.top_n(5)
        lines += [
            "## Top Priority Issues",
            "",
            "| # | Title | Category | Priority | Labels | Rationale |",
            "|---|-------|----------|----------|--------|-----------|" ,
        ]
        for issue in top:
            lines.append(issue.to_markdown_row())

        lines += [""]

        # Full table
        lines += [
            "## All Open Issues",
            "",
            "| # | Title | Category | Priority | Labels | Rationale |",
            "|---|-------|----------|----------|--------|-----------|" ,
        ]
        for issue in sorted(self.issues, key=lambda i: (i.priority, -i.priority_score)):
            lines.append(issue.to_markdown_row())

        lines += [""]

        # Category breakdown
        lines += ["## Category Breakdown", ""]
        by_cat = self.by_category()
        for cat, cat_issues in sorted(by_cat.items()):
            lines.append(f"- **{cat}**: {len(cat_issues)} issue(s)")

        lines += ["", "---", "", "*Triage performed by `src/issue_triage.py`.*"]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return {
            "generated_at": self.generated_at,
            "total_open": self.total_open,
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def _classify_category(title: str, body: str, labels: list[str]) -> str:
    """Classify an issue into one of the category buckets."""
    # Label overrides first
    label_map = {
        "bug": "BUG",
        "enhancement": "ENHANCEMENT",
        "feature": "FEATURE",
        "question": "QUESTION",
        "chore": "CHORE",
    }
    for label in labels:
        for key, cat in label_map.items():
            if key in label.lower():
                return cat

    # Text classification
    text = f"{title} {body}".lower()
    scores: dict[str, int] = {}
    for category, patterns in CATEGORY_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text))
        if score > 0:
            scores[category] = score

    if not scores:
        return "UNKNOWN"

    return max(scores, key=lambda c: scores[c])


def _compute_priority(
    category: str,
    labels: list[str],
    comment_count: int,
    has_human_priority: bool,
) -> tuple[int, float, str]:
    """Return (priority_level 1-5, raw_score, rationale_string)."""
    score = 0.0
    reasons: list[str] = []

    # Label weights
    for label in labels:
        w = PRIORITY_LABEL_WEIGHTS.get(label.lower(), 0)
        if w != 0:
            score += w
            reasons.append(f"label:{label}({w:+d})")

    # Category boost
    if category == "BUG":
        score += 2
        reasons.append("category:BUG(+2)")
    elif category == "FEATURE":
        score += 1
        reasons.append("category:FEATURE(+1)")

    # Comment engagement
    if comment_count >= 5:
        score += 2
        reasons.append(f"comments:{comment_count}(+2)")
    elif comment_count >= 3:
        score += 1
        reasons.append(f"comments:{comment_count}(+1)")

    # Map raw score to 1-5 priority levels
    if score >= 5:
        level = 1
    elif score >= 3:
        level = 2
    elif score >= 1:
        level = 3
    elif score >= -1:
        level = 4
    else:
        level = 5

    return level, score, ";".join(reasons) or "default"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def triage_issues(issues_data: list[dict]) -> TriageReport:
    """Triage a list of raw GitHub issue dicts.

    Args:
        issues_data: List of dicts with keys: number, title, body, labels
                     (list of label name strings), comments (int), created_at.

    Returns:
        A fully populated TriageReport.
    """
    triaged: list[TriagedIssue] = []

    for raw in issues_data:
        number = raw.get("number", 0)
        title = raw.get("title", "")
        body = raw.get("body", "") or ""
        # Labels can come as strings or {"name": "..."} dicts
        raw_labels = raw.get("labels", [])
        labels = [
            (l["name"] if isinstance(l, dict) else str(l))
            for l in raw_labels
        ]
        comment_count = raw.get("comments", raw.get("comment_count", 0))
        created_at = raw.get("created_at", "")
        has_human_priority = "human-priority" in labels

        category = _classify_category(title, body, labels)
        priority, score, rationale = _compute_priority(
            category, labels, comment_count, has_human_priority
        )

        triaged.append(
            TriagedIssue(
                number=number,
                title=title,
                body=body[:500],  # truncate for storage
                labels=labels,
                comment_count=comment_count,
                created_at=created_at,
                category=category,
                priority=priority,
                priority_score=score,
                rationale=rationale,
            )
        )

    return TriageReport(issues=triaged, total_open=len(triaged))


def load_issues_from_file(path: Path) -> list[dict]:
    """Load issues from a JSON file (GitHub API export format)."""
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_triage_report(report: TriageReport, output_path: Path) -> None:
    """Write the triage report as Markdown."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown(), encoding="utf-8")


def save_triage_json(report: TriageReport, output_path: Path) -> None:
    """Write the triage report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
