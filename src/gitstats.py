"""Git statistics deep-dive for Nightshift.

Provides a detailed breakdown of commit frequency, code churn rate,
average PR size, contributor velocity, and day-of-week activity patterns.
Uses only stdlib (subprocess + re) and works on any git repository.

Usage
-----
    from src.gitstats import compute_git_stats, save_git_stats_report
    report = compute_git_stats(repo_path=Path("."))
    print(report.to_markdown())
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


def _git(cmd: list[str], cwd: Path) -> str:
    """Run a git command and return stdout, or '' on failure."""
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=30,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


@dataclass
class CommitRecord:
    """Lightweight representation of a single git commit."""
    sha: str
    author: str
    date: str
    weekday: str
    hour: int
    insertions: int
    deletions: int
    files_changed: int
    subject: str

    @property
    def churn(self) -> int:
        """Return total churn (insertions plus deletions) for this commit"""
        return self.insertions + self.deletions

    @property
    def net(self) -> int:
        """Return the net line delta for this commit"""
        return self.insertions - self.deletions


@dataclass
class ContributorStats:
    """Aggregated commit statistics for a single contributor"""

    name: str
    commits: int
    insertions: int
    deletions: int

    @property
    def churn(self) -> int:
        """Return total churn (insertions plus deletions) for this contributor"""
        return self.insertions + self.deletions

    def to_dict(self) -> dict:
        """Return a dictionary representation of this contributor's stats"""
        return asdict(self)


@dataclass
class GitStatsReport:
    """Aggregated git statistics for the repository."""
    total_commits: int = 0
    total_insertions: int = 0
    total_deletions: int = 0
    total_files_changed: int = 0
    avg_insertions_per_commit: float = 0.0
    avg_deletions_per_commit: float = 0.0
    avg_churn_per_commit: float = 0.0
    avg_files_per_commit: float = 0.0
    commits_by_weekday: dict = field(default_factory=dict)
    commits_by_hour: dict = field(default_factory=dict)
    contributors: list[ContributorStats] = field(default_factory=list)
    estimated_pr_count: int = 0
    avg_pr_size_lines: float = 0.0
    active_days: int = 0
    first_commit_date: str = ""
    last_commit_date: str = ""
    churn_rate_per_day: float = 0.0
    recent_velocity: int = 0

    @property
    def contributor_count(self) -> int:
        """Return the number of contributors."""
        return len(self.contributors)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the full git stats report"""
        d = asdict(self)
        d["contributors"] = [c.to_dict() for c in self.contributors]
        return d

    def to_json(self) -> str:
        """Serialize the git stats report to a JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render the git stats report as a Markdown document"""
        lines: list[str] = ["# Nightshift Git Statistics Deep-Dive\n"]
        if self.first_commit_date:
            lines.append(f"*Date range: {self.first_commit_date} \u2192 {self.last_commit_date}*\n")

        lines += [
            "## Overview\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total commits | {self.total_commits:,} |",
            f"| Total insertions | {self.total_insertions:,} |",
            f"| Total deletions | {self.total_deletions:,} |",
            f"| Net lines added | {self.total_insertions - self.total_deletions:,} |",
            f"| Files ever touched | {self.total_files_changed:,} |",
            f"| Active days | {self.active_days} |",
            f"| Churn rate (lines/day) | {self.churn_rate_per_day:.1f} |",
            f"| Recent velocity (last 30d) | {self.recent_velocity} commits |",
            f"| Estimated PRs | {self.estimated_pr_count} |",
            f"| Avg PR size | {self.avg_pr_size_lines:.0f} lines |",
            "",
        ]

        lines += [
            "## Commit Size Averages\n",
            "| Metric | Per Commit |",
            "|--------|-----------|",
            f"| Insertions | {self.avg_insertions_per_commit:.1f} |",
            f"| Deletions | {self.avg_deletions_per_commit:.1f} |",
            f"| Churn | {self.avg_churn_per_commit:.1f} |",
            f"| Files changed | {self.avg_files_per_commit:.1f} |",
            "",
        ]

        if self.contributors:
            lines += ["## Top Contributors\n",
                      "| Author | Commits | Insertions | Deletions |",
                      "|--------|--------:|-----------:|----------:|"]
            for c in self.contributors[:10]:
                lines.append(f"| {c.name} | {c.commits} | {c.insertions:,} | {c.deletions:,} |")
            lines.append("")

        if self.commits_by_weekday:
            lines.append("## Activity by Day of Week\n")
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            max_count = max(self.commits_by_weekday.values(), default=1)
            for day in days:
                count = self.commits_by_weekday.get(day, 0)
                bar_len = int((count / max_count) * 20) if max_count else 0
                bar = "█" * bar_len
                lines.append(f"  {day[:3]}  {bar:<20} {count}")
            lines.append("")

        if self.commits_by_hour:
            lines.append("## Activity by Hour (UTC)\n")
            max_h = max(self.commits_by_hour.values(), default=1)
            for h in range(24):
                count = self.commits_by_hour.get(h, 0)
                bar_len = int((count / max_h) * 15) if max_h else 0
                bar = "█" * bar_len
                lines.append(f"  {h:02d}h  {bar:<15} {count}")
            lines.append("")

        return "\n".join(lines)


def _parse_commits(raw_log: str) -> list[CommitRecord]:
    """Parse git log output into CommitRecord objects."""
    records: list[CommitRecord] = []
    log_pattern = re.compile(
        r"^([0-9a-f]{40})\|(.+?)\|(\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\d{2}[^|]*\|(.*)$"
    )
    for line in raw_log.splitlines():
        m = log_pattern.match(line.strip())
        if not m:
            continue
        sha, author, date_str, hour_str, subject = m.groups()
        import datetime
        try:
            dt = datetime.date.fromisoformat(date_str)
            weekday = dt.strftime("%A")
        except ValueError:
            weekday = "Unknown"
        records.append(CommitRecord(
            sha=sha, author=author, date=date_str, weekday=weekday,
            hour=int(hour_str), insertions=0, deletions=0, files_changed=0, subject=subject,
        ))
    return records


def _enrich_with_numstat(records: list[CommitRecord], cwd: Path) -> None:
    """Fill insertions/deletions/files_changed using git diff-tree --numstat."""
    if not records:
        return
    sha_map = {r.sha: r for r in records[:200]}
    for sha, r in sha_map.items():
        out = _git(["diff-tree", "--numstat", "-r", "--no-commit-id", sha], cwd)
        ins = dels = files = 0
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                try:
                    ins += int(parts[0])
                    dels += int(parts[1])
                    files += 1
                except ValueError:
                    pass
        r.insertions, r.deletions, r.files_changed = ins, dels, files


def compute_git_stats(repo_path: Optional[Path] = None) -> GitStatsReport:
    """Compute detailed git statistics for *repo_path*."""
    import datetime
    repo = repo_path or Path(__file__).resolve().parent.parent
    raw_log = _git(["log", "--format=%H|%aN|%ai|%s", "--no-merges"], repo)
    records = _parse_commits(raw_log)
    if not records:
        return GitStatsReport()

    _enrich_with_numstat(records, repo)

    total_commits = len(records)
    total_ins = sum(r.insertions for r in records)
    total_dels = sum(r.deletions for r in records)
    total_files = sum(r.files_changed for r in records)

    commits_by_weekday: dict[str, int] = defaultdict(int)
    commits_by_hour: dict[int, int] = defaultdict(int)
    contributor_commits: dict[str, int] = defaultdict(int)
    contributor_ins: dict[str, int] = defaultdict(int)
    contributor_dels: dict[str, int] = defaultdict(int)
    active_dates: set[str] = set()

    for r in records:
        commits_by_weekday[r.weekday] += 1
        commits_by_hour[r.hour] += 1
        contributor_commits[r.author] += 1
        contributor_ins[r.author] += r.insertions
        contributor_dels[r.author] += r.deletions
        active_dates.add(r.date)

    active_days = len(active_dates)
    dates_sorted = sorted(active_dates)
    first_date = dates_sorted[0] if dates_sorted else ""
    last_date = dates_sorted[-1] if dates_sorted else ""
    churn_rate = ((total_ins + total_dels) / active_days) if active_days else 0.0

    recent_velocity = 0
    if last_date:
        try:
            last_dt = datetime.date.fromisoformat(last_date)
            cutoff = last_dt - datetime.timedelta(days=30)
            recent_velocity = sum(1 for r in records if r.date >= cutoff.isoformat())
        except ValueError:
            pass

    full_log = _git(["log", "--format=%s"], repo)
    estimated_prs = sum(
        1 for line in full_log.splitlines()
        if re.search(r"(merge pull request|^merge branch)", line, re.I)
    )
    avg_pr_size = (total_ins + total_dels) / estimated_prs if estimated_prs else 0.0

    contributors = [
        ContributorStats(name=name, commits=contributor_commits[name],
                         insertions=contributor_ins[name], deletions=contributor_dels[name])
        for name in contributor_commits
    ]
    contributors.sort(key=lambda c: c.commits, reverse=True)

    return GitStatsReport(
        total_commits=total_commits, total_insertions=total_ins, total_deletions=total_dels,
        total_files_changed=total_files,
        avg_insertions_per_commit=total_ins / total_commits if total_commits else 0.0,
        avg_deletions_per_commit=total_dels / total_commits if total_commits else 0.0,
        avg_churn_per_commit=(total_ins + total_dels) / total_commits if total_commits else 0.0,
        avg_files_per_commit=total_files / total_commits if total_commits else 0.0,
        commits_by_weekday=dict(commits_by_weekday),
        commits_by_hour={k: v for k, v in sorted(commits_by_hour.items())},
        contributors=contributors, estimated_pr_count=estimated_prs, avg_pr_size_lines=avg_pr_size,
        active_days=active_days, first_commit_date=first_date, last_commit_date=last_date,
        churn_rate_per_day=churn_rate, recent_velocity=recent_velocity,
    )


def save_git_stats_report(report: GitStatsReport, output_path: Path) -> None:
    """Write Markdown + JSON sidecar to *output_path*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown())
    output_path.with_suffix(".json").write_text(report.to_json())
