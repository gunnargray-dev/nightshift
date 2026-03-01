"""Self-stats engine for Nightshift.

Analyzes git history (or GitHub API data) and computes repository statistics:
- Total PRs merged
- Total commits
- Lines changed
- Session streak
- Active nights
- Per-session stats

These stats are used to update README.md and NIGHTSHIFT_LOG.md at the end
of each autonomous session.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class RepoStats:
    """Aggregate statistics for the Nightshift repository."""

    nights_active: int = 0
    total_prs: int = 0
    total_commits: int = 0
    lines_changed: int = 0
    sessions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the repository stats"""
        return asdict(self)

    def readme_table(self) -> str:
        """Render the stats as a Markdown table row set (README format)."""
        rows = [
            ("Nights active", self.nights_active),
            ("Total PRs", self.total_prs),
            ("Total commits", self.total_commits),
            ("Lines changed", self.lines_changed),
        ]
        header = "| Metric | Count |\n|--------|-------|" 
        body = "\n".join(f"| {label} | {value} |" for label, value in rows)
        return f"{header}\n{body}"


def _run_git(args: list[str], cwd: Optional[Path] = None) -> str:
    """Run a git command and return stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or Path.cwd(),
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def count_commits(repo_path: Optional[Path] = None) -> int:
    """Count total commits in the repository."""
    output = _run_git(["rev-list", "--count", "HEAD"], cwd=repo_path)
    try:
        return int(output)
    except ValueError:
        return 0


def count_lines_changed(repo_path: Optional[Path] = None) -> int:
    """Count total lines inserted + deleted across all commits."""
    output = _run_git(
        ["log", "--shortstat", "--oneline"],
        cwd=repo_path,
    )
    insertions = 0
    deletions = 0
    for line in output.splitlines():
        # Matches lines like: " 3 files changed, 42 insertions(+), 7 deletions(-)"
        ins_match = re.search(r"(\d+) insertion", line)
        del_match = re.search(r"(\d+) deletion", line)
        if ins_match:
            insertions += int(ins_match.group(1))
        if del_match:
            deletions += int(del_match.group(1))
    return insertions + deletions


def get_commit_messages(repo_path: Optional[Path] = None) -> list[str]:
    """Return all commit messages in the repository."""
    output = _run_git(
        ["log", "--pretty=format:%s"],
        cwd=repo_path,
    )
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def count_nightshift_sessions(repo_path: Optional[Path] = None) -> int:
    """Count unique Nightshift session numbers from commit messages.

    Nightshift commits follow the format: [nightshift] <type>: <description>
    Session entries in NIGHTSHIFT_LOG.md track session numbers.
    """
    messages = get_commit_messages(repo_path)
    nightshift_commits = [m for m in messages if m.startswith("[nightshift]")]
    if not nightshift_commits:
        return 0
    # Each session produces multiple commits; deduplicate by Session: N in body
    output = _run_git(
        ["log", "--pretty=format:%B", "--grep=\\[nightshift\\]"],
        cwd=repo_path,
    )
    session_numbers = set(re.findall(r"Session:\s*(\d+)", output))
    return len(session_numbers)


def parse_nightshift_log(log_path: Path) -> list[dict]:
    """Parse NIGHTSHIFT_LOG.md and extract per-session metadata."""
    if not log_path.exists():
        return []

    content = log_path.read_text(encoding="utf-8")
    sessions = []

    # Match session headers like: ## Session 1 — February 27, 2026
    session_blocks = re.split(r"(?=^## Session \d+)", content, flags=re.MULTILINE)

    for block in session_blocks:
        header_match = re.match(
            r"## Session (\d+) — (.+?)$", block, flags=re.MULTILINE
        )
        if not header_match:
            continue

        session_num = int(header_match.group(1))
        session_date = header_match.group(2).strip()

        # Extract PR count from block
        pr_matches = re.findall(r"PR #(\d+)", block)
        pr_count = len(set(pr_matches))

        # Extract tasks count
        task_matches = re.findall(r"^\s*[-*]\s+\*\*[^\*]+\*\*", block, flags=re.MULTILINE)
        task_count = len(task_matches)

        sessions.append(
            {
                "session": session_num,
                "date": session_date,
                "prs": pr_count,
                "tasks": task_count,
            }
        )

    return sessions


def compute_stats(
    repo_path: Optional[Path] = None,
    log_path: Optional[Path] = None,
    pr_count: int = 0,
) -> RepoStats:
    """Compute full repository statistics.

    Args:
        repo_path: Path to the git repository root. Defaults to CWD.
        log_path: Path to NIGHTSHIFT_LOG.md. Defaults to repo_path/NIGHTSHIFT_LOG.md.
        pr_count: Total PR count from GitHub API (since git doesn't track PRs locally).

    Returns:
        RepoStats populated with current values.
    """
    rp = repo_path or Path.cwd()
    lp = log_path or (rp / "NIGHTSHIFT_LOG.md")

    sessions = parse_nightshift_log(lp)
    nights = count_nightshift_sessions(rp)
    # Use session log count if git parsing returned zero (fresh clone with log)
    if nights == 0 and sessions:
        nights = len([s for s in sessions if s["session"] > 0])

    return RepoStats(
        nights_active=nights,
        total_prs=pr_count or sum(s["prs"] for s in sessions),
        total_commits=count_commits(rp),
        lines_changed=count_lines_changed(rp),
        sessions=sessions,
    )


def update_readme_stats(readme_path: Path, stats: RepoStats) -> str:
    """Replace the stats table in README.md with updated values.

    Returns the new README content (does not write to disk).
    """
    content = readme_path.read_text(encoding="utf-8")
    new_table = stats.readme_table()

    # Replace existing table between ## Stats and the next ## section
    pattern = r"(## Stats\n\n)(\|[^\n]*\n\|[-| ]*\n(?:\|[^\n]*\n)+)"
    replacement = r"\g<1>" + new_table + "\n"
    updated = re.sub(pattern, replacement, content)

    # If no table found, append it
    if updated == content:
        updated = content + f"\n## Stats\n\n{new_table}\n"

    return updated
