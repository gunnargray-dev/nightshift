"""Session health-report generator for Awake.

Produces a structured Markdown report at the end of each session covering:
- Session metadata (number, date, duration)
- Test outcomes (pass / fail counts, new tests added)
- Commit summary (count, types, conventional-commit compliance)
- Refactoring activity (smells fixed, complexity delta)
- Roadmap delta (items checked off this session)
- Health score (composite 0-100)

The report is written to reports/session_<N>.md and optionally
appended to CHANGELOG.md.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TestOutcome:
    """Test run results for the session."""

    total: int
    passed: int
    failed: int
    new_tests: int

    @property
    def pass_rate(self) -> float:
        return round(self.passed / self.total * 100, 1) if self.total else 0.0


@dataclass
class CommitSummary:
    """Commit statistics for the session."""

    total: int
    by_type: dict[str, int]   # e.g. {"feat": 2, "fix": 1}
    cc_compliant: int         # commits matching conventional-commit pattern


@dataclass
class RefactorDelta:
    """Change in code-smell count between session start and end."""

    smells_before: int
    smells_after: int

    @property
    def delta(self) -> int:
        return self.smells_after - self.smells_before

    @property
    def improved(self) -> bool:
        return self.delta < 0


@dataclass
class SessionReport:
    """Complete health report for a single Awake session."""

    session: int
    date: str               # YYYY-MM-DD
    duration_min: Optional[int]
    test_outcome: TestOutcome
    commit_summary: CommitSummary
    refactor_delta: RefactorDelta
    roadmap_items_closed: int
    health_score: float     # 0-100
    notes: str              # free-text remarks


# ---------------------------------------------------------------------------
# Metric collectors
# ---------------------------------------------------------------------------


def _run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, check=False).stdout.strip()


def collect_test_outcome(repo_root: Path, prev_test_count: int = 0) -> TestOutcome:
    """Run pytest and parse results."""
    out = _run(["python", "-m", "pytest", "--tb=no", "-q"], cwd=repo_root)
    total_m = re.search(r"(\d+) passed", out)
    failed_m = re.search(r"(\d+) failed", out)
    total = int(total_m.group(1)) if total_m else 0
    failed = int(failed_m.group(1)) if failed_m else 0
    passed = total - failed
    new_tests = max(0, total - prev_test_count)
    return TestOutcome(total=total, passed=passed, failed=failed, new_tests=new_tests)


_CC_RE = re.compile(
    r"^\[awake\]\s+(feat|fix|refactor|test|ci|docs|meta|chore)"
    r"(?:\([^)]+\))?!?:\s+"
)


def collect_commit_summary(repo_root: Path, since_sha: Optional[str] = None) -> CommitSummary:
    """Summarise commits since *since_sha* (or last tag if None)."""
    base = since_sha or _run(["git", "describe", "--tags", "--abbrev=0"], cwd=repo_root)
    if not base:
        log_range = "HEAD"
    else:
        log_range = f"{base}..HEAD"
    subjects = _run(["git", "log", log_range, "--pretty=format:%s"], cwd=repo_root).splitlines()
    by_type: dict[str, int] = {}
    cc_compliant = 0
    for subj in subjects:
        m = _CC_RE.match(subj)
        if m:
            cc_compliant += 1
            t = m.group(1)
            by_type[t] = by_type.get(t, 0) + 1
        else:
            by_type["misc"] = by_type.get("misc", 0) + 1
    return CommitSummary(total=len(subjects), by_type=by_type, cc_compliant=cc_compliant)


def collect_roadmap_delta(repo_root: Path, prev_checked: int = 0) -> int:
    """Return how many new roadmap items were checked off this session."""
    roadmap = repo_root / "ROADMAP.md"
    if not roadmap.exists():
        return 0
    text = roadmap.read_text(encoding="utf-8")
    checked = len(re.findall(r"- \[x\]", text, re.IGNORECASE))
    return max(0, checked - prev_checked)


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------


def compute_health_score(
    tests: TestOutcome,
    commits: CommitSummary,
    refactor: RefactorDelta,
    roadmap_closed: int,
) -> float:
    """
    Composite 0-100 score.
    - Tests passing     : up to 40 pts
    - CC compliance     : up to 20 pts
    - Refactor progress : up to 20 pts (negative delta is good)
    - Roadmap progress  : up to 20 pts
    """
    score = 0.0
    # Tests
    score += tests.pass_rate * 0.40
    # CC compliance
    cc_rate = (commits.cc_compliant / commits.total * 100) if commits.total else 0
    score += cc_rate * 0.20
    # Refactor (each smell removed = +2 pts, capped at 20)
    if refactor.delta < 0:
        score += min(abs(refactor.delta) * 2, 20)
    # Roadmap
    score += min(roadmap_closed * 5, 20)
    return round(score, 1)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(
    session: int,
    repo_root: Path,
    prev_test_count: int = 0,
    prev_smell_count: int = 0,
    prev_roadmap_checked: int = 0,
    since_sha: Optional[str] = None,
    duration_min: Optional[int] = None,
    notes: str = "",
) -> SessionReport:
    """Collect all metrics and return a SessionReport."""
    tests = collect_test_outcome(repo_root, prev_test_count)
    commits = collect_commit_summary(repo_root, since_sha)
    # Current smell count via a lightweight scan
    from src.refactor import scan_repo
    smells_after = len(scan_repo(repo_root))
    refactor = RefactorDelta(smells_before=prev_smell_count, smells_after=smells_after)
    roadmap_closed = collect_roadmap_delta(repo_root, prev_roadmap_checked)
    health = compute_health_score(tests, commits, refactor, roadmap_closed)
    return SessionReport(
        session=session,
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        duration_min=duration_min,
        test_outcome=tests,
        commit_summary=commits,
        refactor_delta=refactor,
        roadmap_items_closed=roadmap_closed,
        health_score=health,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_report(report: SessionReport) -> str:
    """Render SessionReport to GitHub-flavoured Markdown."""
    dur = f"{report.duration_min} min" if report.duration_min else "unknown"
    lines = [
        f"# Awake — Session {report.session} Report",
        "",
        f"**Date:** {report.date}  ",
        f"**Duration:** {dur}  ",
        f"**Health score:** {report.health_score}/100",
        "",
        "## Tests",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total | {report.test_outcome.total} |",
        f"| Passed | {report.test_outcome.passed} |",
        f"| Failed | {report.test_outcome.failed} |",
        f"| New this session | {report.test_outcome.new_tests} |",
        f"| Pass rate | {report.test_outcome.pass_rate}% |",
        "",
        "## Commits",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total | {report.commit_summary.total} |",
        f"| CC-compliant | {report.commit_summary.cc_compliant} |",
    ]
    for ctype, count in sorted(report.commit_summary.by_type.items()):
        lines.append(f"| {ctype} | {count} |")
    lines += [
        "",
        "## Refactoring",
        "",
        f"- Smells before: {report.refactor_delta.smells_before}",
        f"- Smells after : {report.refactor_delta.smells_after}",
        f"- Delta        : {report.refactor_delta.delta:+d}",
        f"- Improved     : {'yes' if report.refactor_delta.improved else 'no'}",
        "",
        "## Roadmap",
        "",
        f"- Items closed this session: {report.roadmap_items_closed}",
        "",
    ]
    if report.notes:
        lines += ["## Notes", "", report.notes, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: python -m src.report --session N [--duration M] [--notes TEXT]"""
    import sys
    args = sys.argv[1:]

    def _get_arg(flag: str, default: str = "") -> str:
        try:
            return args[args.index(flag) + 1]
        except (ValueError, IndexError):
            return default

    session = int(_get_arg("--session", "1"))
    duration = _get_arg("--duration")
    notes = _get_arg("--notes")
    repo_root = Path(__file__).resolve().parent.parent
    report = build_report(
        session=session,
        repo_root=repo_root,
        duration_min=int(duration) if duration else None,
        notes=notes,
    )
    output = render_report(report)
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    out_path = reports_dir / f"session_{report.session}.md"
    out_path.write_text(output, encoding="utf-8")
    print(f"Report written to {out_path}")
    print(f"Health score: {report.health_score}/100")


if __name__ == "__main__":
    main()
