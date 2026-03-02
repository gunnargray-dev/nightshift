"""Tests for src/complexity.py — Cyclomatic complexity analyser.

All tests are self-contained and do not require a real git repository.
Temporary Python source files are written to pytest's ``tmp_path`` fixture.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.complexity import (
    FunctionComplexity,
    ComplexityReport,
    analyze_complexity,
    save_complexity_report,
    _rank,
    _parse_file,
    _analyse_tree,
    _ComplexityVisitor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_src(tmp_path: Path, filename: str, source: str) -> Path:
    """Write *source* to ``<tmp_path>/src/<filename>`` and return the Path."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    py_file = src_dir / filename
    py_file.write_text(source, encoding="utf-8")
    return py_file


def _complexity_of(source: str, func_name: str | None = None) -> int:
    """Parse *source*, return complexity of the first (or named) function."""
    tree = ast.parse(source)
    results = _analyse_tree(tree, rel_path="test.py")
    if not results:
        raise ValueError("No functions found in source")
    if func_name is not None:
        for r in results:
            if r.function == func_name:
                return r.complexity
        raise ValueError(f"Function {func_name!r} not found")
    return results[0].complexity


# ---------------------------------------------------------------------------
# _rank helper
# ---------------------------------------------------------------------------


class TestRank:
    def test_low_at_1(self):
        assert _rank(1) == "LOW"

    def test_low_at_5(self):
        assert _rank(5) == "LOW"

    def test_medium_at_6(self):
        assert _rank(6) == "MEDIUM"

    def test_medium_at_14(self):
        assert _rank(14) == "MEDIUM"

    def test_high_at_15(self):
        assert _rank(15) == "HIGH"

    def test_high_at_100(self):
        assert _rank(100) == "HIGH"


# ---------------------------------------------------------------------------
# FunctionComplexity dataclass
# ---------------------------------------------------------------------------


class TestFunctionComplexity:
    def _make(self, complexity: int = 3) -> FunctionComplexity:
        return FunctionComplexity(
            function="my_func",
            file="src/mod.py",
            line=10,
            complexity=complexity,
            rank=_rank(complexity),
        )

    def test_to_dict_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {"function", "file", "line", "complexity", "rank"}

    def test_to_dict_values(self):
        fc = self._make(complexity=7)
        d = fc.to_dict()
        assert d["function"] == "my_func"
        assert d["complexity"] == 7
        assert d["rank"] == "MEDIUM"


# ---------------------------------------------------------------------------
# Complexity counting — individual decision-point nodes
# ---------------------------------------------------------------------------


class TestComplexityCounting:
    def test_simple_function_is_one(self):
        src = "def simple():\n    return 42\n"
        assert _complexity_of(src) == 1

    def test_if_adds_one(self):
        src = "def f(x):\n    if x:\n        pass\n"
        assert _complexity_of(src) == 2

    def test_elif_adds_one_each(self):
        src = (
            "def f(x):\n"
            "    if x == 1:\n"
            "        pass\n"
            "    elif x == 2:\n"
            "        pass\n"
            "    elif x == 3:\n"
            "        pass\n"
        )
        # if + elif + elif = 3 branches, base 1 → 4
        assert _complexity_of(src) == 4

    def test_for_loop_adds_one(self):
        src = "def f(items):\n    for i in items:\n        pass\n"
        assert _complexity_of(src) == 2

    def test_while_loop_adds_one(self):
        src = "def f():\n    while True:\n        break\n"
        assert _complexity_of(src) == 2

    def test_except_handler_adds_one(self):
        src = (
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
        )
        assert _complexity_of(src) == 2

    def test_two_except_handlers_add_two(self):
        src = (
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
            "    except TypeError:\n"
            "        pass\n"
        )
        assert _complexity_of(src) == 3

    def test_with_statement_adds_one(self):
        src = "def f():\n    with open('x') as fh:\n        pass\n"
        assert _complexity_of(src) == 2

    def test_assert_adds_one(self):
        src = "def f(x):\n    assert x > 0\n"
        assert _complexity_of(src) == 2

    def test_and_operator_adds_one(self):
        # a and b → 1 extra branch
        src = "def f(a, b):\n    return a and b\n"
        assert _complexity_of(src) == 2

    def test_or_operator_adds_one(self):
        src = "def f(a, b):\n    return a or b\n"
        assert _complexity_of(src) == 2

    def test_three_operand_and_adds_two(self):
        # a and b and c → 2 extra branches
        src = "def f(a, b, c):\n    return a and b and c\n"
        assert _complexity_of(src) == 3

    def test_list_comprehension_adds_one(self):
        src = "def f(items):\n    return [x for x in items]\n"
        assert _complexity_of(src) == 2

    def test_dict_comprehension_adds_one(self):
        src = "def f(items):\n    return {k: v for k, v in items}\n"
        assert _complexity_of(src) == 2

    def test_set_comprehension_adds_one(self):
        src = "def f(items):\n    return {x for x in items}\n"
        assert _complexity_of(src) == 2

    def test_generator_expression_adds_one(self):
        src = "def f(items):\n    return sum(x for x in items)\n"
        assert _complexity_of(src) == 2

    def test_ternary_expression_adds_one(self):
        src = "def f(x):\n    return 'yes' if x else 'no'\n"
        assert _complexity_of(src) == 2

    def test_nested_if_and_loop(self):
        src = (
            "def f(items):\n"
            "    for item in items:\n"
            "        if item > 0:\n"
            "            pass\n"
        )
        # base 1 + for + if = 3
        assert _complexity_of(src) == 3

    def test_nested_functions_not_counted_in_outer(self):
        src = (
            "def outer():\n"
            "    def inner():\n"
            "        if True:\n"
            "            pass\n"
            "    return inner\n"
        )
        tree = ast.parse(src)
        results = _analyse_tree(tree, "f.py")
        outer = next(r for r in results if r.function == "outer")
        inner = next(r for r in results if r.function == "inner")
        # outer should not count inner's if
        assert outer.complexity == 1
        # inner has its own if
        assert inner.complexity == 2

    def test_multiple_functions_in_file(self):
        src = (
            "def simple():\n"
            "    return 1\n"
            "\n"
            "def with_if(x):\n"
            "    if x:\n"
            "        return x\n"
            "    return 0\n"
        )
        tree = ast.parse(src)
        results = _analyse_tree(tree, "f.py")
        assert len(results) == 2
        by_name = {r.function: r for r in results}
        assert by_name["simple"].complexity == 1
        assert by_name["with_if"].complexity == 2


# ---------------------------------------------------------------------------
# ComplexityReport properties
# ---------------------------------------------------------------------------


class TestComplexityReportProperties:
    def _make_report(self) -> ComplexityReport:
        rpt = ComplexityReport(repo_path="/tmp/repo", files_scanned=3)
        rpt.results = [
            FunctionComplexity("a", "src/a.py", 1, 2, "LOW"),
            FunctionComplexity("b", "src/a.py", 5, 8, "MEDIUM"),
            FunctionComplexity("c", "src/b.py", 1, 20, "HIGH"),
            FunctionComplexity("d", "src/b.py", 10, 4, "LOW"),
        ]
        return rpt

    def test_total_functions(self):
        assert self._make_report().total_functions == 4

    def test_high_count(self):
        assert self._make_report().high_count == 1

    def test_medium_count(self):
        assert self._make_report().medium_count == 1

    def test_low_count(self):
        assert self._make_report().low_count == 2

    def test_avg_complexity(self):
        # (2 + 8 + 20 + 4) / 4 = 34 / 4 = 8.5
        assert self._make_report().avg_complexity == 8.5

    def test_empty_report_defaults(self):
        rpt = ComplexityReport()
        assert rpt.total_functions == 0
        assert rpt.avg_complexity == 0.0
        assert rpt.high_count == 0
        assert rpt.medium_count == 0
        assert rpt.low_count == 0


# ---------------------------------------------------------------------------
# ComplexityReport serialisation
# ---------------------------------------------------------------------------


class TestComplexityReportSerialization:
    def _make_report(self) -> ComplexityReport:
        rpt = ComplexityReport(repo_path="/tmp/repo", files_scanned=2)
        rpt.results = [
            FunctionComplexity("foo", "src/a.py", 1, 3, "LOW"),
            FunctionComplexity("bar", "src/b.py", 5, 16, "HIGH"),
        ]
        return rpt

    def test_to_dict_keys(self):
        d = self._make_report().to_dict()
        assert "repo_path" in d
        assert "files_scanned" in d
        assert "total_functions" in d
        assert "avg_complexity" in d
        assert "high_count" in d
        assert "medium_count" in d
        assert "low_count" in d
        assert "results" in d

    def test_to_dict_results_are_dicts(self):
        d = self._make_report().to_dict()
        assert all(isinstance(r, dict) for r in d["results"])

    def test_to_json_valid(self):
        rpt = self._make_report()
        obj = json.loads(rpt.to_json())
        assert obj["total_functions"] == 2
        assert len(obj["results"]) == 2

    def test_to_markdown_contains_header(self):
        md = self._make_report().to_markdown()
        assert "Cyclomatic Complexity Report" in md

    def test_to_markdown_contains_high_section(self):
        md = self._make_report().to_markdown()
        assert "HIGH" in md

    def test_to_markdown_contains_function_names(self):
        md = self._make_report().to_markdown()
        assert "foo" in md
        assert "bar" in md

    def test_to_markdown_empty(self):
        rpt = ComplexityReport(repo_path="/tmp", files_scanned=0)
        md = rpt.to_markdown()
        assert "No functions found" in md


# ---------------------------------------------------------------------------
# analyze_complexity — integration tests
# ---------------------------------------------------------------------------


class TestAnalyzeComplexity:
    def test_missing_src_dir_returns_empty_report(self, tmp_path):
        report = analyze_complexity(repo_path=tmp_path)
        assert report.total_functions == 0
        assert report.files_scanned == 0

    def test_empty_src_dir_returns_empty_report(self, tmp_path):
        (tmp_path / "src").mkdir()
        report = analyze_complexity(repo_path=tmp_path)
        assert report.total_functions == 0
        assert report.files_scanned == 0

    def test_empty_python_file(self, tmp_path):
        _make_src(tmp_path, "empty.py", "")
        report = analyze_complexity(repo_path=tmp_path)
        assert report.total_functions == 0
        assert report.files_scanned == 1

    def test_simple_function_complexity_one(self, tmp_path):
        _make_src(tmp_path, "simple.py", "def f():\n    return 42\n")
        report = analyze_complexity(repo_path=tmp_path)
        assert report.total_functions == 1
        assert report.results[0].complexity == 1
        assert report.results[0].rank == "LOW"

    def test_syntax_error_file_skipped(self, tmp_path):
        _make_src(tmp_path, "broken.py", "def bad(:\n")
        report = analyze_complexity(repo_path=tmp_path)
        assert report.files_scanned == 0
        assert report.total_functions == 0

    def test_multiple_files_aggregated(self, tmp_path):
        _make_src(tmp_path, "a.py", "def fa():\n    return 1\n")
        _make_src(tmp_path, "b.py", "def fb():\n    return 2\n")
        report = analyze_complexity(repo_path=tmp_path)
        assert report.files_scanned == 2
        assert report.total_functions == 2

    def test_results_sorted_by_descending_complexity(self, tmp_path):
        src = (
            "def simple():\n"
            "    return 1\n"
            "\n"
            "def complex_one(x):\n"
            "    if x:\n"
            "        for i in x:\n"
            "            if i:\n"
            "                pass\n"
        )
        _make_src(tmp_path, "mixed.py", src)
        report = analyze_complexity(repo_path=tmp_path)
        complexities = [r.complexity for r in report.results]
        assert complexities == sorted(complexities, reverse=True)

    def test_relative_file_path_in_results(self, tmp_path):
        _make_src(tmp_path, "rel.py", "def g():\n    pass\n")
        report = analyze_complexity(repo_path=tmp_path)
        assert report.results[0].file.startswith("src/")

    def test_high_complexity_function_detected(self, tmp_path):
        # Build a function with complexity >= 15
        branches = "\n".join(
            f"    if x == {i}:\n        pass" for i in range(15)
        )
        src = f"def very_complex(x):\n{branches}\n"
        _make_src(tmp_path, "complex.py", src)
        report = analyze_complexity(repo_path=tmp_path)
        assert report.high_count >= 1
        assert report.results[0].rank == "HIGH"

    def test_repo_path_stored_in_report(self, tmp_path):
        (tmp_path / "src").mkdir()
        report = analyze_complexity(repo_path=tmp_path)
        assert str(tmp_path) == report.repo_path


# ---------------------------------------------------------------------------
# save_complexity_report
# ---------------------------------------------------------------------------


class TestSaveComplexityReport:
    def _simple_report(self) -> ComplexityReport:
        rpt = ComplexityReport(repo_path="/tmp/repo", files_scanned=1)
        rpt.results = [
            FunctionComplexity("foo", "src/a.py", 1, 3, "LOW"),
        ]
        return rpt

    def test_writes_markdown_file(self, tmp_path):
        out = tmp_path / "complexity.md"
        save_complexity_report(self._simple_report(), out)
        assert out.exists()
        assert "Cyclomatic Complexity Report" in out.read_text()

    def test_writes_json_sidecar(self, tmp_path):
        out = tmp_path / "complexity.md"
        save_complexity_report(self._simple_report(), out)
        json_file = tmp_path / "complexity.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert "results" in data

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "a" / "b" / "c" / "report.md"
        save_complexity_report(self._simple_report(), out)
        assert out.exists()

    def test_json_sidecar_valid_structure(self, tmp_path):
        out = tmp_path / "report.md"
        save_complexity_report(self._simple_report(), out)
        data = json.loads((tmp_path / "report.json").read_text())
        assert data["total_functions"] == 1
        assert data["files_scanned"] == 1
