"""Test quality analysis utilities for awake."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TestFileReport:
    """Quality report for a single test file."""

    path: str
    test_count: int
    assertion_count: int
    parametrize_count: int
    fixture_count: int
    missing_docstrings: list[str] = field(default_factory=list)
    long_tests: list[str] = field(default_factory=list)
    parse_error: bool = False

    @property
    def avg_assertions_per_test(self) -> float:
        if self.test_count == 0:
            return 0.0
        return round(self.assertion_count / self.test_count, 2)


@dataclass
class SuiteReport:
    """Aggregate quality report for a test suite."""

    files: list[TestFileReport] = field(default_factory=list)

    @property
    def total_tests(self) -> int:
        return sum(f.test_count for f in self.files)

    @property
    def total_assertions(self) -> int:
        return sum(f.assertion_count for f in self.files)

    @property
    def files_with_errors(self) -> list[str]:
        return [f.path for f in self.files if f.parse_error]


# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------


def _is_test_function(node: ast.FunctionDef) -> bool:
    return node.name.startswith("test_")


def _count_assertions(func_node: ast.FunctionDef) -> int:
    """Count assert statements and common assertion calls."""
    count = 0
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.Call):
            # pytest.raises, unittest assert* methods
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "raises",
                "warns",
                "approx",
            ):
                count += 1
            elif isinstance(func, ast.Name) and func.id.startswith("assert"):
                count += 1
    return count


def _has_docstring(node) -> bool:
    return (
        bool(node.body)
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    )


def _count_lines(node: ast.FunctionDef, source_lines: list[str]) -> int:
    return (node.end_lineno or node.lineno) - node.lineno + 1


def analyze_test_file(
    path: str,
    *,
    long_test_threshold: int = 50,
) -> TestFileReport:
    """
    Analyze a single pytest-style test file.

    Args:
        path: Path to the test .py file.
        long_test_threshold: Number of lines above which a test is flagged as long.

    Returns:
        A TestFileReport.
    """
    source = Path(path).read_text(encoding="utf-8")
    source_lines = source.splitlines()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return TestFileReport(
            path=path,
            test_count=0,
            assertion_count=0,
            parametrize_count=0,
            fixture_count=0,
            parse_error=True,
        )

    test_count = 0
    assertion_count = 0
    parametrize_count = 0
    fixture_count = 0
    missing_docstrings: list[str] = []
    long_tests: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Fixture detection
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                    fixture_count += 1
                elif isinstance(decorator, ast.Name) and decorator.id == "fixture":
                    fixture_count += 1
                elif isinstance(decorator, ast.Call):
                    df = decorator.func
                    if (
                        isinstance(df, ast.Attribute) and df.attr == "parametrize"
                    ) or (
                        isinstance(df, ast.Name) and df.id == "parametrize"
                    ):
                        parametrize_count += 1

            if not _is_test_function(node):
                continue

            test_count += 1
            assertion_count += _count_assertions(node)

            if not _has_docstring(node):
                missing_docstrings.append(node.name)

            if _count_lines(node, source_lines) > long_test_threshold:
                long_tests.append(node.name)

    return TestFileReport(
        path=path,
        test_count=test_count,
        assertion_count=assertion_count,
        parametrize_count=parametrize_count,
        fixture_count=fixture_count,
        missing_docstrings=missing_docstrings,
        long_tests=long_tests,
    )


def analyze_test_suite(
    directory: str,
    *,
    pattern: str = "test_*.py",
    long_test_threshold: int = 50,
) -> SuiteReport:
    """
    Analyze all test files matching a glob pattern in a directory.

    Args:
        directory: Root directory to search.
        pattern: Glob pattern for test files.
        long_test_threshold: Passed through to analyze_test_file.

    Returns:
        A SuiteReport.
    """
    reports = [
        analyze_test_file(str(p), long_test_threshold=long_test_threshold)
        for p in sorted(Path(directory).rglob(pattern))
    ]
    return SuiteReport(files=reports)


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


def render_report(report: SuiteReport) -> str:
    """
    Render a SuiteReport as a human-readable text summary.

    Args:
        report: The suite report to render.

    Returns:
        A formatted string.
    """
    lines = [
        "Test Quality Report",
        "===================",
        f"Files analyzed : {len(report.files)}",
        f"Total tests    : {report.total_tests}",
        f"Total asserts  : {report.total_assertions}",
        "",
    ]
    for fr in report.files:
        status = "[PARSE ERROR]" if fr.parse_error else ""
        lines.append(f"  {fr.path} {status}")
        if not fr.parse_error:
            lines.append(f"    tests={fr.test_count}  asserts={fr.assertion_count}  fixtures={fr.fixture_count}")
            if fr.missing_docstrings:
                lines.append(f"    missing docstrings: {', '.join(fr.missing_docstrings)}")
            if fr.long_tests:
                lines.append(f"    long tests (>{50} lines): {', '.join(fr.long_tests)}")
    if report.files_with_errors:
        lines.append("")
        lines.append("Files with parse errors:")
        for f in report.files_with_errors:
            lines.append(f"  {f}")
    return "\n".join(lines) + "\n"
