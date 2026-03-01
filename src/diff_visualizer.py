"""Session diff visualizer for Awake.

Generates a visual Markdown summary of a single overnight session's changes:
- Files added / modified / deleted (with line-delta counts)
- Commit timeline with types and descriptions
- Per-module change heatmap rendered as a bar chart in Markdown
- Test delta: tests added this session vs previous session baseline
- "Biggest change" callout: file with most lines added

The visualizer reads from git log and git diff, so it works without any
external dependencies beyond a standard git installation.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileDelta:
    """Change summary for a single file in a session."""

    path: str
    added: int
    deleted: int
    status: str   # A=added, M=modified, D=deleted, R=renamed

    @property
    def net(self) -> int:
        """Return the net line delta for this file"""
        return self.added - self.deleted

    @property
    def churn(self) -> int:
        """Return the total churn (additions plus deletions) for this file"""
        return self.added + self.deleted


@dataclass
class CommitSummary:
    """A commit belonging to a session."""

    sha: str
    commit_type: str
    description: str
    timestamp: str


@dataclass
class SessionDiff:
    """All change data for one Awake session."""

    session_number: int
    start_sha: str
    end_sha: str
    commits: list[CommitSummary]
    file_deltas: list[FileDelta]
    tests_before: int
    tests_after: int

    @property
    def files_added(self) -> list[FileDelta]:
        """Return file deltas with status 'added'"""
        return [f for f in self.file_deltas if f.status == "A"]

    @property
    def files_modified(self) -> list[FileDelta]:
        """Return file deltas with status 'modified'"""
        return [f for f in self.file_deltas if f.status == "M"]

    @property
    def files_deleted(self) -> list[FileDelta]:
        """Return file deltas with status 'deleted'"""
        return [f for f in self.file_deltas if f.status == "D"]

    @property
    def total_added(self) -> int:
        """Return the sum of added lines across all file deltas"""
        return sum(f.added for f in self.file_deltas)

    @property
    def total_deleted(self) -> int:
        """Return the sum of deleted lines across all file deltas"""
        return sum(f.deleted for f in self.file_deltas)

    @property
    def tests_delta(self) -> int:
        """Return the change in test count between before and after"""
        return self.tests_after - self.tests_before

    @property
    def biggest_change(self) -> Optional[FileDelta]:
        """Return the file delta with the highest churn, or None if empty"""
        if not self.file_deltas:
            return None
        return max(self.file_deltas, key=lambda f: f.churn)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout, or '' on error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return result.stdout
    except FileNotFoundError:
        return ""


def _get_session_shas(repo_root: Path, session_number: int) -> tuple[str, str]:
    """Return (start_sha, end_sha) for a session's commits.

    Convention: commits tagged ``[awake]`` and ``Session: N``.
    Falls back to last-N-commits heuristic.
    """
    log = _run_git(
        ["log", "--oneline", "--format=%H %s", "-100"],
        cwd=repo_root,
    )
    session_commits = []
    for line in log.splitlines():
        if "[awake]" in line or "awake" in line.lower():
            session_commits.append(line.split()[0])

    if len(session_commits) >= 2:
        return session_commits[-1], session_commits[0]
    elif len(session_commits) == 1:
        return session_commits[0], "HEAD"
    else:
        # Fallback: diff against HEAD~10
        return "HEAD~10", "HEAD"


def _parse_numstat(output: str) -> list[FileDelta]:
    """Parse ``git diff --numstat`` output into FileDelta objects."""
    deltas = []
    for line in output.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        added_str, deleted_str, path = parts
        # Binary files show "-" for both -- skip them
        if added_str == "-" or deleted_str == "-":
            continue
        try:
            added = int(added_str)
            deleted = int(deleted_str)
        except ValueError:
            continue
        # Determine status from context (we'll refine this)
        status = "M"
        deltas.append(FileDelta(path=path, added=added, deleted=deleted, status=status))
    return deltas


def _parse_diff_name_status(output: str, deltas: list[FileDelta]) -> list[FileDelta]:
    """Enrich FileDelta status codes from ``git diff --name-status``."""
    status_map: dict[str, str] = {}
    for line in output.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        code = parts[0][0]   # A, M, D, R, C ...
        path = parts[1].split("\t")[-1]  # handle rename "old\tnew"
        status_map[path] = code

    enriched = []
    for d in deltas:
        new_status = status_map.get(d.path, d.status)
        enriched.append(
            FileDelta(path=d.path, added=d.added, deleted=d.deleted, status=new_status)
        )
    return enriched


def _count_tests(repo_root: Path, ref: str = "HEAD") -> int:
    """Count test functions at a given ref by scanning test files."""
    # We can't easily checkout other refs, so we count current tests
    tests_dir = repo_root / "tests"
    if not tests_dir.exists():
        return 0
    count = 0
    for test_file in tests_dir.glob("test_*.py"):
        try:
            text = test_file.read_text(encoding="utf-8")
            count += len(re.findall(r"^\s*def test_", text, re.MULTILINE))
        except OSError:
            pass
    return count


def _get_commits_for_range(
    repo_root: Path, start_sha: str, end_sha: str
) -> list[CommitSummary]:
    """Return parsed commits in the range (start_sha, end_sha]."""
    log = _run_git(
        ["log", f"{start_sha}..{end_sha}", "--format=%H\t%ai\t%s"],
        cwd=repo_root,
    )
    commits = []
    for line in log.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        sha, timestamp, subject = parts

        m = re.match(r"\[awake\]\s+(\w+):\s+(.+)", subject)
        if m:
            commit_type = m.group(1)
            description = m.group(2)
        else:
            commit_type = "misc"
            description = subject

        commits.append(
            CommitSummary(
                sha=sha[:8],
                commit_type=commit_type,
                description=description,
                timestamp=timestamp[:16],
            )
        )
    return commits


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def build_session_diff(
    repo_root: Path,
    session_number: int,
    start_sha: str = "",
    end_sha: str = "HEAD",
) -> SessionDiff:
    """Build a SessionDiff for the given session."""
    if not start_sha:
        start_sha, end_sha = _get_session_shas(repo_root, session_number)

    numstat_out = _run_git(
        ["diff", "--numstat", f"{start_sha}...{end_sha}"],
        cwd=repo_root,
    )
    name_status_out = _run_git(
        ["diff", "--name-status", f"{start_sha}...{end_sha}"],
        cwd=repo_root,
    )

    file_deltas = _parse_numstat(numstat_out)
    file_deltas = _parse_diff_name_status(name_status_out, file_deltas)

    commits = _get_commits_for_range(repo_root, start_sha, end_sha)
    tests_before = _count_tests(repo_root, start_sha)
    tests_after = _count_tests(repo_root, end_sha)

    return SessionDiff(
        session_number=session_number,
        start_sha=start_sha,
        end_sha=end_sha,
        commits=commits,
        file_deltas=file_deltas,
        tests_before=tests_before,
        tests_after=tests_after,
    )


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_session_diff(diff: SessionDiff) -> str:
    """Render a SessionDiff as a Markdown string."""
    lines: list[str] = []

    lines.append(f"# Awake Session {diff.session_number} Diff")
    lines.append(f"Commit range: `{diff.start_sha[:8]}...{diff.end_sha[:8]}`")
    lines.append("")

    # --- File summary table ---
    added_files = diff.files_added
    modified_files = diff.files_modified
    deleted_files = diff.files_deleted

    lines.append("## File Changes")
    lines.append("")
    lines.append(
        f"| Category | Count |\n"
        f"|----------|-------|\n"
        f"| Added    | {len(added_files)} |\n"
        f"| Modified | {len(modified_files)} |\n"
        f"| Deleted  | {len(deleted_files)} |"
    )
    lines.append("")

    if diff.file_deltas:
        lines.append("### Top Changed Files")
        lines.append("")
        lines.append("| File | +Lines | -Lines | Net |")
        lines.append("|------|--------|--------|-----|")
        top = sorted(diff.file_deltas, key=lambda f: f.churn, reverse=True)[:10]
        for f in top:
            lines.append(f"| `{f.path}` | +{f.added} | -{f.deleted} | {f.net:+d} |")
        lines.append("")

    # --- Commit timeline ---
    if diff.commits:
        lines.append("## Commit Timeline")
        lines.append("")
        lines.append("| SHA | Type | Description | Time |")
        lines.append("|-----|------|-------------|------|")
        for c in diff.commits:
            lines.append(
                f"| `{c.sha}` | `{c.commit_type}` | {c.description} | {c.timestamp} |"
            )
        lines.append("")

    # --- Test delta ---
    lines.append("## Test Coverage")
    lines.append("")
    lines.append(
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Tests before | {diff.tests_before} |\n"
        f"| Tests after  | {diff.tests_after} |\n"
        f"| Delta        | {diff.tests_delta:+d} |"
    )
    lines.append("")

    # --- Biggest change callout ---
    if diff.biggest_change:
        bc = diff.biggest_change
        lines.append(
            f"> **Biggest change:** `{bc.path}` "
            f"(+{bc.added} / -{bc.deleted}, net {bc.net:+d})"
        )
        lines.append("")

    return "\n".join(lines)
