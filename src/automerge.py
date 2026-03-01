"""Auto-merge decision engine for Awake.

Determines whether a PR is eligible for auto-merge based on:
  1. CI status (all checks passed)
  2. PR score threshold (default: 80)

Design: pure function, no GitHub side-effects. Safe to call anywhere.
Actual merge execution is deferred to a future GitHub Actions integration.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MergeDecision:
    """Result of an auto-merge eligibility check."""

    pr_number: int
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    score: Optional[float] = None
    ci_passed: Optional[bool] = None

    def to_dict(self) -> dict:
        """Serialise to plain dict for JSON output."""
        return {
            "pr_number": self.pr_number,
            "eligible": self.eligible,
            "score": self.score,
            "ci_passed": self.ci_passed,
            "reasons": self.reasons,
        }


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------


def _load_scores(scores_path: Path) -> dict[int, float]:
    """Load PR scores from the JSON persistence file produced by pr_scorer."""
    if not scores_path.exists():
        return {}
    try:
        raw = json.loads(scores_path.read_text())
        return {int(k): float(v) for k, v in raw.items()}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# CI status helpers
# ---------------------------------------------------------------------------


def _ci_passed(pr_number: int) -> bool:
    """Return True when the local test suite is green.

    In the current implementation we run the test suite locally via pytest
    rather than querying the GitHub Checks API (which would require a token).
    A future version can replace this with a `gh pr checks` call.
    """
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=no", "--no-header"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_eligibility(
    pr_number: int,
    *,
    min_score: float = 80.0,
    scores_path: Path | None = None,
    skip_ci: bool = False,
) -> MergeDecision:
    """Determine whether *pr_number* is eligible for auto-merge.

    Args:
        pr_number: GitHub PR number to evaluate.
        min_score: Minimum PR score required for eligibility (default 80).
        scores_path: Path to the pr_scores JSON file.  Defaults to
            ``pr_scores.json`` in the current working directory.
        skip_ci: If *True*, skip the local pytest run (useful in tests).

    Returns:
        A :class:`MergeDecision` with ``eligible=True`` only when *all*
        gates pass.
    """
    if scores_path is None:
        scores_path = Path("pr_scores.json")

    reasons: list[str] = []
    eligible = True

    # --- Gate 1: PR score ------------------------------------------------
    scores = _load_scores(scores_path)
    score = scores.get(pr_number)
    if score is None:
        reasons.append(f"PR #{pr_number} not found in score file ({scores_path})")
        eligible = False
    elif score < min_score:
        reasons.append(f"PR score {score:.1f} < threshold {min_score:.1f}")
        eligible = False

    # --- Gate 2: CI ------------------------------------------------------
    if skip_ci:
        ci_ok: Optional[bool] = None
    else:
        ci_ok = _ci_passed(pr_number)
        if not ci_ok:
            reasons.append("Local test suite failed")
            eligible = False

    if eligible:
        reasons.append("All gates passed")

    return MergeDecision(
        pr_number=pr_number,
        eligible=eligible,
        reasons=reasons,
        score=score,
        ci_passed=ci_ok,
    )
