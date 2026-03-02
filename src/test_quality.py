"""Test quality analyzer for Awake.

Grades each test file on assertion density, test isolation, naming
conventions, fixture usage, and overall coverage proxy metrics.

Public API
----------
- ``TestFileGrade``  -- grade for a single test file
- ``TestQualityReport`` -- full report
- ``grade_test_file(path, rel)`` -> ``TestFileGrade``
- ``scan_test_quality(repo_path)`` -> ``TestQualityReport``
- ``save_test_quality_report(report, out_path)``

CLI
---
    awake test-quality         # Print report to stdout
    awake test-quality --write # Write docs/test_quality_report.json
    awake test-quality --json  # Output raw JSON
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TestFileGrade:
    """Grade for a single test file."""

    file: str
    total_tests: int = 0
    assertion_count: int = 0
    assertion_density: float = 0.0   # assertions per test
    has_fixtures: bool = False
    naming_ok: bool = True            # all test funcs start with test_
    isolated: bool = True             # no global state mutations detected
    score: float = 0.0                # 0-100
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a serialisable dict."""
        return {
            "file": self.file,
            "total_tests": self.total_tests,
            "assertion_count": self.assertion_count,
            "assertion_density": round(self.assertion_density, 2),
            "has_fixtures": self.has_fixtures,
            "naming_ok": self.naming_ok,
            "isolated": self.isolated,
            "score": round(self.score, 1),
            "notes": self.notes,
        }


@dataclass
class TestQualityReport:
    """Full test quality report for a repository."""

    files_graded: int = 0
    total_tests: int = 0
    overall_score: float = 0.0
    grades: list[TestFileGrade] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a serialisable dict."""
        return {
            "files_graded": self.files_graded,
            "total_tests": self.total_tests,
            "overall_score": round(self.overall_score, 1),
            "grades": [g.to_dict() for g in self.grades],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _count_assertions(tree: ast.AST) -> int:
    """Count assert statements and self.assert* calls in an AST."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.Call):
            # self.assertEqual / self.assertTrue / etc.
            if isinstance(node.func, ast.Attribute):
                if node.func.attr.startswith("assert"):
                    count += 1
            # pytest.raises / pytest.approx used in assert
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest":
                    count += 1
    return count


def _has_fixtures(tree: ast.AST) -> bool:
    """Return True if any function uses @pytest.fixture or has a 'fixture' decorator."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Attribute) and deco.attr == "fixture":
                    return True
                if isinstance(deco, ast.Name) and deco.id == "fixture":
                    return True
                if isinstance(deco, ast.Call):
                    inner = deco.func
                    if isinstance(inner, ast.Attribute) and inner.attr == "fixture":
                        return True
    return False


def _get_test_functions(tree: ast.AST) -> list[ast.FunctionDef]:
    """Return all top-level test functions (names starting with 'test_' or 'test')."""
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                funcs.append(node)
    return funcs


def _check_naming(funcs: list[ast.FunctionDef]) -> bool:
    """Return True if all test functions follow test_ naming convention."""
    for f in funcs:
        if not f.name.startswith("test_"):
            return False
    return True


def _check_isolation(tree: ast.AST) -> bool:
    """Heuristic: return False if global variables are assigned (potential shared state)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            return False
    return True


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------


def grade_test_file(path: Path, rel: str) -> TestFileGrade:
    """Grade a single test file.

    Parameters
    ----------
    path:
        Absolute path to the test file.
    rel:
        Relative path for display.

    Returns
    -------
    TestFileGrade
    """
    grade = TestFileGrade(file=rel)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        grade.notes.append(f"Parse error: {e}")
        return grade

    funcs = _get_test_functions(tree)
    grade.total_tests = len(funcs)

    if grade.total_tests == 0:
        grade.notes.append("No test functions found.")
        grade.score = 0.0
        return grade

    grade.assertion_count = _count_assertions(tree)
    grade.assertion_density = grade.assertion_count / grade.total_tests
    grade.has_fixtures = _has_fixtures(tree)
    grade.naming_ok = _check_naming(funcs)
    grade.isolated = _check_isolation(tree)

    # Scoring heuristic (0-100)
    score = 0.0

    # Assertion density (up to 40 pts)
    density_score = min(grade.assertion_density / 3.0, 1.0) * 40
    score += density_score

    # Naming (20 pts)
    if grade.naming_ok:
        score += 20
    else:
        grade.notes.append("Some test functions do not follow test_ naming convention.")

    # Isolation (20 pts)
    if grade.isolated:
        score += 20
    else:
        grade.notes.append("Global state mutations detected -- tests may not be isolated.")

    # Fixtures (20 pts)
    if grade.has_fixtures:
        score += 20
    else:
        grade.notes.append("No pytest fixtures detected.")

    grade.score = min(score, 100.0)
    return grade


# ---------------------------------------------------------------------------
# Repository scanner
# ---------------------------------------------------------------------------


def scan_test_quality(repo_path: str | Path) -> TestQualityReport:
    """Scan all test files in the repository.

    Parameters
    ----------
    repo_path:
        Path to the repository root.

    Returns
    -------
    TestQualityReport
    """
    repo = Path(repo_path)
    test_dirs = [repo / "tests", repo / "test"]
    report = TestQualityReport()

    py_files: list[Path] = []
    for test_dir in test_dirs:
        if test_dir.exists():
            py_files.extend(sorted(test_dir.rglob("test_*.py")))
            py_files.extend(sorted(test_dir.rglob("*_test.py")))

    # Deduplicate
    seen: set[Path] = set()
    unique_files: list[Path] = []
    for f in py_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    report.files_graded = len(unique_files)

    for py_file in unique_files:
        rel = str(py_file.relative_to(repo))
        try:
            grade = grade_test_file(py_file, rel)
            report.grades.append(grade)
            report.total_tests += grade.total_tests
        except Exception as e:
            report.errors.append(f"{rel}: {e}")

    if report.grades:
        report.overall_score = sum(g.score for g in report.grades) / len(report.grades)

    return report


def save_test_quality_report(report: TestQualityReport, out_path: str | Path) -> None:
    """Save the report as JSON.

    Parameters
    ----------
    report:
        The report to save.
    out_path:
        Output file path.
    """
    Path(out_path).write_text(
        json.dumps(report.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: TestQualityReport) -> str:
    """Render the test quality report as Markdown."""
    lines = [
        "# Test Quality Report",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files graded | {report.files_graded} |",
        f"| Total tests | {report.total_tests} |",
        f"| Overall score | {report.overall_score:.1f} / 100 |",
        "",
    ]
    if report.grades:
        lines += [
            "## File Grades",
            "",
            "| File | Tests | Assertions | Density | Fixtures | Score |",
            "|------|-------|------------|---------|----------|-------|",
        ]
        for g in sorted(report.grades, key=lambda x: x.score):
            lines.append(
                f"| {g.file} | {g.total_tests} | {g.assertion_count} "
                f"| {g.assertion_density:.1f} | {'yes' if g.has_fixtures else 'no'} "
                f"| {g.score:.1f} |"
            )
        lines.append("")
    if report.errors:
        lines += ["## Errors", ""]
        for err in report.errors:
            lines.append(f"- {err}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for test quality analysis."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-test-quality")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--write", action="store_true", help="Write report to docs/")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    report = scan_test_quality(repo_path)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_markdown(report))

    if args.write:
        docs = repo_path / "docs"
        docs.mkdir(exist_ok=True)
        save_test_quality_report(report, docs / "test_quality_report.json")
        print(f"  Wrote docs/test_quality_report.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
