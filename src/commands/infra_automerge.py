"""Auto-merge command for Nightshift CLI.

This is a thin wrapper around :mod:`src.automerge`.

It intentionally does not perform a GitHub merge action; it only reports
whether a PR is eligible.
"""

from __future__ import annotations

import json

from src.automerge import decide_automerge
from src.commands import _repo, _print_header, _print_ok, _print_warn


def cmd_automerge(args) -> int:
    """Determine whether a PR is eligible for auto-merge."""
    _repo(getattr(args, "repo", None))  # validate repo path, even if unused
    _print_header("Auto-merge Gate")

    decision = decide_automerge(
        pr_score=args.score,
        ci_passed=args.ci_passed,
        min_score=args.min_score,
        pr_number=getattr(args, "pr", None),
    )

    if getattr(args, "json", False):
        print(json.dumps(decision.to_dict(), indent=2))
        return 0 if decision.eligible else 1

    if decision.eligible:
        _print_ok(decision.reason)
        return 0
    _print_warn(decision.reason)
    return 1
