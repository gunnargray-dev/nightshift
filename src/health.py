"""Code health monitor for Awake.

Analyzes the repository's source code for quality metrics:
- Lines of code and file counts
- Complexity indicators (long files, large functions)
- TODO / FIXME / HACK comment density
- Test coverage ratio (estimated from test file presence)
- Import hygiene (stdlib vs third-party vs local)

CLI: awake health [--json] [--threshold N]
API: GET /api/health
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLD = 70          # health score below which a warning is emitted
MAX_FILE_LINES = 400            # files over this are flagged as too long
MAX_FUNCTION_LINES = 60         # functions over this are flagged as complex
SRC_EXTENSIONS = {".py"}        # source file extensions to analyze
EXCLUDE_DIRS = {                # directories to skip
    "__pycache__", ".git", ".awake", ".venv", "venv", "env",
    "node_modules", "dist", "build", ".tox",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileHealthRecord:
    """Health metrics for a single source file."""

    path: str
    lines: int
    functions: int
    classes: int
    long_functions: int         # functions exceeding MAX_FUNCTION_LINES
    todo_count: int             # TODO / FIXME / HACK comments
    has_test: bool              # True if a corresponding test file exists
    complexity_flag: bool       # True if file exceeds MAX_FILE_LINES


@dataclass
class HealthReport:
    """Aggregate health report for the repository."""

    score: int                  # 0–100
    grade: str                  # A / B / C / D / F
    total_files: int
    total_lines: int
    total_functions: int
    total_classes: int
    long_files: int
    long_functions: int
    todo_density: float         # TODOs per 100 lines
    test_coverage_ratio: float  # fraction of src files with a test file
    file_records: List[FileHealthRecord]
    top_issues: List[str]
    summary: str


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _discover_python_files(root: Path) -> list[Path]:
    """Recursively discover Python source files, skipping excluded dirs."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix in SRC_EXTENSIONS:
                found.append(p)
    return sorted(found)


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

_TODO_RE = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)", re.IGNORECASE)


def _analyze_file(path: Path, root: Path) -> Optional[FileHealthRecord]:
    """Analyze a single Python file. Returns None if the file cannot be parsed."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = source.splitlines()
    line_count = len(lines)
    todo_count = sum(1 for ln in lines if _TODO_RE.search(ln))

    # AST-based analysis
    functions = 0
    classes = 0
    long_functions = 0
    try:
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions += 1
                if hasattr(node, "end_lineno") and node.end_lineno:
                    fn_lines = node.end_lineno - node.lineno
                    if fn_lines > MAX_FUNCTION_LINES:
                        long_functions += 1
            elif isinstance(node, ast.ClassDef):
                classes += 1
    except SyntaxError:
        pass

    # Test file heuristic: look for tests/test_<stem>.py or test_<stem>.py
    rel = path.relative_to(root)
    stem = path.stem
    test_candidates = [
        root / "tests" / f"test_{stem}.py",
        root / "test" / f"test_{stem}.py",
        path.parent / f"test_{stem}.py",
    ]
    has_test = any(c.exists() for c in test_candidates)

    return FileHealthRecord(
        path=str(rel),
        lines=line_count,
        functions=functions,
        classes=classes,
        long_functions=long_functions,
        todo_count=todo_count,
        has_test=has_test,
        complexity_flag=line_count > MAX_FILE_LINES,
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _compute_score(records: list[FileHealthRecord]) -> int:
    """Compute a 0-100 health score from aggregate file metrics."""
    if not records:
        return 100

    total = len(records)

    # Component scores (each 0-100, weighted)
    # 1. Long-file ratio (lower = better)
    long_file_ratio = sum(1 for r in records if r.complexity_flag) / total
    long_file_score = max(0, 100 - int(long_file_ratio * 150))

    # 2. Long-function ratio
    total_fns = sum(r.functions for r in records) or 1
    long_fn_ratio = sum(r.long_functions for r in records) / total_fns
    long_fn_score = max(0, 100 - int(long_fn_ratio * 200))

    # 3. TODO density (per 100 lines)
    total_lines = sum(r.lines for r in records) or 1
    todo_density = (sum(r.todo_count for r in records) / total_lines) * 100
    todo_score = max(0, 100 - int(todo_density * 15))

    # 4. Test coverage ratio
    coverage_ratio = sum(1 for r in records if r.has_test) / total
    coverage_score = int(coverage_ratio * 100)

    # Weighted average
    score = int(
        long_file_score * 0.25
        + long_fn_score * 0.30
        + todo_score * 0.15
        + coverage_score * 0.30
    )
    return max(0, min(100, score))


def _grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def generate_health_report(
    root: Optional[Path] = None,
    threshold: int = DEFAULT_THRESHOLD,
) -> HealthReport:
    """Generate a code health report for the repository at *root*."""
    root = root or Path.cwd()
    files = _discover_python_files(root)

    records: list[FileHealthRecord] = []
    for f in files:
        rec = _analyze_file(f, root)
        if rec is not None:
            records.append(rec)

    total_lines = sum(r.lines for r in records)
    total_fns = sum(r.functions for r in records)
    total_cls = sum(r.classes for r in records)
    long_files = sum(1 for r in records if r.complexity_flag)
    long_fns = sum(r.long_functions for r in records)
    total_todos = sum(r.todo_count for r in records)
    todo_density = (total_todos / total_lines * 100) if total_lines else 0.0
    coverage_ratio = (
        sum(1 for r in records if r.has_test) / len(records)
        if records else 0.0
    )

    score = _compute_score(records)
    grade = _grade(score)

    # Build top issues list
    top_issues: list[str] = []
    if long_files:
        worst = sorted(records, key=lambda r: r.lines, reverse=True)[:3]
        for r in worst:
            if r.complexity_flag:
                top_issues.append(f"Long file ({r.lines} lines): {r.path}")
    if long_fns > 0:
        top_issues.append(f"{long_fns} function(s) exceed {MAX_FUNCTION_LINES} lines")
    if todo_density > 1.0:
        top_issues.append(f"High TODO density: {todo_density:.1f} per 100 lines")
    if coverage_ratio < 0.5:
        top_issues.append(
            f"Low test coverage: {coverage_ratio:.0%} of files have a test file"
        )
    if score < threshold:
        top_issues.append(
            f"Health score {score} is below threshold {threshold} — review required"
        )

    summary = (
        f"Score {score}/100 (Grade {grade}). "
        f"{len(records)} files, {total_lines} lines. "
        f"{long_files} long files, {long_fns} long functions. "
        f"TODO density {todo_density:.1f}/100 lines. "
        f"Test coverage ~{coverage_ratio:.0%}."
    )

    return HealthReport(
        score=score,
        grade=grade,
        total_files=len(records),
        total_lines=total_lines,
        total_functions=total_fns,
        total_classes=total_cls,
        long_files=long_files,
        long_functions=long_fns,
        todo_density=round(todo_density, 2),
        test_coverage_ratio=round(coverage_ratio, 4),
        file_records=records,
        top_issues=top_issues,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_health_report(report: HealthReport) -> str:
    """Format a HealthReport as a human-readable string."""

    grade_style = {
        "A": "✅", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴",
    }.get(report.grade, "")

    lines = [
        "═" * 70,
        "  AWAKE — CODE HEALTH REPORT",
        "═" * 70,
        f"  Score    : {report.score}/100  Grade: {report.grade} {grade_style}",
        f"  Files    : {report.total_files}  Lines: {report.total_lines}",
        f"  Functions: {report.total_functions}  Classes: {report.total_classes}",
        f"  Long files   : {report.long_files}  Long functions: {report.long_functions}",
        f"  TODO density : {report.todo_density}/100 lines",
        f"  Test coverage: {report.test_coverage_ratio:.0%}",
        f"  Summary  : {report.summary}",
        "",
    ]

    if report.top_issues:
        lines += [
            "─" * 70,
            "  TOP ISSUES",
            "─" * 70,
        ]
        for issue in report.top_issues:
            lines.append(f"  ⚠  {issue}")
        lines.append("")

    if report.file_records:
        lines += [
            "─" * 70,
            "  FILE BREAKDOWN (sorted by lines desc)",
            "─" * 70,
        ]
        sorted_records = sorted(report.file_records, key=lambda r: r.lines, reverse=True)
        for r in sorted_records[:20]:
            flags = []
            if r.complexity_flag:
                flags.append("LONG")
            if r.long_functions:
                flags.append(f"{r.long_functions}×complex-fn")
            if r.todo_count:
                flags.append(f"{r.todo_count}×TODO")
            if not r.has_test:
                flags.append("no-test")
            flag_str = "  [" + ", ".join(flags) + "]" if flags else ""
            lines.append(
                f"  {r.lines:>5}  {r.functions:>3}fn  {r.classes:>2}cls  "
                f"{r.path}{flag_str}"
            )
        lines.append("")

    lines.append("═" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(args=None) -> int:
    """CLI entry point for `awake health`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="awake health",
        description="Analyze repository code health",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD,
        help=f"Score threshold for warnings (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--root", type=str, default=None,
        help="Repository root path (default: cwd)",
    )

    parsed = parser.parse_args(args)
    root = Path(parsed.root) if parsed.root else None

    report = generate_health_report(root=root, threshold=parsed.threshold)

    if parsed.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_health_report(report))

    return 0 if report.score >= parsed.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
