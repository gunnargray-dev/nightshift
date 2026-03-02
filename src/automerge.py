from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .utils import run_cmd


@dataclass
class MergeResult:
    success: bool
    branch: str
    message: str
    conflicts: list[str]


def _current_branch(repo: Path) -> str:
    return run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo).strip()


def _has_conflicts(repo: Path) -> list[str]:
    out = run_cmd(["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo)
    return [line for line in out.splitlines() if line.strip()]


def attempt_automerge(
    branch: str,
    base: str = "main",
    repo: Optional[Path] = None,
    strategy: str = "ort",
) -> MergeResult:
    """Try to auto-merge *branch* into *base* without conflicts.

    Returns a :class:`MergeResult` describing the outcome.  The working
    directory is left clean on both success and failure (the merge is
    aborted on conflict).
    """
    cwd = repo or Path(".")

    # Ensure we are on the base branch
    run_cmd(["git", "checkout", base], cwd=cwd)

    try:
        run_cmd(
            ["git", "merge", "--no-ff", f"--strategy={strategy}", branch],
            cwd=cwd,
        )
    except subprocess.CalledProcessError:
        conflicts = _has_conflicts(cwd)
        run_cmd(["git", "merge", "--abort"], cwd=cwd)
        return MergeResult(
            success=False,
            branch=branch,
            message=f"Merge conflict in {len(conflicts)} file(s)",
            conflicts=conflicts,
        )

    return MergeResult(
        success=True,
        branch=branch,
        message=f"Successfully merged {branch!r} into {base!r}",
        conflicts=[],
    )


def rebase_branch(
    branch: str,
    onto: str = "main",
    repo: Optional[Path] = None,
) -> MergeResult:
    """Rebase *branch* onto *onto*."""
    cwd = repo or Path(".")
    run_cmd(["git", "checkout", branch], cwd=cwd)

    try:
        run_cmd(["git", "rebase", onto], cwd=cwd)
    except subprocess.CalledProcessError:
        conflicts = _has_conflicts(cwd)
        run_cmd(["git", "rebase", "--abort"], cwd=cwd)
        return MergeResult(
            success=False,
            branch=branch,
            message=f"Rebase conflict in {len(conflicts)} file(s)",
            conflicts=conflicts,
        )

    return MergeResult(
        success=True,
        branch=branch,
        message=f"Successfully rebased {branch!r} onto {onto!r}",
        conflicts=[],
    )
