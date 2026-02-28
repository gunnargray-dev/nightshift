"""Tests for the Nightshift code health monitor (src/health.py)."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from src.health import (
    FileHealth,
    HealthReport,
    MAX_LINE_LENGTH,
    _count_ast_items,
    _count_docstring_coverage,
    analyze_file,
    analyze_directory,
    generate_health_report,
    save_health_report,
)


# ---------------------------------------------------------------------------
# FileHealth
# ---------------------------------------------------------------------------


class TestFileHealth:
    def test_defaults(self):
        fh = FileHealth(path="src/foo.py")
        assert fh.total_lines == 0
        assert fh.parse_error is False
        assert fh.docstring_coverage == 0.0

    def test_health_score_perfect(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=0,
            todo_count=0,
            docstring_coverage=1.0,
        )
        assert fh.health_score == 100.0

    def test_health_score_long_lines_penalty(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=10,
            todo_count=0,
            docstring_coverage=1.0,
        )
        assert fh.health_score == 100.0 - 5.0  # 10 * 0.5

    def test_health_score_long_lines_capped(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=100,
            todo_count=0,
            docstring_coverage=1.0,
        )
        # Penalty capped at 20
        assert fh.health_score == 80.0

    def test_health_score_todo_penalty(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=0,
            todo_count=3,
            docstring_coverage=1.0,
        )
        assert fh.health_score == 100.0 - 6.0  # 3 * 2.0

    def test_health_score_todo_capped(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=0,
            todo_count=20,
            docstring_coverage=1.0,
        )
        assert fh.health_score == 80.0  # capped at -20

    def test_health_score_no_docstrings(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=0,
            todo_count=0,
            docstring_coverage=0.0,
        )
        assert fh.health_score == 80.0  # -20 for 0% docstrings

    def test_health_score_half_docstrings(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=0,
            todo_count=0,
            docstring_coverage=0.5,
        )
        assert fh.health_score == 90.0  # -10 for 50% docstrings

    def test_health_score_parse_error(self):
        fh = FileHealth(path="src/foo.py", parse_error=True)
        assert fh.health_score == 50.0

    def test_health_score_floor_is_zero(self):
        fh = FileHealth(
            path="src/foo.py",
            long_lines=1000,
            todo_count=1000,
            docstring_coverage=0.0,
        )
        assert fh.health_score >= 0.0

    def test_to_dict(self):
        fh = FileHealth(path="src/foo.py", total_lines=100)
        d = fh.to_dict()
        assert d["path"] == "src/foo.py"
        assert d["total_lines"] == 100


# ---------------------------------------------------------------------------
# HealthReport
# ---------------------------------------------------------------------------


class TestHealthReport:
    def _make_file(self, **kwargs) -> FileHealth:
        defaults = {
            "path": "src/foo.py",
            "total_lines": 50,
            "code_lines": 40,
            "function_count": 3,
            "class_count": 1,
            "todo_count": 0,
            "long_lines": 0,
            "docstring_coverage": 1.0,
        }
        defaults.update(kwargs)
        return FileHealth(**defaults)

    def test_empty_report_defaults(self):
        report = HealthReport()
        assert report.total_lines == 0
        assert report.total_functions == 0
        assert report.overall_health_score == 100.0
        assert report.overall_docstring_coverage == 0.0

    def test_total_lines_sum(self):
        report = HealthReport(
            files=[
                self._make_file(path="a.py", total_lines=100),
                self._make_file(path="b.py", total_lines=200),
            ]
        )
        assert report.total_lines == 300

    def test_total_todos_sum(self):
        report = HealthReport(
            files=[
                self._make_file(path="a.py", todo_count=2),
                self._make_file(path="b.py", todo_count=5),
            ]
        )
        assert report.total_todos == 7

    def test_overall_health_score_average(self):
        f1 = self._make_file(path="a.py", long_lines=0, todo_count=0, docstring_coverage=1.0)
        f2 = self._make_file(path="b.py", long_lines=40, todo_count=0, docstring_coverage=1.0)
        # f1 score = 100, f2 score = 100 - 20 (capped) = 80
        report = HealthReport(files=[f1, f2])
        assert report.overall_health_score == 90.0

    def test_to_markdown_contains_header(self):
        report = HealthReport(generated_at="2026-02-27 23:00 UTC")
        md = report.to_markdown()
        assert "# Code Health Report" in md
        assert "2026-02-27 23:00 UTC" in md

    def test_to_markdown_contains_summary_table(self):
        report = HealthReport(
            files=[self._make_file()],
            generated_at="2026-02-27",
        )
        md = report.to_markdown()
        assert "Overall health score" in md
        assert "Total source lines" in md
        assert "Docstring coverage" in md

    def test_to_markdown_contains_per_file_rows(self):
        report = HealthReport(
            files=[self._make_file(path="src/stats.py")],
            generated_at="now",
        )
        md = report.to_markdown()
        assert "src/stats.py" in md

    def test_to_markdown_sorts_files(self):
        report = HealthReport(
            files=[
                self._make_file(path="src/z.py"),
                self._make_file(path="src/a.py"),
            ],
            generated_at="now",
        )
        md = report.to_markdown()
        idx_a = md.index("src/a.py")
        idx_z = md.index("src/z.py")
        assert idx_a < idx_z


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


class TestCountAstItems:
    def _parse(self, code: str) -> ast.Module:
        return ast.parse(textwrap.dedent(code))

    def test_counts_functions(self):
        tree = self._parse("""
            def foo(): pass
            def bar(): pass
            def baz(): pass
        """)
        funcs, classes = _count_ast_items(tree)
        assert funcs == 3
        assert classes == 0

    def test_counts_classes(self):
        tree = self._parse("""
            class Foo: pass
            class Bar: pass
        """)
        funcs, classes = _count_ast_items(tree)
        assert classes == 2

    def test_counts_methods_as_functions(self):
        tree = self._parse("""
            class MyClass:
                def method_one(self): pass
                def method_two(self): pass
        """)
        funcs, classes = _count_ast_items(tree)
        assert funcs == 2
        assert classes == 1

    def test_empty_module(self):
        tree = self._parse("")
        funcs, classes = _count_ast_items(tree)
        assert funcs == 0
        assert classes == 0


class TestCountDocstringCoverage:
    def _parse(self, code: str) -> ast.Module:
        return ast.parse(textwrap.dedent(code))

    def test_all_documented(self):
        tree = self._parse('''
            def foo():
                """Docstring."""
                pass

            def bar():
                """Docstring."""
                pass
        ''')
        cov = _count_docstring_coverage(tree)
        assert cov == 1.0

    def test_none_documented(self):
        tree = self._parse("""
            def foo():
                pass

            def bar():
                pass
        """)
        cov = _count_docstring_coverage(tree)
        assert cov == 0.0

    def test_half_documented(self):
        tree = self._parse('''
            def foo():
                """Has docstring."""
                pass

            def bar():
                pass
        ''')
        cov = _count_docstring_coverage(tree)
        assert cov == 0.5

    def test_private_functions_excluded(self):
        tree = self._parse("""
            def _private():
                pass

            def __dunder__():
                pass
        """)
        # No public functions → full coverage by convention
        cov = _count_docstring_coverage(tree)
        assert cov == 1.0

    def test_empty_module_full_coverage(self):
        tree = self._parse("")
        cov = _count_docstring_coverage(tree)
        assert cov == 1.0


# ---------------------------------------------------------------------------
# analyze_file
# ---------------------------------------------------------------------------


class TestAnalyzeFile:
    def test_counts_lines(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def foo():\n    pass\n\n# comment\n")
        fh = analyze_file(f)
        assert fh.total_lines == 4
        assert fh.blank_lines == 1
        assert fh.comment_lines == 1

    def test_detects_long_lines(self, tmp_path):
        f = tmp_path / "mod.py"
        long_line = "x = " + "a" * (MAX_LINE_LENGTH + 10)
        f.write_text(long_line + "\n")
        fh = analyze_file(f)
        assert fh.long_lines == 1

    def test_no_long_lines(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("x = 1\n")
        fh = analyze_file(f)
        assert fh.long_lines == 0

    def test_detects_todos(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("# TODO: fix this\n# FIXME: broken\nx = 1  # HACK\n")
        fh = analyze_file(f)
        assert fh.todo_count == 3

    def test_handles_syntax_error(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def foo(\n    # missing closing paren\n")
        fh = analyze_file(f)
        assert fh.parse_error is True

    def test_handles_missing_file(self, tmp_path):
        fh = analyze_file(tmp_path / "nonexistent.py")
        assert fh.parse_error is True

    def test_docstring_coverage_computed(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text(textwrap.dedent('''
            def documented():
                """Has a docstring."""
                pass

            def undocumented():
                pass
        '''))
        fh = analyze_file(f)
        assert fh.docstring_coverage == 0.5

    def test_function_count(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("def a(): pass\ndef b(): pass\nclass C: pass\n")
        fh = analyze_file(f)
        assert fh.function_count == 2
        assert fh.class_count == 1


# ---------------------------------------------------------------------------
# analyze_directory
# ---------------------------------------------------------------------------


class TestAnalyzeDirectory:
    def test_finds_python_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n")
        (src / "b.py").write_text("y = 2\n")
        results = analyze_directory(tmp_path)
        assert len(results) == 2

    def test_excludes_patterns(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("x = 1\n")
        (src / "__init__.py").write_text("")
        results = analyze_directory(tmp_path, exclude=["__init__"])
        paths = [r.path for r in results]
        assert not any("__init__" in p for p in paths)

    def test_empty_directory(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        results = analyze_directory(tmp_path)
        assert results == []

    def test_relative_paths_stored(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("pass\n")
        results = analyze_directory(tmp_path)
        assert results[0].path == "src/mod.py"


# ---------------------------------------------------------------------------
# generate_health_report
# ---------------------------------------------------------------------------


class TestGenerateHealthReport:
    def test_returns_health_report(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def foo():\n    pass\n")
        report = generate_health_report(repo_path=tmp_path)
        assert isinstance(report, HealthReport)

    def test_timestamp_set(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        report = generate_health_report(repo_path=tmp_path, timestamp="2026-02-27 23:00 UTC")
        assert report.generated_at == "2026-02-27 23:00 UTC"

    def test_excludes_init(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "stats.py").write_text("def foo(): pass\n")
        report = generate_health_report(repo_path=tmp_path)
        paths = [f.path for f in report.files]
        assert not any("__init__" in p for p in paths)


# ---------------------------------------------------------------------------
# save_health_report
# ---------------------------------------------------------------------------


class TestSaveHealthReport:
    def test_writes_markdown(self, tmp_path):
        report = HealthReport(generated_at="2026-02-27")
        out = tmp_path / "health_report.md"
        save_health_report(report, out)
        assert out.exists()
        content = out.read_text()
        assert "# Code Health Report" in content
