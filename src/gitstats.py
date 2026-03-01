"""Git statistics deep-dive for Awake.

Provides a detailed breakdown of commit frequency, code churn, contributor
activity, and branch health. Designed to surface patterns invisible in
standard `git log` output.

CLI: awake gitstats [--json] [--days N] [--author AUTHOR]
API: GET /api/gitstats
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CommitRecord:
    """Normalised representation of a single commit."""

    sha: str
    author: str
    email: str
    timestamp: str          # ISO-8601
    subject: str
    insertions: int
    deletions: int
    files_changed: int


@dataclass
class AuthorStats:
    """Per-author aggregate statistics."""

    author: str
    email: str
    commits: int
    insertions: int
    deletions: int
    files_changed: int
    first_commit: str
    last_commit: str
    active_days: int


@dataclass
class ChurnRecord:
    """High-churn file record."""

    path: str
    changes: int        # number of commits touching this file
    insertions: int
    deletions: int


@dataclass
class GitStatsReport:
    """Full git-statistics report."""

    period_days: int
    total_commits: int
    total_insertions: int
    total_deletions: int
    active_authors: int
    commits_per_day: float
    busiest_day: str
    busiest_day_count: int
    author_stats: List[AuthorStats]
    top_churn_files: List[ChurnRecord]
    recent_commits: List[CommitRecord]
    branch_count: int
    stale_branches: List[str]   # branches with no commits in >30 days
    summary: str


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Optional[Path] = None) -> str:
    """Run a git command and return stdout, or empty string on error."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _repo_root() -> Path:
    """Return the repository root (or cwd)."""
    root = _run(["git", "rev-parse", "--show-toplevel"])
    return Path(root) if root else Path.cwd()


def _since_date(days: int) -> str:
    """Return an ISO date string N days in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Commit parsing
# ---------------------------------------------------------------------------

_SEP = "\x00"  # NUL separator — safe delimiter for log format


def _parse_commits(days: int, author: Optional[str] = None) -> list[CommitRecord]:
    """Parse commits in the given period into CommitRecord objects."""
    since = _since_date(days)
    fmt = f"%H{_SEP}%an{_SEP}%ae{_SEP}%aI{_SEP}%s"
    cmd = ["git", "log", f"--since={since}", f"--format={fmt}", "--numstat"]
    if author:
        cmd += [f"--author={author}"]

    root = _repo_root()
    raw = _run(cmd, cwd=root)
    if not raw:
        return []

    records: list[CommitRecord] = []
    # Split on blank lines — each commit block starts with the NUL-delimited header
    blocks = re.split(r"\n(?=\S.*\x00)", raw)

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        header_line = lines[0]
        parts = header_line.split(_SEP)
        if len(parts) < 5:
            continue
        sha, author_name, email, ts, subject = parts[0], parts[1], parts[2], parts[3], parts[4]

        insertions = deletions = files_changed = 0
        for line in lines[1:]:
            m = re.match(r"(\d+)\s+(\d+)\s+(\S+)", line)
            if m:
                insertions += int(m.group(1))
                deletions += int(m.group(2))
                files_changed += 1

        records.append(CommitRecord(
            sha=sha[:8],
            author=author_name,
            email=email,
            timestamp=ts,
            subject=subject,
            insertions=insertions,
            deletions=deletions,
            files_changed=files_changed,
        ))

    return records


# ---------------------------------------------------------------------------
# Churn analysis
# ---------------------------------------------------------------------------

def _compute_churn(days: int) -> list[ChurnRecord]:
    """Return the top 20 most-changed files in the period."""
    since = _since_date(days)
    root = _repo_root()
    raw = _run(
        ["git", "log", f"--since={since}", "--numstat", "--format="],
        cwd=root,
    )
    if not raw:
        return []

    file_stats: dict[str, dict] = defaultdict(lambda: {"changes": 0, "ins": 0, "dels": 0})
    for line in raw.splitlines():
        m = re.match(r"(\d+)\s+(\d+)\s+(\S+)", line)
        if m:
            ins, dels, path = int(m.group(1)), int(m.group(2)), m.group(3)
            file_stats[path]["changes"] += 1
            file_stats[path]["ins"] += ins
            file_stats[path]["dels"] += dels

    sorted_files = sorted(file_stats.items(), key=lambda x: x[1]["changes"], reverse=True)
    return [
        ChurnRecord(path=p, changes=s["changes"], insertions=s["ins"], deletions=s["dels"])
        for p, s in sorted_files[:20]
    ]


# ---------------------------------------------------------------------------
# Branch analysis
# ---------------------------------------------------------------------------

def _branch_stats() -> tuple[int, list[str]]:
    """Return (total_branch_count, list_of_stale_branch_names)."""
    root = _repo_root()
    raw = _run(
        ["git", "branch", "-r", "--format=%(refname:short) %(committerdate:iso)"],
        cwd=root,
    )
    if not raw:
        return 0, []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale: list[str] = []
    total = 0
    for line in raw.splitlines():
        parts = line.strip().split(" ", 1)
        if not parts:
            continue
        total += 1
        if len(parts) == 2:
            try:
                dt = datetime.fromisoformat(parts[1].replace(" +", "+").replace(" -", "-"))
                if dt.replace(tzinfo=timezone.utc) < cutoff:
                    stale.append(parts[0])
            except Exception:
                pass

    return total, stale


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def generate_gitstats_report(
    days: int = 30,
    author: Optional[str] = None,
) -> GitStatsReport:
    """Generate a full git statistics report."""

    commits = _parse_commits(days=days, author=author)
    churn = _compute_churn(days=days)
    branch_count, stale_branches = _branch_stats()

    # Aggregate author stats
    author_map: dict[str, dict] = defaultdict(lambda: {
        "commits": 0, "ins": 0, "dels": 0, "files": 0,
        "dates": [], "email": "",
    })
    for c in commits:
        a = author_map[c.author]
        a["commits"] += 1
        a["ins"] += c.insertions
        a["dels"] += c.deletions
        a["files"] += c.files_changed
        a["dates"].append(c.timestamp)
        a["email"] = c.email

    author_stats = [
        AuthorStats(
            author=name,
            email=s["email"],
            commits=s["commits"],
            insertions=s["ins"],
            deletions=s["dels"],
            files_changed=s["files"],
            first_commit=min(s["dates"]) if s["dates"] else "",
            last_commit=max(s["dates"]) if s["dates"] else "",
            active_days=len(set(d[:10] for d in s["dates"])),
        )
        for name, s in sorted(author_map.items(), key=lambda x: -x[1]["commits"])
    ]

    # Day-level commit counts
    day_counts: dict[str, int] = defaultdict(int)
    for c in commits:
        day_counts[c.timestamp[:10]] += 1

    busiest_day = max(day_counts, key=lambda d: day_counts[d]) if day_counts else ""
    busiest_count = day_counts.get(busiest_day, 0)

    total_ins = sum(c.insertions for c in commits)
    total_dels = sum(c.deletions for c in commits)
    cpd = len(commits) / days if days else 0

    summary = (
        f"{len(commits)} commits over {days} days "
        f"(~{cpd:.1f}/day). "
        f"+{total_ins}/−{total_dels} lines. "
        f"{len(author_stats)} active author(s). "
        f"{branch_count} branches ({len(stale_branches)} stale)."
    )

    return GitStatsReport(
        period_days=days,
        total_commits=len(commits),
        total_insertions=total_ins,
        total_deletions=total_dels,
        active_authors=len(author_stats),
        commits_per_day=round(cpd, 2),
        busiest_day=busiest_day,
        busiest_day_count=busiest_count,
        author_stats=author_stats,
        top_churn_files=churn,
        recent_commits=commits[:20],
        branch_count=branch_count,
        stale_branches=stale_branches,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_gitstats_report(report: GitStatsReport) -> str:
    """Render a GitStatsReport as a human-readable string."""

    lines = [
        "═" * 70,
        "  AWAKE — GIT STATISTICS",
        "═" * 70,
        f"  Period       : last {report.period_days} days",
        f"  Commits      : {report.total_commits}  ({report.commits_per_day}/day avg)",
        f"  Lines added  : +{report.total_insertions}  removed: −{report.total_deletions}",
        f"  Authors      : {report.active_authors}",
        f"  Branches     : {report.branch_count} total, {len(report.stale_branches)} stale",
        f"  Busiest day  : {report.busiest_day}  ({report.busiest_day_count} commits)",
        f"  Summary      : {report.summary}",
        "",
    ]

    # Author breakdown
    if report.author_stats:
        lines += [
            "─" * 70,
            "  AUTHORS",
            "─" * 70,
        ]
        for a in report.author_stats:
            lines += [
                f"  {a.author} <{a.email}>",
                f"    commits={a.commits}  +{a.insertions}/−{a.deletions}  "
                f"files={a.files_changed}  active_days={a.active_days}",
                f"    first={a.first_commit[:10]}  last={a.last_commit[:10]}",
                "",
            ]

    # Top churn files
    if report.top_churn_files:
        lines += [
            "─" * 70,
            "  TOP CHURN FILES",
            "─" * 70,
        ]
        for f in report.top_churn_files[:10]:
            lines += [
                f"  {f.path}",
                f"    changes={f.changes}  +{f.insertions}/−{f.deletions}",
            ]
        lines.append("")

    # Recent commits
    if report.recent_commits:
        lines += [
            "─" * 70,
            "  RECENT COMMITS (up to 20)",
            "─" * 70,
        ]
        for c in report.recent_commits:
            lines.append(
                f"  {c.sha}  {c.timestamp[:10]}  {c.author[:20]:<20}  {c.subject[:50]}"
            )
        lines.append("")

    # Stale branches
    if report.stale_branches:
        lines += [
            "─" * 70,
            "  STALE BRANCHES (>30 days inactive)",
            "─" * 70,
        ]
        for b in report.stale_branches:
            lines.append(f"  {b}")
        lines.append("")

    lines.append("═" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(args=None) -> int:
    """CLI entry point for `awake gitstats`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="awake gitstats",
        description="Deep-dive git statistics",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--days", type=int, default=30, help="Analysis window (default: 30)")
    parser.add_argument("--author", type=str, default=None, help="Filter by author name")

    parsed = parser.parse_args(args)

    report = generate_gitstats_report(days=parsed.days, author=parsed.author)

    if parsed.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_gitstats_report(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
