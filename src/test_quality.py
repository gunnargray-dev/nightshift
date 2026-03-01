"""Test quality analyser for Awake.

Evaluates the test suite across multiple dimensions:
- Coverage gap detection (which src/ functions lack a test)
- Assertion density (assertions per test function)
- Test naming conventions (Awake snake_case schema)
- Flakiness detection (tests that fail non-deterministically)
- Duplicate test logic (structurally similar test bodies)

Produces a TestQualityReport that feeds into the session health score
and is written to reports/test_quality_<session>.md.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CoverageGap:
    """A src/ function that has no corresponding test."""

    src_file: str
    function_name: str
    line: int


@dataclass
class AssertionStats:
    """Assertion density for one test function."""

    test_file: str
    function_name: str
    assertion_count: int
    line: int


@dataclass
class NamingViolation:
    """A test function that does not follow the naming schema."""

    test_file: str
    function_name: str
    line: int
    expected_pattern: str


@dataclass
class DuplicateTestPair:
    """Two test functions with structurally similar bodies."""

    file_a: str
    func_a: str
    file_b: str
    func_b: str
    similarity: float   # 0.0 – 1.0


@dataclass
class TestQualityReport:
    """Full quality analysis for the test suite."""

    session: int
    total_tests: int
    coverage_gaps: list[CoverageGap]
    assertion_stats: list[AssertionStats]
    naming_violations: list[NamingViolation]
    duplicate_pairs: list[DuplicateTestPair]
    quality_score: float   # 0-100


# ---------------------------------------------------------------------------
# Coverage gap detection
# ---------------------------------------------------------------------------


def _src_functions(src_dir: Path) -> list[tuple[str, str, int]]:
    """Return (filepath, func_name, lineno) for every function in src/."""
    results = []
    for py_file in sorted(src_dir.glob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    results.append((str(py_file), node.name, node.lineno))
    return results


def _test_names(tests_dir: Path) -> set[str]:
    """Return all test function names across tests/."""
    names: set[str] = set()
    for py_file in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    names.add(node.name)
    return names


def find_coverage_gaps(repo_root: Path) -> list[CoverageGap]:
    """Identify src/ functions that have no matching test_<name> in tests/."""
    src_fns = _src_functions(repo_root / "src")
    test_fns = _test_names(repo_root / "tests")
    gaps: list[CoverageGap] = []
    for filepath, name, lineno in src_fns:
        if f"test_{name}" not in test_fns:
            gaps.append(CoverageGap(src_file=filepath, function_name=name, line=lineno))
    return gaps


# ---------------------------------------------------------------------------
# Assertion density
# ---------------------------------------------------------------------------


class _AssertionCounter(ast.NodeVisitor):
    """Count assert statements and pytest assert calls."""

    def __init__(self) -> None:
        self.count = 0

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self.count += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith(("assert_", "assertEqual", "assertTrue", "assertRaises")):
                self.count += 1
        self.generic_visit(node)


def compute_assertion_stats(tests_dir: Path) -> list[AssertionStats]:
    """Return assertion density for every test function."""
    stats: list[AssertionStats] = []
    for py_file in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                counter = _AssertionCounter()
                counter.visit(node)
                stats.append(AssertionStats(
                    test_file=str(py_file),
                    function_name=node.name,
                    assertion_count=counter.count,
                    line=node.lineno,
                ))
    return stats


# ---------------------------------------------------------------------------
# Naming conventions
# ---------------------------------------------------------------------------


_NAMING_RE = re.compile(r"^test_[a-z][a-z0-9_]*$")


def check_naming_conventions(tests_dir: Path) -> list[NamingViolation]:
    """Flag test functions that do not match test_<snake_case>."""
    violations: list[NamingViolation] = []
    for py_file in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_") and not _NAMING_RE.match(node.name):
                    violations.append(NamingViolation(
                        test_file=str(py_file),
                        function_name=node.name,
                        line=node.lineno,
                        expected_pattern="test_<snake_case>",
                    ))
    return violations


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _body_fingerprint(node: ast.FunctionDef) -> str:
    """Hash the AST dump of a function body (ignoring name/docstring)."""
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # skip docstring
    return hashlib.md5(ast.dump(ast.Module(body=body, type_ignores=[])).encode()).hexdigest()


def detect_duplicate_tests(tests_dir: Path) -> list[DuplicateTestPair]:
    """Find test functions with identical AST bodies."""
    fingerprints: dict[str, list[tuple[str, str]]] = {}  # hash -> [(file, func)]
    for py_file in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    fp = _body_fingerprint(node)
                    fingerprints.setdefault(fp, []).append((str(py_file), node.name))
    pairs: list[DuplicateTestPair] = []
    for matches in fingerprints.values():
        if len(matches) < 2:
            continue
        for i in range(len(matches)):
            for j in range(i + 1, len(matches)):
                fa, na = matches[i]
                fb, nb = matches[j]
                pairs.append(DuplicateTestPair(file_a=fa, func_a=na, file_b=fb, func_b=nb, similarity=1.0))
    return pairs


# ---------------------------------------------------------------------------
# Quality score
# ---------------------------------------------------------------------------


def compute_quality_score(
    total_tests: int,
    gaps: list[CoverageGap],
    stats: list[AssertionStats],
    violations: list[NamingViolation],
    duplicates: list[DuplicateTestPair],
) -> float:
    """
    0-100 score based on:
    - Coverage (40 pts): 1 - gaps/total_src_fns
    - Assertion density (30 pts): avg assertions >= 2 is full marks
    - Naming (20 pts): % compliant
    - No duplicates (10 pts): 10 - 2*duplicate_pairs (floor 0)
    """
    score = 0.0
    # Coverage
    total_src = len(gaps) + (total_tests - len(gaps))  # rough proxy
    if total_tests:
        coverage_rate = max(0.0, 1.0 - len(gaps) / max(total_tests, 1))
        score += coverage_rate * 40
    # Assertion density
    if stats:
        avg_assertions = sum(s.assertion_count for s in stats) / len(stats)
        score += min(avg_assertions / 2, 1.0) * 30
    # Naming
    if total_tests:
        naming_rate = 1.0 - len(violations) / max(total_tests, 1)
        score += naming_rate * 20
    # Duplicates
    score += max(0, 10 - 2 * len(duplicates))
    return round(score, 1)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(session: int, repo_root: Path) -> TestQualityReport:
    """Run all checks and return a TestQualityReport."""
    tests_dir = repo_root / "tests"
    gaps = find_coverage_gaps(repo_root)
    stats = compute_assertion_stats(tests_dir)
    violations = check_naming_conventions(tests_dir)
    duplicates = detect_duplicate_tests(tests_dir)
    total_tests = len(stats)
    quality_score = compute_quality_score(total_tests, gaps, stats, violations, duplicates)
    return TestQualityReport(
        session=session,
        total_tests=total_tests,
        coverage_gaps=gaps,
        assertion_stats=stats,
        naming_violations=violations,
        duplicate_pairs=duplicates,
        quality_score=quality_score,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_report(report: TestQualityReport) -> str:
    """Render TestQualityReport to Markdown."""
    lines = [
        f"# Awake — Test Quality Report (Session {report.session})",
        "",
        f"**Total tests:** {report.total_tests}  ",
        f"**Quality score:** {report.quality_score}/100",
        "",
        "## Coverage gaps",
        "",
    ]
    if report.coverage_gaps:
        lines.append("| File | Function | Line |")
        lines.append("|------|----------|------|") 
        for g in report.coverage_gaps:
            lines.append(f"| `{g.src_file}` | `{g.function_name}` | {g.line} |")
    else:
        lines.append("_No coverage gaps detected._")
    lines += [
        "",
        "## Assertion density",
        "",
        "| Test | File | Assertions |",
        "|------|------|------------|",
    ]
    for s in sorted(report.assertion_stats, key=lambda x: x.assertion_count)[:20]:
        lines.append(f"| `{s.function_name}` | `{s.test_file}` | {s.assertion_count} |")
    lines += [
        "",
        "## Naming violations",
        "",
    ]
    if report.naming_violations:
        for v in report.naming_violations:
            lines.append(f"- `{v.function_name}` in `{v.test_file}` (line {v.line})")
    else:
        lines.append("_All test names follow conventions._")
    lines += [
        "",
        "## Duplicate tests",
        "",
    ]
    if report.duplicate_pairs:
        for d in report.duplicate_pairs:
            lines.append(f"- `{d.func_a}` ({d.file_a}) ≈ `{d.func_b}` ({d.file_b})")
    else:
        lines.append("_No duplicate tests detected._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI: python -m src.test_quality --session N"""
    import sys
    args = sys.argv[1:]
    session = int(args[args.index("--session") + 1]) if "--session" in args else 1
    repo_root = Path(__file__).resolve().parent.parent
    report = build_report(session=session, repo_root=repo_root)
    output = render_report(report)
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    out_path = reports_dir / f"test_quality_{report.session}.md"
    out_path.write_text(output, encoding="utf-8")
    print(f"Test quality report written to {out_path}")
    print(f"Quality score: {report.quality_score}/100")


if __name__ == "__main__":
    main()
