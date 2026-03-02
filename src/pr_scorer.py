"""Pull-request quality and risk scorer."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .utils import run_cmd


@dataclass
class ScoringConfig:
    """Configuration for PR scoring."""

    model: str = "gpt-4o-mini"
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "size": 0.20,
            "test_coverage": 0.25,
            "complexity": 0.20,
            "description": 0.15,
            "review_comments": 0.10,
            "ci_status": 0.10,
        }
    )
    max_diff_lines: int = 1000


@dataclass
class PRMetrics:
    """Raw metrics extracted from a pull request."""

    pr_number: int
    title: str
    description: str
    diff_lines_added: int
    diff_lines_removed: int
    files_changed: int
    test_files_changed: int
    has_description: bool
    ci_passed: Optional[bool]
    review_comment_count: int


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------


def _count_diff_lines(diff: str) -> tuple[int, int]:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return added, removed


def _is_test_file(path: str) -> bool:
    return bool(re.search(r"(test_|_test\.py|tests/)", path))


def _extract_metrics_from_git(
    pr_number: int,
    repo: Path,
) -> PRMetrics:
    """Extract PR metrics from local git data (stub for CI/API-less usage)."""
    # In production this would call the GitHub API.
    # Here we simulate by diffing HEAD against the merge-base.
    try:
        base = run_cmd(["git", "merge-base", "HEAD", "origin/main"], cwd=repo).strip()
        diff = run_cmd(["git", "diff", base, "HEAD"], cwd=repo)
        files_raw = run_cmd(["git", "diff", "--name-only", base, "HEAD"], cwd=repo)
    except Exception:
        diff, files_raw = "", ""
        base = ""

    files = [f for f in files_raw.splitlines() if f.strip()]
    added, removed = _count_diff_lines(diff)
    test_files = sum(1 for f in files if _is_test_file(f))

    return PRMetrics(
        pr_number=pr_number,
        title=f"PR #{pr_number}",
        description="",
        diff_lines_added=added,
        diff_lines_removed=removed,
        files_changed=len(files),
        test_files_changed=test_files,
        has_description=False,
        ci_passed=None,
        review_comment_count=0,
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_size(metrics: PRMetrics, config: ScoringConfig) -> float:
    total = metrics.diff_lines_added + metrics.diff_lines_removed
    if total == 0:
        return 1.0
    ratio = min(total / config.max_diff_lines, 1.0)
    return 1.0 - ratio


def _score_test_coverage(metrics: PRMetrics) -> float:
    if metrics.files_changed == 0:
        return 1.0
    return min(metrics.test_files_changed / max(metrics.files_changed - metrics.test_files_changed, 1), 1.0)


def _score_complexity(metrics: PRMetrics, config: ScoringConfig) -> float:
    # Proxy: fewer lines added relative to files changed = simpler
    if metrics.files_changed == 0:
        return 1.0
    avg = metrics.diff_lines_added / metrics.files_changed
    return max(0.0, 1.0 - avg / 200)


def _score_description(metrics: PRMetrics) -> float:
    return 1.0 if metrics.has_description else 0.0


def _score_ci(metrics: PRMetrics) -> float:
    if metrics.ci_passed is None:
        return 0.5
    return 1.0 if metrics.ci_passed else 0.0


def _score_review_comments(metrics: PRMetrics) -> float:
    return max(0.0, 1.0 - metrics.review_comment_count / 10)


def score_pull_request(
    pr_number: int,
    config: Optional[ScoringConfig] = None,
    repo: Optional[Path] = None,
) -> dict[str, Any]:
    """Score a pull request and return a detailed breakdown."""
    cfg = config or ScoringConfig()
    cwd = repo or Path(".")
    metrics = _extract_metrics_from_git(pr_number, cwd)
    w = cfg.weights

    scores = {
        "size": _score_size(metrics, cfg),
        "test_coverage": _score_test_coverage(metrics),
        "complexity": _score_complexity(metrics, cfg),
        "description": _score_description(metrics),
        "ci_status": _score_ci(metrics),
        "review_comments": _score_review_comments(metrics),
    }

    overall = sum(scores[k] * w.get(k, 0.0) for k in scores)

    return {
        "pr_number": pr_number,
        "overall_score": round(overall, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "metrics": {
            "diff_lines_added": metrics.diff_lines_added,
            "diff_lines_removed": metrics.diff_lines_removed,
            "files_changed": metrics.files_changed,
            "test_files_changed": metrics.test_files_changed,
            "has_description": metrics.has_description,
            "ci_passed": metrics.ci_passed,
            "review_comment_count": metrics.review_comment_count,
        },
    }
