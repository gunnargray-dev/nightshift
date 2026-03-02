"""Auto-merge *executor* for Awake.

The existing :mod:`src.automerge` module is deliberately side-effect free: it
implements an eligibility decision engine.

This module is the counterpart that can *apply* the decision by merging a pull
request using GitHub's REST API.

Design goals
------------
- Dependency-free (stdlib only).
- Safe by default: supports ``--dry-run``.
- Suitable for GitHub Actions: uses ``GITHUB_TOKEN`` and repo env vars.

The executor is intentionally small; all policy lives in :func:`src.automerge.decide_automerge`.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from src.automerge import AutoMergeDecision, decide_automerge


@dataclass(frozen=True)
class MergeResult:
    """Result of attempting to merge a PR."""

    merged: bool
    status: str
    message: str
    pr_number: int
    sha: str | None = None
    decision: AutoMergeDecision | None = None

    def to_dict(self) -> dict:
        """Return a dictionary representation of this merge result."""
        return {
            "merged": self.merged,
            "status": self.status,
            "message": self.message,
            "pr_number": self.pr_number,
            "sha": self.sha,
            "decision": self.decision.to_dict() if self.decision else None,
        }


def _github_api_request(*, method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "awake-automerge-exec",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if hasattr(e, "read") else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return int(getattr(e, "code", 0) or 0), parsed


def merge_pull_request(
    *,
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    merge_method: str = "squash",
    commit_title: str | None = None,
    commit_message: str | None = None,
    dry_run: bool = False,
) -> MergeResult:
    """Merge a pull request via GitHub API."""
    if dry_run:
        return MergeResult(
            merged=False,
            status="dry_run",
            message="Dry run: merge not attempted",
            pr_number=pr_number,
        )

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge"
    payload: dict = {"merge_method": merge_method}
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message

    status, data = _github_api_request(method="PUT", url=url, token=token, payload=payload)
    if status == 200:
        return MergeResult(
            merged=bool(data.get("merged")),
            status="merged" if data.get("merged") else "not_merged",
            message=str(data.get("message", "")),
            pr_number=pr_number,
            sha=data.get("sha"),
        )

    message = data.get("message") if isinstance(data, dict) else None
    return MergeResult(
        merged=False,
        status=f"http_{status}",
        message=str(message or data),
        pr_number=pr_number,
    )


def _env_repo() -> tuple[str, str]:
    slug = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if slug and "/" in slug:
        owner, repo = slug.split("/", 1)
        return owner, repo
    owner = os.environ.get("AWAKE_REPO_OWNER", "").strip()
    repo = os.environ.get("AWAKE_REPO_NAME", "").strip()
    return owner, repo


def main(argv=None) -> int:
    """CLI entry point."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-automerge-exec")
    p.add_argument("--pr", type=int, required=True, help="PR number")
    p.add_argument("--score", type=int, required=True, help="PR score (0-100)")
    p.add_argument("--ci-passed", type=str, required=True, help="Whether CI passed (true/false)")
    p.add_argument("--min-score", type=int, default=80, help="Minimum score required")
    p.add_argument("--merge-method", choices=["merge", "squash", "rebase"], default="squash")
    p.add_argument("--commit-title", default=None)
    p.add_argument("--commit-message", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = p.parse_args(argv)

    from src.automerge import _parse_bool

    try:
        ci_passed = _parse_bool(args.ci_passed)
    except ValueError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        else:
            print(str(e))
        return 2

    decision = decide_automerge(pr_score=args.score, ci_passed=ci_passed, min_score=args.min_score, pr_number=args.pr)
    if not decision.eligible:
        res = MergeResult(
            merged=False,
            status="ineligible",
            message=decision.reason,
            pr_number=args.pr,
            decision=decision,
        )
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(f"INELIGIBLE: {decision.reason}")
        return 1

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token and not args.dry_run:
        res = MergeResult(
            merged=False,
            status="missing_token",
            message="GITHUB_TOKEN is required (or use --dry-run)",
            pr_number=args.pr,
            decision=decision,
        )
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print("ERROR: GITHUB_TOKEN is required (or use --dry-run)")
        return 2

    owner, repo = _env_repo()
    if (not owner or not repo) and not args.dry_run:
        res = MergeResult(
            merged=False,
            status="missing_repo",
            message="Missing GITHUB_REPOSITORY (or AWAKE_REPO_OWNER/AWAKE_REPO_NAME)",
            pr_number=args.pr,
            decision=decision,
        )
        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print("ERROR: Missing repo env vars")
        return 2

    merge_res = merge_pull_request(
        owner=owner or "",
        repo=repo or "",
        pr_number=args.pr,
        token=token,
        merge_method=args.merge_method,
        commit_title=args.commit_title,
        commit_message=args.commit_message,
        dry_run=args.dry_run,
    )
    merge_res = MergeResult(
        merged=merge_res.merged,
        status=merge_res.status,
        message=merge_res.message,
        pr_number=merge_res.pr_number,
        sha=merge_res.sha,
        decision=decision,
    )

    if args.json:
        print(json.dumps(merge_res.to_dict(), indent=2))
    else:
        if merge_res.merged:
            print(f"MERGED: PR #{args.pr} ({merge_res.sha})")
        else:
            print(f"NOT MERGED: {merge_res.status}: {merge_res.message}")

    # In dry-run mode we treat the run as successful if the PR was eligible.
    if args.dry_run:
        return 0

    return 0 if merge_res.merged else 1


if __name__ == "__main__":
    raise SystemExit(main())
