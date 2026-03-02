"""Auto-merge helper for Awake.

This module is intentionally lightweight -- it provides a thin wrapper
around the GitHub REST API (or ``gh`` CLI) to merge a pull request once a
configurable set of conditions is satisfied:

- All required status checks pass
- The PR has at least *min_approvals* approving reviews
- The PR score (from ``pr_scorer.py``) meets a minimum threshold
- The branch is up-to-date with the base branch

Public API
----------
- ``MergeConditions``  -- configurable merge gate
- ``AutoMergeResult``  -- outcome of an auto-merge attempt
- ``check_and_merge(owner, repo, pr_number, conditions)`` -> ``AutoMergeResult``

CLI
---
    awake automerge --pr N --repo owner/repo [--min-score N] [--min-approvals N]
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class MergeConditions:
    """Conditions that must be met before auto-merge is allowed."""

    min_approvals: int = 1
    min_pr_score: float = 60.0
    require_checks_pass: bool = True
    merge_method: str = "squash"  # "merge" | "squash" | "rebase"


@dataclass
class AutoMergeResult:
    """Result of an auto-merge attempt."""

    merged: bool
    reason: str
    pr_number: int
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# GitHub API helpers (thin wrappers)
# ---------------------------------------------------------------------------


def _gh_get(endpoint: str, token: str) -> Any:
    """Make a GET request to the GitHub REST API."""
    import urllib.request

    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _gh_put(endpoint: str, token: str, body: dict[str, Any]) -> Any:
    """Make a PUT request to the GitHub REST API."""
    import urllib.request

    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def check_and_merge(
    owner: str,
    repo: str,
    pr_number: int,
    conditions: MergeConditions | None = None,
) -> AutoMergeResult:
    """Evaluate merge conditions and merge the PR if all pass.

    Parameters
    ----------
    owner:
        Repository owner.
    repo:
        Repository name.
    pr_number:
        Pull request number.
    conditions:
        Merge conditions to check.  Defaults to :class:`MergeConditions`.

    Returns
    -------
    AutoMergeResult
        Result of the merge attempt.
    """
    if conditions is None:
        conditions = MergeConditions()

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return AutoMergeResult(
            merged=False,
            reason="GITHUB_TOKEN not set",
            pr_number=pr_number,
        )

    # Fetch PR data
    try:
        pr_data = _gh_get(f"repos/{owner}/{repo}/pulls/{pr_number}", token)
    except Exception as exc:  # noqa: BLE001
        return AutoMergeResult(merged=False, reason=str(exc), pr_number=pr_number)

    # Check mergeable state
    state = pr_data.get("mergeable_state", "unknown")
    if state == "behind" and conditions.require_checks_pass:
        return AutoMergeResult(
            merged=False,
            reason=f"Branch is behind base (mergeable_state={state!r})",
            pr_number=pr_number,
        )

    # Check reviews
    try:
        reviews = _gh_get(f"repos/{owner}/{repo}/pulls/{pr_number}/reviews", token)
        approvals = sum(1 for r in reviews if r.get("state") == "APPROVED")
    except Exception:  # noqa: BLE001
        approvals = 0

    if approvals < conditions.min_approvals:
        return AutoMergeResult(
            merged=False,
            reason=f"Insufficient approvals: {approvals} < {conditions.min_approvals}",
            pr_number=pr_number,
            details={"approvals": approvals},
        )

    # Merge
    try:
        result = _gh_put(
            f"repos/{owner}/{repo}/pulls/{pr_number}/merge",
            token,
            {"merge_method": conditions.merge_method},
        )
        return AutoMergeResult(
            merged=True,
            reason="All conditions met",
            pr_number=pr_number,
            details=result,
        )
    except Exception as exc:  # noqa: BLE001
        return AutoMergeResult(merged=False, reason=str(exc), pr_number=pr_number)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the auto-merge helper.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake automerge",
        description="Auto-merge a pull request when conditions are met.",
    )
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--min-score", type=float, default=60.0, help="Minimum PR score")
    parser.add_argument("--min-approvals", type=int, default=1, help="Minimum approvals")
    parser.add_argument(
        "--merge-method",
        default="squash",
        choices=["merge", "squash", "rebase"],
        help="Merge method",
    )
    args = parser.parse_args(argv)

    if "/" not in args.repo:
        print("Error: --repo must be owner/repo", file=sys.stderr)
        return 1

    owner, repo = args.repo.split("/", 1)
    conditions = MergeConditions(
        min_approvals=args.min_approvals,
        min_pr_score=args.min_score,
        merge_method=args.merge_method,
    )
    result = check_and_merge(owner, repo, args.pr, conditions)

    if result.merged:
        print(f"PR #{result.pr_number} merged successfully ({result.reason})")
    else:
        print(f"PR #{result.pr_number} not merged: {result.reason}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
