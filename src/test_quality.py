"""Test quality analyzer for Nightshift.

Grades each test file on assertion density, edge case coverage, mock usage,
and structural best practices.

CLI
---
    nightshift test-quality             # Show test quality report
    nightshift test-quality --json      # Emit JSON
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class TestFileScore:
    file: str
    module: str
    score: float = 0.0
    grade: str = ""
    test_count: int = 0
    assertion_count: int = 0
    assertion_density: float = 0.0
    mock_usage_count: int = 0
    parametrize_count: int = 0
    edge_case_markers: int = 0
    docstring_count: int = 0
    fixture_count: int = 0
    setup_present: bool = False
    teardown_present: bool = False
    issues: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TestQualityReport:
    repo_path: str
    total_test_files: int = 0
    total_tests: int = 0
    total_assertions: int = 0
    avg_score: float = 0.0
    overall_grade: str = ""
    files: list[TestFileScore] = field(default_factory=list)
    missing_test_files: list[str] = field(default_factory=list)
    excellent_files: list[str] = field(default_factory=list)
    weak_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [
            "## Test Quality Analysis", "",
            "| Metric | Value |", "|--------|-------|" ,
            f"| Test files analysed | **{self.total_test_files}** |",
            f"| Total tests | **{self.total_tests}** |",
            f"| Total assertions | **{self.total_assertions}** |",
            f"| Avg assertions/test | **{self.total_assertions / max(1, self.total_tests):.1f}** |",
            f"| Avg file score | **{self.avg_score:.1f}/100** |",
            f"| Overall grade | **{self.overall_grade}** |",
            "",
        ]
        if self.weak_files:
            lines += ["### Weakest Test Files", ""]
            for f in self.weak_files[:5]:
                lines.append(f"- `{f}`")
            lines.append("")
        if self.excellent_files:
            lines += ["### Excellent Test Files", ""]
            for f in self.excellent_files[:5]:
                lines.append(f"- `{f}`")
            lines.append("")
        lines += [
            "### Per-File Scores", "",
            "| File | Score | Grade | Tests | Asserts | Density |",
            "|------|-------|-------|-------|---------|---------|" ,
        ]
        for fs in sorted(self.files, key=lambda f: -f.score):
            lines.append(f"| `{fs.file}` | {fs.score:.0f} | {fs.grade} | {fs.test_count} | {fs.assertion_count} | {fs.assertion_density:.1f} |")
        return "\n".join(lines)


_ASSERT_FUNCTIONS = {
    "assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
    "assertIs", "assertIsNot", "assertIsNone", "assertIsNotNone",
    "assertIn", "assertNotIn", "assertIsInstance", "assertRaises",
    "assertRaisesRegex", "assertAlmostEqual", "assertGreater",
    "assertGreaterEqual", "assertLess", "assertLessEqual",
    "assertRegex", "assertCountEqual", "assertDictEqual", "fail", "approx",
}

_EDGE_CASE_WORDS = {
    "empty", "none", "null", "zero", "negative", "overflow", "boundary",
    "edge", "invalid", "error", "exception", "fail", "timeout", "large",
    "unicode", "special", "malformed",
}


class _TestFileVisitor(ast.NodeVisitor):
    def __init__(self):
        self.test_count = 0
        self.assertion_count = 0
        self.mock_usage = 0
        self.parametrize_count = 0
        self.edge_case_markers = 0
        self.docstring_count = 0
        self.fixture_count = 0
        self.setup_present = False
        self.teardown_present = False
        self._has_mock_import = False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if "mock" in alias.name.lower():
                self._has_mock_import = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and ("mock" in node.module.lower() or "pytest" in node.module.lower()):
            self._has_mock_import = True
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        name = node.name.lower()
        if name.startswith("test_"):
            self.test_count += 1
            if ast.get_docstring(node):
                self.docstring_count += 1
            words = set(re.split(r"[_\s]+", name))
            if words & _EDGE_CASE_WORDS:
                self.edge_case_markers += 1
        if name in ("setup", "setup_method"):
            self.setup_present = True
        if name in ("teardown", "teardown_method"):
            self.teardown_present = True
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and dec.attr == "parametrize":
                self.parametrize_count += 1
            elif isinstance(dec, ast.Name) and dec.id == "parametrize":
                self.parametrize_count += 1
            elif isinstance(dec, ast.Attribute) and "fixture" in dec.attr.lower():
                self.fixture_count += 1
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assert(self, node: ast.Assert) -> None:
        self.assertion_count += 1
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in _ASSERT_FUNCTIONS:
                self.assertion_count += 1
            if node.func.attr in ("patch", "MagicMock", "Mock", "AsyncMock"):
                self.mock_usage += 1
        elif isinstance(node.func, ast.Name):
            if node.func.id in _ASSERT_FUNCTIONS:
                self.assertion_count += 1
            if node.func.id in ("patch", "MagicMock", "Mock", "AsyncMock"):
                self.mock_usage += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call):
                if isinstance(ctx.func, ast.Attribute) and ctx.func.attr in ("raises", "warns"):
                    self.assertion_count += 1
                elif isinstance(ctx.func, ast.Name) and ctx.func.id in ("raises", "warns"):
                    self.assertion_count += 1
        self.generic_visit(node)


def _grade(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 85: return "A-"
    if score >= 80: return "B+"
    if score >= 75: return "B"
    if score >= 70: return "B-"
    if score >= 65: return "C+"
    if score >= 60: return "C"
    if score >= 50: return "C-"
    if score >= 40: return "D"
    return "F"


def _score_test_file(path: Path, module_name: str) -> TestFileScore:
    fs = TestFileScore(file=path.name, module=module_name)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        fs.issues.append("could not parse")
        return fs
    visitor = _TestFileVisitor()
    visitor.visit(tree)
    fs.test_count = visitor.test_count
    fs.assertion_count = visitor.assertion_count
    fs.mock_usage_count = visitor.mock_usage + (1 if visitor._has_mock_import else 0)
    fs.parametrize_count = visitor.parametrize_count
    fs.edge_case_markers = visitor.edge_case_markers
    fs.docstring_count = visitor.docstring_count
    fs.fixture_count = visitor.fixture_count
    fs.setup_present = visitor.setup_present
    fs.teardown_present = visitor.teardown_present
    if fs.test_count > 0:
        fs.assertion_density = fs.assertion_count / fs.test_count
    score = 30.0
    if fs.test_count == 0:
        score -= 20
        fs.issues.append("no tests defined")
    elif fs.test_count < 3:
        score += 5
        fs.issues.append("very few tests")
    elif fs.test_count < 8:
        score += 12
    else:
        score += 20
        fs.highlights.append(f"{fs.test_count} tests")
    if fs.assertion_density == 0:
        score -= 10
        fs.issues.append("no assertions")
    elif fs.assertion_density < 1:
        score += 5
        fs.issues.append("low assertion density")
    elif fs.assertion_density < 2:
        score += 10
    elif fs.assertion_density < 4:
        score += 15
    else:
        score += 20
        fs.highlights.append(f"{fs.assertion_density:.1f} asserts/test")
    if fs.edge_case_markers == 0:
        fs.issues.append("no edge case tests")
    elif fs.edge_case_markers < 2:
        score += 5
    else:
        score += 10
        fs.highlights.append(f"{fs.edge_case_markers} edge cases")
    if fs.parametrize_count > 0:
        score += 10
        fs.highlights.append(f"{fs.parametrize_count} parametrized")
    if fs.docstring_count > 0:
        score += 5
        fs.highlights.append("documented")
    if 0 < fs.mock_usage_count <= 5:
        score += 5
    elif fs.mock_usage_count > 10:
        fs.issues.append("heavy mock usage")
    score = max(0.0, min(100.0, score))
    fs.score = round(score, 1)
    fs.grade = _grade(score)
    return fs


def analyze_test_quality(repo_root: Path) -> TestQualityReport:
    """Analyse all test files and produce a quality report."""
    tests_dir = repo_root / "tests"
    src_dir = repo_root / "src"
    report = TestQualityReport(repo_path=str(repo_root))
    if not tests_dir.exists():
        return report
    test_files = sorted(tests_dir.glob("test_*.py"))
    src_modules = {p.stem for p in src_dir.glob("*.py") if p.stem != "__init__"} if src_dir.exists() else set()
    covered_modules: set = set()
    file_scores: list[TestFileScore] = []
    for tf in test_files:
        mod = tf.stem.replace("test_", "", 1)
        covered_modules.add(mod)
        fs = _score_test_file(tf, mod)
        file_scores.append(fs)
    report.missing_test_files = sorted(src_modules - covered_modules - {"__init__", "cli", "server"})
    report.files = file_scores
    report.total_test_files = len(file_scores)
    report.total_tests = sum(f.test_count for f in file_scores)
    report.total_assertions = sum(f.assertion_count for f in file_scores)
    report.avg_score = sum(f.score for f in file_scores) / len(file_scores) if file_scores else 0.0
    report.overall_grade = _grade(report.avg_score)
    sorted_files = sorted(file_scores, key=lambda f: f.score)
    report.weak_files = [f.file for f in sorted_files[:5] if f.score < 60]
    report.excellent_files = [f.file for f in sorted_files if f.score >= 85]
    return report
