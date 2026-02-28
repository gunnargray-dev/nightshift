"""Tests for src/coverage_map.py — Test coverage heat map."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.coverage_map import (
    ModuleCoverageEntry,
    CoverageMapReport,
    build_coverage_map,
    save_coverage_map,
    _count_public_symbols,
    _count_test_functions,
    _parse_or_none,
)


# ---------------------------------------------------------------------------
# _count_public_symbols
# ---------------------------------------------------------------------------

def _parse(source: str):
    import ast
    return ast.parse(source)


class TestCountPublicSymbols:
    def test_counts_public_function(self):
        tree = _parse("def foo(): pass\ndef bar(): pass\n")
        assert _count_public_symbols(tree) == 2

    def test_skips_private_function(self):
        tree = _parse("def _foo(): pass\ndef bar(): pass\n")
        assert _count_public_symbols(tree) == 1

    def test_counts_public_class(self):
        tree = _parse("class Foo: pass\nclass Bar: pass\n")
        assert _count_public_symbols(tree) == 2

    def test_skips_private_class(self):
        tree = _parse("class _Foo: pass\nclass Bar: pass\n")
        assert _count_public_symbols(tree) == 1

    def test_mixed(self):
        tree = _parse(
            "def pub(): pass\ndef _priv(): pass\nclass Pub: pass\nclass _Priv: pass\n"
        )
        assert _count_public_symbols(tree) == 2

    def test_empty_module(self):
        tree = _parse("")
        assert _count_public_symbols(tree) == 0


# ---------------------------------------------------------------------------
# _count_test_functions
# ---------------------------------------------------------------------------

class TestCountTestFunctions:
    def test_counts_test_functions(self):
        tree = _parse(
            "def test_foo(): pass\ndef test_bar(): pass\ndef helper(): pass\n"
        )
        assert _count_test_functions(tree) == 2

    def test_skips_non_test_functions(self):
        tree = _parse("def foo(): pass\ndef helper(): pass\n")
        assert _count_test_functions(tree) == 0

    def test_nested_test_functions(self):
        source = """
class TestFoo:
    def test_a(self):
        pass
    def test_b(self):
        pass
    def setup(self):
        pass
"""
        tree = _parse(source)
        assert _count_test_functions(tree) == 2

    def test_async_test_counted(self):
        tree = _parse("async def test_async(): pass\n")
        assert _count_test_functions(tree) == 1


# ---------------------------------------------------------------------------
# _parse_or_none
# ---------------------------------------------------------------------------

class TestParseOrNone:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text("x = 1\n")
        tree = _parse_or_none(f)
        assert tree is not None

    def test_syntax_error_returns_none(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n")
        assert _parse_or_none(f) is None

    def test_missing_file_returns_none(self, tmp_path):
        f = tmp_path / "missing.py"
        assert _parse_or_none(f) is None


# ---------------------------------------------------------------------------
# ModuleCoverageEntry
# ---------------------------------------------------------------------------

class TestModuleCoverageEntry:
    def _entry(self, public=10, tests=30, has_test=True) -> ModuleCoverageEntry:
        return ModuleCoverageEntry(
            module="health",
            src_file="src/health.py",
            test_file="tests/test_health.py",
            public_symbols=public,
            test_count=tests,
            has_test_file=has_test,
        )

    def test_ratio_calculation(self):
        e = self._entry(public=10, tests=30)
        assert e.ratio == 3.0

    def test_ratio_zero_symbols(self):
        e = self._entry(public=0, tests=5)
        assert e.ratio == 0.0

    def test_ratio_no_test_file(self):
        e = self._entry(has_test=False)
        assert e.ratio == 0.0

    def test_coverage_score_100_at_3x(self):
        e = self._entry(public=10, tests=30)
        assert e.coverage_score == 100

    def test_coverage_score_0_no_tests(self):
        e = self._entry(public=10, tests=0)
        assert e.coverage_score == 0

    def test_coverage_score_0_no_test_file(self):
        e = self._entry(has_test=False)
        assert e.coverage_score == 0

    def test_coverage_score_partial(self):
        e = self._entry(public=10, tests=10)
        # ratio = 1.0, score = round(1.0/3.0 * 100) = 33
        assert e.coverage_score == 33

    def test_heat_green_high_score(self):
        e = self._entry(public=5, tests=15)  # score 100
        assert e.heat == "🟢"

    def test_heat_red_zero_score(self):
        e = self._entry(public=10, tests=0)
        assert e.heat == "🔴"

    def test_to_dict_has_all_keys(self):
        d = self._entry().to_dict()
        assert "module" in d
        assert "coverage_score" in d
        assert "ratio" in d
        assert "heat" in d
        assert "has_test_file" in d


# ---------------------------------------------------------------------------
# CoverageMapReport
# ---------------------------------------------------------------------------

class TestCoverageMapReport:
    def _make_report(self) -> CoverageMapReport:
        rpt = CoverageMapReport(repo_path="/tmp/repo")
        rpt.entries = [
            ModuleCoverageEntry("a", "src/a.py", "tests/test_a.py", 10, 30, True),
            ModuleCoverageEntry("b", "src/b.py", "tests/test_b.py", 10, 5, True),
            ModuleCoverageEntry("c", "src/c.py", "—", 5, 0, False),
        ]
        return rpt

    def test_modules_without_tests(self):
        rpt = self._make_report()
        assert len(rpt.modules_without_tests) == 1
        assert rpt.modules_without_tests[0].module == "c"

    def test_weakest_sorted_ascending(self):
        rpt = self._make_report()
        w = rpt.weakest
        # scores should be ascending
        scores = [e.coverage_score for e in w]
        assert scores == sorted(scores)

    def test_avg_score(self):
        rpt = self._make_report()
        avg = rpt.avg_score
        assert avg >= 0.0
        assert avg <= 100.0

    def test_total_tests(self):
        rpt = self._make_report()
        assert rpt.total_tests == 35

    def test_total_symbols(self):
        rpt = self._make_report()
        assert rpt.total_symbols == 25

    def test_to_markdown_has_heat_map(self):
        rpt = self._make_report()
        md = rpt.to_markdown()
        assert "Heat Map" in md

    def test_to_markdown_lists_missing(self):
        rpt = self._make_report()
        md = rpt.to_markdown()
        assert "Missing Test Files" in md

    def test_to_markdown_empty(self):
        rpt = CoverageMapReport(repo_path="/tmp")
        md = rpt.to_markdown()
        assert "No modules found" in md

    def test_to_dict(self):
        rpt = self._make_report()
        d = rpt.to_dict()
        assert d["modules_count"] == 3
        assert d["total_tests"] == 35
        assert "entries" in d

    def test_to_json_valid(self):
        rpt = self._make_report()
        obj = json.loads(rpt.to_json())
        assert "entries" in obj


# ---------------------------------------------------------------------------
# build_coverage_map integration
# ---------------------------------------------------------------------------

class TestBuildCoverageMap:
    def test_missing_src_dir(self, tmp_path):
        report = build_coverage_map(repo_path=tmp_path)
        assert len(report.entries) == 0

    def test_finds_module_with_test_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        tests = tmp_path / "tests"
        tests.mkdir()
        (src / "health.py").write_text(
            "def analyze(): pass\ndef score(): pass\n"
        )
        (tests / "test_health.py").write_text(
            "def test_analyze(): pass\ndef test_score(): pass\ndef test_extra(): pass\n"
        )
        report = build_coverage_map(repo_path=tmp_path)
        assert len(report.entries) == 1
        e = report.entries[0]
        assert e.module == "health"
        assert e.public_symbols == 2
        assert e.test_count == 3
        assert e.has_test_file is True

    def test_module_without_test_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "tests").mkdir()
        (src / "orphan.py").write_text("def foo(): pass\n")
        report = build_coverage_map(repo_path=tmp_path)
        e = report.entries[0]
        assert e.has_test_file is False
        assert e.test_count == 0
        assert e.coverage_score == 0

    def test_skips_init_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "tests").mkdir()
        (src / "__init__.py").write_text("def init_func(): pass\n")
        (src / "real.py").write_text("def real(): pass\n")
        report = build_coverage_map(repo_path=tmp_path)
        modules = [e.module for e in report.entries]
        assert "__init__" not in modules
        assert "real" in modules

    def test_repo_path_recorded(self, tmp_path):
        (tmp_path / "src").mkdir()
        report = build_coverage_map(repo_path=tmp_path)
        assert str(tmp_path) == report.repo_path


# ---------------------------------------------------------------------------
# save_coverage_map
# ---------------------------------------------------------------------------

class TestSaveCoverageMap:
    def test_writes_markdown_and_json(self, tmp_path):
        out = tmp_path / "cov.md"
        rpt = CoverageMapReport(repo_path=str(tmp_path))
        save_coverage_map(rpt, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_json_content(self, tmp_path):
        out = tmp_path / "cov.md"
        rpt = CoverageMapReport(repo_path=str(tmp_path))
        save_coverage_map(rpt, out)
        data = json.loads(out.with_suffix(".json").read_text())
        assert "entries" in data

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "a" / "b" / "cov.md"
        rpt = CoverageMapReport(repo_path=str(tmp_path))
        save_coverage_map(rpt, out)
        assert out.exists()
