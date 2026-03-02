"""Auto-merge pull requests that pass all checks."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from github import Github, GithubException

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    pr_number: int
    merged: bool
    reason: str


def get_github_client() -> Github:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable not set")
    return Github(token)


def is_mergeable(pr) -> tuple[bool, str]:
    """Check if a PR is safe to auto-merge."""
    if pr.draft:
        return False, "PR is a draft"

    if pr.mergeable_state == "blocked":
        return False, "PR is blocked (failing checks or required reviews missing)"

    if pr.mergeable_state == "behind":
        return False, "PR is behind the base branch"

    if pr.mergeable_state not in ("clean", "unstable"):
        return False, f"PR mergeable state is '{pr.mergeable_state}'"

    labels = [label.name.lower() for label in pr.labels]
    if "do-not-merge" in labels or "wip" in labels:
        return False, "PR has a blocking label"

    return True, "OK"


def auto_merge_pr(
    owner: str,
    repo_name: str,
    pr_number: int,
    merge_method: str = "squash",
) -> MergeResult:
    """Attempt to merge a single PR."""
    g = get_github_client()
    repo = g.get_repo(f"{owner}/{repo_name}")
    pr = repo.get_pull(pr_number)

    ok, reason = is_mergeable(pr)
    if not ok:
        logger.info("PR #%d not mergeable: %s", pr_number, reason)
        return MergeResult(pr_number=pr_number, merged=False, reason=reason)

    try:
        result = pr.merge(
            commit_title=f"{pr.title} (#{pr_number})",
            merge_method=merge_method,
        )
        if result.merged:
            logger.info("Merged PR #%d", pr_number)
            return MergeResult(pr_number=pr_number, merged=True, reason="merged")
        return MergeResult(
            pr_number=pr_number, merged=False, reason=result.message or "unknown"
        )
    except GithubException as exc:
        msg = str(exc)
        logger.warning("Failed to merge PR #%d: %s", pr_number, msg)
        return MergeResult(pr_number=pr_number, merged=False, reason=msg)


def auto_merge_all(
    owner: str,
    repo_name: str,
    label: Optional[str] = "auto-merge",
    merge_method: str = "squash",
) -> list[MergeResult]:
    """Merge all open PRs that carry the given label (default: 'auto-merge')."""
    g = get_github_client()
    repo = g.get_repo(f"{owner}/{repo_name}")

    query = f"is:pr is:open repo:{owner}/{repo_name}"
    if label:
        query += f' label:"{label}"'

    pulls = list(repo.get_pulls(state="open", sort="created"))
    if label:
        pulls = [p for p in pulls if any(lb.name == label for lb in p.labels)]

    results = []
    for pr in pulls:
        results.append(
            auto_merge_pr(
                owner=owner,
                repo_name=repo_name,
                pr_number=pr.number,
                merge_method=merge_method,
            )
        )
    return results
