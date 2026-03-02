"""PR quality scorer for Awake.

Analyzes pull requests (via the GitHub REST API or local git diff) and
produces a quality score (0-100) plus structured feedback.  The scoring
rubric rewards:

- Small, focused diffs (fewer files and lines changed)
- Presence of tests alongside production changes
- A descriptive PR title and body
- Conventional commit messages in the branch
- Linked issues / keywords ("Fixes #N", "Closes #N")

The scorer can operate in two modes:

``--local``
    Compare the current branch against ``main`` using ``git diff``.

``--pr N``
    Fetch PR metadata from the GitHub API (requires ``GITHUB_TOKEN``).

Public API
----------
- ``PRInfo``          -- raw PR metadata
- ``PRScore``         -- scoring result
- ``score_pr(pr_info)`` -> ``PRScore``
- ``fetch_pr_info(owner, repo, pr_number)`` -> ``PRInfo``
- ``score_local_diff(repo_path)`` -> ``PRScore``

CLI
---
    awake pr-score [--local] [--pr N] [--repo owner/repo]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PRInfo:
    """Raw metadata for a pull request."""

    title: str
    body: str
    files_changed: int
    lines_added: int
    lines_deleted: int
    commits: list[str] = field(default_factory=list)  # commit messages
    has_tests: bool = False
    linked_issues: list[int] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


@dataclass
class PRScore:
    """Scoring result for a pull request."""

    score: float  # 0-100
    grade: str    # A / B / C / D / F
    feedback: list[str] = field(default_factory=list)
    breakdown: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert)(\(.+\))?!?: .+",
    re.IGNORECASE,
)
_LINK_RE = re.compile(r"(fixes|closes|resolves)\s+#(\d+)", re.IGNORECASE)


def score_pr(pr: PRInfo) -> PRScore:
    """Compute a quality score for *pr* and return a :class:`PRScore`.

    Parameters
    ----------
    pr:
        Pull request metadata to score.

    Returns
    -------
    PRScore
        The computed score, grade, and feedback.
    """
    breakdown: dict[str, float] = {}
    feedback: list[str] = []

    # --- Diff size (30 pts) ---
    total_lines = pr.lines_added + pr.lines_deleted
    if total_lines <= 50:
        diff_score = 30.0
    elif total_lines <= 200:
        diff_score = 25.0
    elif total_lines <= 500:
        diff_score = 15.0
    elif total_lines <= 1000:
        diff_score = 8.0
    else:
        diff_score = 0.0
        feedback.append("PR is very large (>1000 changed lines). Consider splitting it.")
    if pr.files_changed > 20:
        diff_score = max(0.0, diff_score - 5.0)
        feedback.append(f"PR touches {pr.files_changed} files. Focused PRs are easier to review.")
    breakdown["diff_size"] = diff_score

    # --- Tests (20 pts) ---
    if pr.has_tests:
        test_score = 20.0
    else:
        test_score = 0.0
        feedback.append("No test files detected in the diff.")
    breakdown["tests"] = test_score

    # --- PR description (20 pts) ---
    title_ok = len(pr.title.strip()) >= 10
    body_ok = len(pr.body.strip()) >= 30
    desc_score = (10.0 if title_ok else 0.0) + (10.0 if body_ok else 0.0)
    if not title_ok:
        feedback.append("PR title is too short (< 10 chars).")
    if not body_ok:
        feedback.append("PR description is too short. Add context and motivation.")
    breakdown["description"] = desc_score

    # --- Commit messages (20 pts) ---
    if not pr.commits:
        commit_score = 10.0  # can't penalise what we can't see
    else:
        conventional = sum(1 for c in pr.commits if _CONVENTIONAL_RE.match(c))
        ratio = conventional / len(pr.commits)
        commit_score = round(ratio * 20.0, 1)
        if ratio < 0.5:
            feedback.append("Less than half of commit messages follow Conventional Commits.")
    breakdown["commit_messages"] = commit_score

    # --- Linked issues (10 pts) ---
    if pr.linked_issues:
        link_score = 10.0
    elif _LINK_RE.search(pr.body):
        link_score = 10.0
    else:
        link_score = 0.0
        feedback.append("No linked issues found. Use 'Fixes #N' or 'Closes #N'.")
    breakdown["linked_issues"] = link_score

    total = sum(breakdown.values())
    grade = "A" if total >= 90 else "B" if total >= 75 else "C" if total >= 60 else "D" if total >= 45 else "F"

    return PRScore(score=total, grade=grade, feedback=feedback, breakdown=breakdown)


# ---------------------------------------------------------------------------
# GitHub API fetcher
# ---------------------------------------------------------------------------


def _gh_api(endpoint: str, token: str) -> Any:
    """Make a simple GitHub REST API GET request and return parsed JSON."""
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


def fetch_pr_info(owner: str, repo: str, pr_number: int) -> PRInfo:
    """Fetch PR metadata from the GitHub REST API.

    Parameters
    ----------
    owner:
        Repository owner.
    repo:
        Repository name.
    pr_number:
        Pull request number.

    Returns
    -------
    PRInfo
        Metadata for the specified pull request.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN environment variable not set")

    pr_data = _gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}", token)
    files_data = _gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/files", token)
    commits_data = _gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/commits", token)

    files_changed = len(files_data)
    lines_added = sum(f.get("additions", 0) for f in files_data)
    lines_deleted = sum(f.get("deletions", 0) for f in files_data)
    has_tests = any(
        "test" in f.get("filename", "").lower() for f in files_data
    )
    commits = [c["commit"]["message"].splitlines()[0] for c in commits_data]

    body = pr_data.get("body") or ""
    linked = [int(m.group(2)) for m in _LINK_RE.finditer(body)]

    return PRInfo(
        title=pr_data.get("title", ""),
        body=body,
        files_changed=files_changed,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        commits=commits,
        has_tests=has_tests,
        linked_issues=linked,
        labels=[lbl["name"] for lbl in pr_data.get("labels", [])],
    )


# ---------------------------------------------------------------------------
# Local diff scorer
# ---------------------------------------------------------------------------


def score_local_diff(repo_path: str | Path = ".") -> PRScore:
    """Score the diff between HEAD and ``origin/main``.

    Parameters
    ----------
    repo_path:
        Path to the git repository.

    Returns
    -------
    PRScore
        Score for the current branch diff.
    """
    root = Path(repo_path)

    def _git(*args: str) -> str:
        try:
            return subprocess.check_output(
                ["git"] + list(args), cwd=str(root), text=True, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            return ""

    # Diff stat
    stat = _git("diff", "--shortstat", "origin/main...HEAD")
    files_changed = 0
    lines_added = 0
    lines_deleted = 0
    m = re.search(r"(\d+) file", stat)
    if m:
        files_changed = int(m.group(1))
    m = re.search(r"(\d+) insertion", stat)
    if m:
        lines_added = int(m.group(1))
    m = re.search(r"(\d+) deletion", stat)
    if m:
        lines_deleted = int(m.group(1))

    # Changed files
    changed_files = _git("diff", "--name-only", "origin/main...HEAD").splitlines()
    has_tests = any("test" in f.lower() for f in changed_files)

    # Commit messages
    log = _git("log", "--format=%s", "origin/main...HEAD")
    commits = [l.strip() for l in log.splitlines() if l.strip()]

    pr = PRInfo(
        title="(local diff)",
        body="",
        files_changed=files_changed,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        commits=commits,
        has_tests=has_tests,
    )
    return score_pr(pr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the PR scorer.

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
        prog="awake pr-score",
        description="Score a pull request or local branch diff.",
    )
    parser.add_argument("--local", action="store_true", help="Score local diff vs origin/main")
    parser.add_argument("--pr", type=int, default=0, help="PR number to fetch from GitHub")
    parser.add_argument("--repo", default="", help="owner/repo for GitHub API (e.g. acme/myrepo)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    if args.local:
        result = score_local_diff()
    elif args.pr:
        if "/" not in args.repo:
            print("Error: --repo must be in 'owner/repo' format", file=sys.stderr)
            return 1
        owner, repo = args.repo.split("/", 1)
        pr_info = fetch_pr_info(owner, repo, args.pr)
        result = score_pr(pr_info)
    else:
        print("Specify --local or --pr N", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "score": result.score,
                    "grade": result.grade,
                    "feedback": result.feedback,
                    "breakdown": result.breakdown,
                },
                indent=2,
            )
        )
    else:
        print(f"Score: {result.score:.1f}/100  Grade: {result.grade}")
        for item in result.breakdown.items():
            print(f"  {item[0]:<20} {item[1]:.1f}")
        if result.feedback:
            print("\nFeedback:")
            for msg in result.feedback:
                print(f"  - {msg}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
