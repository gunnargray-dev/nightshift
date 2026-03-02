"""Auto-merge helper for Awake.

This module is intentionally lightweight and dependency-free.

It provides a small decision engine that can be used in CI or from the CLI
(to gate whether a PR is eligible for automatic merging).

Awake's roadmap calls out **PR auto-merge**: merge PRs automatically if:
- CI passes
- PR score >= threshold (default: 80)

The actual merge action is intentionally not implemented here. This keeps the
core library safe to run locally without requiring GitHub credentials.
Instead, the module outputs a machine-readable decision that can be consumed
by a separate GitHub Action step (future work) or by a human.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AutoMergeDecision:
    """A yes/no decision with structured metadata."""

    eligible: bool
    pr_number: Optional[int] = None
    pr_score: Optional[int] = None
    min_score: int = 80
    ci_passed: Optional[bool] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "eligible": self.eligible,
            "pr_number": self.pr_number,
            "pr_score": self.pr_score,
            "min_score": self.min_score,
            "ci_passed": self.ci_passed,
            "reason": self.reason,
        }


def decide_automerge(*, pr_score: int, ci_passed: bool, min_score: int = 80, pr_number: int | None = None) -> AutoMergeDecision:
    """Return whether a PR is eligible for auto-merge.

    Parameters
    ----------
    pr_score:
        Quality score (0-100) as produced by ``src.pr_scorer``.

    ci_passed:
        Whether required checks passed.

    min_score:
        Minimum quality score required.

    pr_number:
        Optional PR number for better reporting.

    Notes
    -----
    This function never raises for ordinary inputs. Validation errors are
    captured in the returned decision's ``reason`` field.
    """
    if not isinstance(pr_score, int) or not (0 <= pr_score <= 100):
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            reason=f"Invalid pr_score: {pr_score!r}. Must be int in [0, 100].",
        )

    if not ci_passed:
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=pr_score,
            min_score=min_score,
            ci_passed=ci_passed,
            reason="CI checks did not pass.",
        )

    if pr_score < min_score:
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=pr_score,
            min_score=min_score,
            ci_passed=ci_passed,
            reason=f"PR score {pr_score} is below minimum {min_score}.",
        )

    return AutoMergeDecision(
        eligible=True,
        pr_number=pr_number,
        pr_score=pr_score,
        min_score=min_score,
        ci_passed=ci_passed,
        reason="All conditions met.",
    )


def format_decision(decision: AutoMergeDecision) -> str:
    """Return a human-readable summary of the decision."""
    status = "ELIGIBLE" if decision.eligible else "NOT ELIGIBLE"
    lines = [f"Auto-merge decision: {status}"]
    if decision.pr_number is not None:
        lines.append(f"  PR: #{decision.pr_number}")
    if decision.pr_score is not None:
        lines.append(f"  Score: {decision.pr_score}/{decision.min_score} (min)")
    if decision.ci_passed is not None:
        lines.append(f"  CI passed: {decision.ci_passed}")
    lines.append(f"  Reason: {decision.reason}")
    return "\n".join(lines)
