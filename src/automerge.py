"""Auto-merge helper for Nightshift.

This module is intentionally lightweight and dependency-free.

It provides a small decision engine that can be used in CI or from the CLI
(to gate whether a PR is eligible for automatic merging).

Nightshift's roadmap calls out **PR auto-merge**: merge PRs automatically if:
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
    This function never raises for ordinary invalid inputs; it returns an
    ineligible decision with a reason.
    """
    if pr_score is None:
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=None,
            min_score=min_score,
            ci_passed=ci_passed,
            reason="Missing pr_score",
        )
    if not isinstance(pr_score, int):
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=None,
            min_score=min_score,
            ci_passed=ci_passed,
            reason="pr_score must be an int",
        )
    if pr_score < 0 or pr_score > 100:
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=pr_score,
            min_score=min_score,
            ci_passed=ci_passed,
            reason="pr_score must be between 0 and 100",
        )
    if not ci_passed:
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=pr_score,
            min_score=min_score,
            ci_passed=False,
            reason="CI checks have not passed",
        )
    if pr_score < min_score:
        return AutoMergeDecision(
            eligible=False,
            pr_number=pr_number,
            pr_score=pr_score,
            min_score=min_score,
            ci_passed=True,
            reason=f"PR score {pr_score} below threshold {min_score}",
        )
    return AutoMergeDecision(
        eligible=True,
        pr_number=pr_number,
        pr_score=pr_score,
        min_score=min_score,
        ci_passed=True,
        reason="Eligible for auto-merge",
    )


def _parse_bool(s: str) -> bool:
    s = s.strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid bool: {s}")


def main(argv=None) -> int:
    """CLI entry point: decide whether to auto-merge.

    Examples
    --------
    python -m src.automerge --score 92 --ci true
    python -m src.automerge --score 79 --ci true --min-score 80
    """
    import argparse

    p = argparse.ArgumentParser(prog="nightshift-automerge")
    p.add_argument("--score", type=int, required=True, help="PR quality score (0-100)")
    p.add_argument("--ci", type=str, required=True, help="Whether CI passed (true/false)")
    p.add_argument("--min-score", type=int, default=80, help="Minimum score threshold")
    p.add_argument("--pr", type=int, default=None, help="PR number")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args(argv)

    try:
        ci_passed = _parse_bool(args.ci)
    except ValueError as e:
        print(str(e))
        return 2

    decision = decide_automerge(
        pr_score=args.score,
        ci_passed=ci_passed,
        min_score=args.min_score,
        pr_number=args.pr,
    )

    if args.json:
        print(json.dumps(decision.to_dict(), indent=2))
    else:
        status = "ELIGIBLE" if decision.eligible else "INELIGIBLE"
        print(f"{status}: {decision.reason}")

    return 0 if decision.eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
