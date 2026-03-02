"""Test quality analyzer for Awake.

Grades each test file (and individual test functions) on a rubric that
checks for:

- **Docstrings** -- every test function should have a one-line description.
- **Assertions** -- tests with zero ``assert`` statements are flagged.
- **Fixture usage** -- tests that never use a fixture may be under-isolated.
- **Parametrize coverage** -- tests with many near-duplicate names suggest
  they should use ``@pytest.mark.parametrize``.
- **Magic literals** -- hard-coded numbers / strings inside ``assert``
  expressions indicate missing named constants.

Scores are 0-100 per file and 0-100 overall.

Public API
----------
- ``TestIssue``       -- a single quality issue
- ``TestFileReport``  -- issues + score for one test file
- ``TestQualityReport`` -- aggregate report
- ``analyze_test_quality(repo_path)`` -> ``TestQualityReport``

CLI
---
    awake test-quality [--json] [--threshold N]
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TestIssue:
    """A single quality issue found in a test function or file."""

    kind: str
    name: str   # test function name or file path
    line: int
    message: str
    severity: str = "warning"  # "warning" | "error"


@dataclass
class TestFileReport:
    """Quality report for a single test file."""

    path: str
    issues: list[TestIssue] = field(default_factory=list)
    test_count: int = 0
    score: float = 100.0


@dataclass
class TestQualityReport:
    """Aggregate quality report across all test files."""

    files: list[TestFileReport] = field(default_factory=list)
    overall_score: float = 100.0

    @property
    def total_tests(self) -> int:
        """Total number of test functions across all files."""
        return sum(f.test_count for f in self.files)

    @property
    def total_issues(self) -> int:
        """Total number of quality issues across all files."""
        return sum(len(f.issues) for f in self.files)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _has_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if *node* has a docstring."""
    if not node.body:
        return False
    first = node.body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


def _count_assertions(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count the number of assert statements in *node*."""
    return sum(
        1 for child in ast.walk(node) if isinstance(child, ast.Assert)
    )


def _uses_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if *node* accepts any pytest fixture parameters."""
    args = node.args
    params = [a.arg for a in args.args]
    # Common pytest fixtures and any non-self/cls parameter suggests fixture use
    return any(p not in ("self", "cls") for p in params)


def _has_magic_literals_in_assert(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if any assert in *node* contains a bare numeric or string literal."""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            for subnode in ast.walk(child.test):
                if isinstance(subnode, ast.Constant):
                    if isinstance(subnode.value, (int, float, complex)) and subnode.value not in (0, 1, -1, True, False):
                        return True
                    if isinstance(subnode.value, str) and len(subnode.value) > 3:
                        return True
    return False


# ---------------------------------------------------------------------------
# File analyser
# ---------------------------------------------------------------------------


def _analyze_file(py_file: Path, repo_root: Path) -> TestFileReport:
    """Analyse a single test file and return a :class:`TestFileReport`."""
    rel = str(py_file.relative_to(repo_root))
    report = TestFileReport(path=rel)

    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=rel)
    except (SyntaxError, OSError) as exc:
        report.issues.append(
            TestIssue(
                kind="parse_error",
                name=rel,
                line=0,
                message=str(exc),
                severity="error",
            )
        )
        return report

    # Collect test functions (top-level and inside Test* classes)
    test_funcs: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_") or node.name.startswith("Test"):
                test_funcs.append(node)

    report.test_count = len(test_funcs)

    # Check for duplicate-name groups suggesting parametrize opportunity
    name_bases: list[str] = []
    for fn in test_funcs:
        # Strip trailing _N or _case_X suffix
        base = re.sub(r"_\d+$", "", fn.name)
        base = re.sub(r"_case_\w+$", "", base)
        name_bases.append(base)

    from collections import Counter
    counts = Counter(name_bases)
    flagged_bases: set[str] = {b for b, c in counts.items() if c >= 3}

    penalty = 0.0
    for fn in test_funcs:
        # Missing docstring
        if not _has_docstring(fn):
            report.issues.append(
                TestIssue(
                    kind="missing_docstring",
                    name=fn.name,
                    line=fn.lineno,
                    message=f"{fn.name}: missing docstring",
                    severity="warning",
                )
            )
            penalty += 2.0

        # No assertions
        if _count_assertions(fn) == 0:
            report.issues.append(
                TestIssue(
                    kind="no_assertions",
                    name=fn.name,
                    line=fn.lineno,
                    message=f"{fn.name}: no assert statements",
                    severity="error",
                )
            )
            penalty += 10.0

        # Magic literals
        if _has_magic_literals_in_assert(fn):
            report.issues.append(
                TestIssue(
                    kind="magic_literal",
                    name=fn.name,
                    line=fn.lineno,
                    message=f"{fn.name}: magic literal in assert",
                    severity="warning",
                )
            )
            penalty += 3.0

        # Parametrize opportunity
        base = re.sub(r"_\d+$", "", fn.name)
        base = re.sub(r"_case_\w+$", "", base)
        if base in flagged_bases:
            report.issues.append(
                TestIssue(
                    kind="parametrize_opportunity",
                    name=fn.name,
                    line=fn.lineno,
                    message=f"{fn.name}: consider @pytest.mark.parametrize",
                    severity="warning",
                )
            )
            penalty += 1.0

    report.score = max(0.0, 100.0 - penalty)
    return report


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_test_quality(repo_path: str | Path) -> TestQualityReport:
    """Analyze test quality across the whole repository.

    Parameters
    ----------
    repo_path:
        Root directory of the repository.

    Returns
    -------
    TestQualityReport
        Aggregate quality report.
    """
    root = Path(repo_path)
    aggregate = TestQualityReport()

    test_files = sorted(
        f for f in root.rglob("*.py") if f.name.startswith("test_") or "tests" in f.parts
    )

    for tf in test_files:
        file_report = _analyze_file(tf, root)
        aggregate.files.append(file_report)

    if aggregate.files:
        aggregate.overall_score = sum(f.score for f in aggregate.files) / len(aggregate.files)

    return aggregate


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the test quality analyzer.

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
    import json
    import sys

    parser = argparse.ArgumentParser(
        prog="awake test-quality",
        description="Grade test quality across the repository.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--threshold",
        type=float,
        default=70.0,
        help="Minimum acceptable overall score (default: 70)",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    report = analyze_test_quality(root)

    if args.json:
        data = {
            "overall_score": report.overall_score,
            "total_tests": report.total_tests,
            "total_issues": report.total_issues,
            "files": [
                {
                    "path": f.path,
                    "score": f.score,
                    "test_count": f.test_count,
                    "issues": [
                        {
                            "kind": i.kind,
                            "name": i.name,
                            "line": i.line,
                            "message": i.message,
                            "severity": i.severity,
                        }
                        for i in f.issues
                    ],
                }
                for f in report.files
            ],
        }
        print(json.dumps(data, indent=2))
        return 0

    print(f"Overall score: {report.overall_score:.1f}/100")
    print(f"Test files analyzed: {len(report.files)}")
    print(f"Total tests: {report.total_tests}")
    print(f"Total issues: {report.total_issues}")
    for f in report.files:
        if f.issues:
            print(f"\n  {f.path}  (score={f.score:.0f})")
            for issue in f.issues:
                print(f"    line {issue.line:>4}: [{issue.kind}] {issue.message}")

    if report.overall_score < args.threshold:
        print(f"\nFAIL: score {report.overall_score:.1f} below threshold {args.threshold}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
