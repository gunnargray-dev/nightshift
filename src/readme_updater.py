"""README auto-updater for Awake.

Generates a dynamic README.md from live repo state, including:
- Session count and last-run timestamp
- File tree of src/ with docstring summaries
- Test status badge (pass/fail count from latest pytest run)
- Recent activity: last N commits with conventional-commit parsing
- Roadmap progress: checked vs unchecked items
- Stats snapshot: PRs, lines of code, health score

Designed to run at the end of each Awake session and push the
refreshed README directly to main via the GitHub API.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileEntry:
    """A source file with its summary line."""

    path: str
    description: str
    lines: int


@dataclass
class RoadmapProgress:
    """Checked vs total items from ROADMAP.md."""

    checked: int
    total: int
    percent: float = field(init=False)

    def __post_init__(self) -> None:
        self.percent = round(self.checked / self.total * 100, 1) if self.total else 0.0


@dataclass
class CommitEntry:
    """A single git commit parsed into type / scope / description."""

    sha: str
    commit_type: str   # feat | fix | refactor | test | ci | docs | meta
    description: str
    session: Optional[int]


@dataclass
class RepoSnapshot:
    """All data needed to render the README."""

    project: str
    version: str
    session_count: int
    last_run: str           # ISO-8601 UTC
    source_files: list[FileEntry]
    test_count: int
    tests_passing: bool
    recent_commits: list[CommitEntry]
    roadmap: RoadmapProgress
    open_prs: int
    total_lines: int
    health_score: float


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a subprocess and return stdout (stripped)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, check=False
    )
    return result.stdout.strip()


def get_recent_commits(repo_root: Path, n: int = 10) -> list[CommitEntry]:
    """Return the last *n* commits parsed into CommitEntry objects."""
    log = _run(
        ["git", "log", f"-{n}", "--pretty=format:%h|||%s"],
        cwd=repo_root,
    )
    entries: list[CommitEntry] = []
    pattern = re.compile(
        r"^\[awake\]\s+(?P<type>[\w]+)(?:\((?P<scope>[^)]+)\))?:\s+(?P<desc>.+)$"
    )
    session_pat = re.compile(r"session[\s-]*(?P<n>\d+)", re.IGNORECASE)
    for line in log.splitlines():
        if "|||" not in line:
            continue
        sha, subject = line.split("|||", 1)
        m = pattern.match(subject)
        if m:
            commit_type = m.group("type")
            description = m.group("desc")
        else:
            commit_type = "misc"
            description = subject
        sm = session_pat.search(subject)
        session_num = int(sm.group("n")) if sm else None
        entries.append(CommitEntry(sha=sha, commit_type=commit_type, description=description, session=session_num))
    return entries


def get_roadmap_progress(repo_root: Path) -> RoadmapProgress:
    """Count checked/unchecked items in ROADMAP.md."""
    roadmap_path = repo_root / "ROADMAP.md"
    if not roadmap_path.exists():
        return RoadmapProgress(checked=0, total=0)
    text = roadmap_path.read_text(encoding="utf-8")
    checked = len(re.findall(r"- \[x\]", text, re.IGNORECASE))
    unchecked = len(re.findall(r"- \[ \]", text))
    return RoadmapProgress(checked=checked, total=checked + unchecked)


def get_source_files(src_dir: Path) -> list[FileEntry]:
    """Collect .py files in src/ with line counts and first docstring line."""
    entries: list[FileEntry] = []
    for py_file in sorted(src_dir.glob("*.py")):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        line_count = len(lines)
        description = ""
        in_docstring = False
        for raw in lines:
            stripped = raw.strip()
            if stripped.startswith('"""') and not in_docstring:
                doc_line = stripped.lstrip('"').strip()
                if doc_line:
                    description = doc_line.split("\"\"\"")[0].strip()
                    break
                in_docstring = True
            elif in_docstring:
                if stripped:
                    description = stripped
                    break
        entries.append(FileEntry(path=str(py_file.relative_to(src_dir.parent)), description=description, lines=line_count))
    return entries


def get_test_status(repo_root: Path) -> tuple[int, bool]:
    """Run pytest --tb=no -q and return (test_count, all_passing)."""
    out = _run(["python", "-m", "pytest", "--tb=no", "-q"], cwd=repo_root)
    m = re.search(r"(\d+) passed", out)
    count = int(m.group(1)) if m else 0
    passing = "failed" not in out and "error" not in out.lower()
    return count, passing


def get_open_prs() -> int:
    """Return the number of open PRs (requires gh CLI)."""
    out = _run(["gh", "pr", "list", "--state", "open", "--json", "number"])
    try:
        return len(__import__("json").loads(out))
    except Exception:
        return 0


def get_total_lines(repo_root: Path) -> int:
    """Count total non-blank lines across .py files."""
    total = 0
    for py_file in repo_root.rglob("*.py"):
        try:
            lines = py_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            total += sum(1 for ln in lines if ln.strip())
        except OSError:
            pass
    return total


def compute_health_score(
    tests_passing: bool,
    roadmap: RoadmapProgress,
    recent_commits: list[CommitEntry],
) -> float:
    """Heuristic 0-100 score: tests 50 pts, roadmap 30 pts, recent activity 20 pts."""
    score = 0.0
    if tests_passing:
        score += 50.0
    score += roadmap.percent * 0.30
    activity = min(len(recent_commits), 10) / 10 * 20
    score += activity
    return round(score, 1)


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def build_snapshot(repo_root: Path) -> RepoSnapshot:
    """Collect all metrics and return a RepoSnapshot."""
    src_dir = repo_root / "src"
    source_files = get_source_files(src_dir)
    test_count, tests_passing = get_test_status(repo_root)
    recent_commits = get_recent_commits(repo_root)
    roadmap = get_roadmap_progress(repo_root)
    open_prs = get_open_prs()
    total_lines = get_total_lines(repo_root)
    health_score = compute_health_score(tests_passing, roadmap, recent_commits)

    # Version from git tag or fallback
    version = _run(["git", "describe", "--tags", "--abbrev=0"], cwd=repo_root) or "0.1.0"

    # Session count = number of commits whose subject matches [awake] ... session N
    all_commits = _run(
        ["git", "log", "--pretty=format:%s"],
        cwd=repo_root,
    )
    session_count = len(re.findall(r"session[\s-]*\d+", all_commits, re.IGNORECASE))

    last_run = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return RepoSnapshot(
        project="Awake",
        version=version,
        session_count=session_count,
        last_run=last_run,
        source_files=source_files,
        test_count=test_count,
        tests_passing=tests_passing,
        recent_commits=recent_commits,
        roadmap=roadmap,
        open_prs=open_prs,
        total_lines=total_lines,
        health_score=health_score,
    )


# ---------------------------------------------------------------------------
# README renderer
# ---------------------------------------------------------------------------


TEMPLATE = """\
# {project} v{version}

> Auto-generated by `readme_updater.py` · last updated {last_run} UTC

## Overview

| Metric | Value |
|--------|-------|
| Sessions | {session_count} |
| Tests | {test_badge} |
| Open PRs | {open_prs} |
| Lines of code | {total_lines:,} |
| Health score | {health_score}/100 |

## Source files

{file_table}

## Recent activity

{commit_log}

## Roadmap

{roadmap_summary}
"""


def _test_badge(passing: bool, count: int) -> str:
    if passing:
        return f"![tests](https://img.shields.io/badge/tests-{count}%20passing-brightgreen)"
    return f"![tests](https://img.shields.io/badge/tests-failing-red)"


def _file_table(files: list[FileEntry]) -> str:
    rows = ["| File | Description | Lines |", "|------|-------------|-------|"] 
    for f in files:
        rows.append(f"| `{f.path}` | {f.description} | {f.lines} |")
    return "\n".join(rows)


def _commit_log(commits: list[CommitEntry]) -> str:
    if not commits:
        return "_No commits yet._"
    lines = []
    for c in commits:
        session_tag = f" *(session {c.session})*" if c.session else ""
        lines.append(f"- `{c.sha}` **{c.commit_type}**: {c.description}{session_tag}")
    return "\n".join(lines)


def _roadmap_summary(roadmap: RoadmapProgress) -> str:
    bar_filled = int(roadmap.percent / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    return (
        f"`[{bar}]` {roadmap.percent}% complete "
        f"({roadmap.checked}/{roadmap.total} items)"
    )


def render_readme(snapshot: RepoSnapshot) -> str:
    """Render the README from a RepoSnapshot."""
    return TEMPLATE.format(
        project=snapshot.project,
        version=snapshot.version,
        last_run=snapshot.last_run,
        session_count=snapshot.session_count,
        test_badge=_test_badge(snapshot.tests_passing, snapshot.test_count),
        open_prs=snapshot.open_prs,
        total_lines=snapshot.total_lines,
        health_score=snapshot.health_score,
        file_table=_file_table(snapshot.source_files),
        commit_log=_commit_log(snapshot.recent_commits),
        roadmap_summary=_roadmap_summary(snapshot.roadmap),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Build snapshot → render README → write to repo root."""
    repo_root = Path(__file__).resolve().parent.parent
    snapshot = build_snapshot(repo_root)
    readme = render_readme(snapshot)
    out_path = repo_root / "README.md"
    out_path.write_text(readme, encoding="utf-8")
    print(f"README written to {out_path} ({len(readme)} chars)")
    print(f"Health score: {snapshot.health_score}/100")


if __name__ == "__main__":
    main()
