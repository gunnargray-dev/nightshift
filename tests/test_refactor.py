"""Tests for src/refactor.py — the self-refactor engine."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.refactor import (
    RefactorEngine,
    RefactorReport,
    RefactorSuggestion,
    FileRefactorResult,
    _analyse_file,
    _analyse_missing_docstrings,
    _analyse_long_lines,
    _analyse_todos,
    _analyse_bare_excepts,
    _analyse_dead_imports,
    _apply_docstring_fix,
)

import ast


class TestRefactorSuggestion:
    def test_to_dict_contains_all_fields(self):
        s = RefactorSuggestion(
            file="src/foo.py", line=10, category="MISSING_DOCSTRING",
            severity="medium", fix_strategy="auto", message="missing docstring",
        )
        d = s.to_dict()
        assert d["file"] == "src/foo.py"
        assert d["category"] == "MISSING_DOCSTRING"
        assert d["severity"] == "medium"


class TestFileRefactorResult:
    def test_suggestion_count(self):
        result = FileRefactorResult(path="src/foo.py")
        s1 = RefactorSuggestion("src/foo.py", 1, "TODO_DEBT", "medium", "review", "msg")
        s2 = RefactorSuggestion("src/foo.py", 5, "LONG_LINE", "low", "manual", "msg")
        result.suggestions = [s1, s2]
        assert result.suggestion_count == 2

    def test_high_severity_filter(self):
        result = FileRefactorResult(path="src/foo.py")
        s_high = RefactorSuggestion("src/foo.py", 1, "BARE_EXCEPT", "high", "manual", "msg")
        s_low = RefactorSuggestion("src/foo.py", 5, "LONG_LINE", "low", "manual", "msg")
        result.suggestions = [s_high, s_low]
        assert len(result.high_severity) == 1
        assert result.high_severity[0].category == "BARE_EXCEPT"

    def test_auto_fixable_filter(self):
        result = FileRefactorResult(path="src/foo.py")
        auto = RefactorSuggestion("src/foo.py", 1, "MISSING_DOCSTRING", "low", "auto", "msg")
        manual = RefactorSuggestion("src/foo.py", 5, "LONG_LINE", "low", "manual", "msg")
        result.suggestions = [auto, manual]
        assert len(result.auto_fixable) == 1


class TestRefactorReport:
    def test_total_suggestions(self):
        r = RefactorReport()
        f1 = FileRefactorResult(path="a.py")
        f1.suggestions = [RefactorSuggestion("a.py", 1, "TODO_DEBT", "medium", "review", "msg")]
        f2 = FileRefactorResult(path="b.py")
        f2.suggestions = [
            RefactorSuggestion("b.py", 1, "LONG_LINE", "low", "manual", "msg"),
            RefactorSuggestion("b.py", 2, "BARE_EXCEPT", "high", "manual", "msg"),
        ]
        r.files = [f1, f2]
        assert r.total_suggestions == 3

    def test_to_markdown_no_suggestions(self):
        r = RefactorReport()
        md = r.to_markdown()
        assert "No refactor suggestions" in md

    def test_to_markdown_with_suggestions(self):
        r = RefactorReport()
        f = FileRefactorResult(path="src/stats.py")
        f.suggestions = [RefactorSuggestion("src/stats.py", 5, "BARE_EXCEPT", "high", "manual", "bare except")]
        r.files = [f]
        md = r.to_markdown()
        assert "BARE_EXCEPT" in md
        assert "stats.py" in md

    def test_all_suggestions_sorted_by_severity(self):
        r = RefactorReport()
        f = FileRefactorResult(path="src/foo.py")
        low = RefactorSuggestion("src/foo.py", 10, "LONG_LINE", "low", "manual", "msg")
        high = RefactorSuggestion("src/foo.py", 5, "BARE_EXCEPT", "high", "manual", "msg")
        med = RefactorSuggestion("src/foo.py", 7, "TODO_DEBT", "medium", "review", "msg")
        f.suggestions = [low, high, med]
        r.files = [f]
        sorted_suggestions = r.all_suggestions
        assert sorted_suggestions[0].severity == "high"
        assert sorted_suggestions[1].severity == "medium"
        assert sorted_suggestions[2].severity == "low"

    def test_to_dict(self):
        r = RefactorReport(generated_at="2026-02-27", session=4)
        d = r.to_dict()
        assert d["session"] == 4
        assert d["generated_at"] == "2026-02-27"


class TestAnalyseMissingDocstrings:
    def test_function_without_docstring(self, tmp_path):
        py = tmp_path / "test.py"
        py.write_text("def foo():\n    return 42\n")
        tree = ast.parse(py.read_text())
        sugg = _analyse_missing_docstrings(tree, py.read_text().splitlines(), "test.py")
        assert any(s.category == "MISSING_DOCSTRING" and "foo" in s.message for s in sugg)

    def test_function_with_docstring_ignored(self, tmp_path):
        py = tmp_path / "test.py"
        py.write_text('def foo():\n    """Does stuff."""\n    return 42\n')
        tree = ast.parse(py.read_text())
        sugg = _analyse_missing_docstrings(tree, py.read_text().splitlines(), "test.py")
        assert not sugg

    def test_private_function_ignored(self, tmp_path):
        py = tmp_path / "test.py"
        py.write_text("def _private():\n    pass\n")
        tree = ast.parse(py.read_text())
        sugg = _analyse_missing_docstrings(tree, py.read_text().splitlines(), "test.py")
        assert not sugg

    def test_class_without_docstring(self, tmp_path):
        py = tmp_path / "test.py"
        py.write_text("class Foo:\n    pass\n")
        tree = ast.parse(py.read_text())
        sugg = _analyse_missing_docstrings(tree, py.read_text().splitlines(), "test.py")
        assert any("Foo" in s.message for s in sugg)

    def test_short_function_is_auto_fixable(self, tmp_path):
        py = tmp_path / "test.py"
        py.write_text("def foo():\n    return 1\n")
        tree = ast.parse(py.read_text())
        sugg = _analyse_missing_docstrings(tree, py.read_text().splitlines(), "test.py")
        assert sugg[0].fix_strategy == "auto"


class TestAnalyseLongLines:
    def test_short_lines_no_suggestions(self):
        assert not _analyse_long_lines(["x = 1", "y = 2"], "test.py")

    def test_long_line_detected(self):
        long = "x = " + "a" * 100
        sugg = _analyse_long_lines([long], "test.py")
        assert len(sugg) == 1
        assert sugg[0].category == "LONG_LINE"
        assert sugg[0].line == 1

    def test_exactly_88_chars_ok(self):
        assert not _analyse_long_lines(["x" * 88], "test.py")

    def test_89_chars_triggers(self):
        assert len(_analyse_long_lines(["x" * 89], "test.py")) == 1


class TestAnalyseTodos:
    def test_todo_detected(self):
        sugg = _analyse_todos(["# TODO: fix this", "x = 1"], "test.py")
        assert any(s.category == "TODO_DEBT" for s in sugg)

    def test_fixme_detected(self):
        assert len(_analyse_todos(["# FIXME: broken"], "test.py")) == 1

    def test_no_todo_no_suggestions(self):
        assert not _analyse_todos(["x = 1", "y = 2"], "test.py")

    def test_hack_detected(self):
        assert len(_analyse_todos(["# HACK: workaround"], "test.py")) == 1


class TestAnalyseBareExcepts:
    def test_bare_except_detected(self, tmp_path):
        source = textwrap.dedent("""\
            try:\n                pass\n            except:\n                pass\n        """)
        tree = ast.parse(source)
        sugg = _analyse_bare_excepts(tree, source.splitlines(), "test.py")
        assert any(s.category == "BARE_EXCEPT" for s in sugg)
        assert sugg[0].severity == "high"

    def test_typed_except_ok(self, tmp_path):
        source = textwrap.dedent("""\
            try:\n                pass\n            except ValueError:\n                pass\n        """)
        tree = ast.parse(source)
        assert not _analyse_bare_excepts(tree, source.splitlines(), "test.py")

    def test_bare_except_suggested_fix(self):
        source = "try:\n    x = 1\nexcept:\n    pass\n"
        tree = ast.parse(source)
        sugg = _analyse_bare_excepts(tree, source.splitlines(), "test.py")
        assert sugg[0].suggestion == "except Exception:"


class TestAnalyseDeadImports:
    def test_unused_import_detected(self):
        source = "import os\n\nx = 1\n"
        tree = ast.parse(source)
        sugg = _analyse_dead_imports(tree, source, "test.py")
        assert any(s.category == "DEAD_IMPORT" and "os" in s.message for s in sugg)

    def test_used_import_not_flagged(self):
        source = "import os\n\npath = os.getcwd()\n"
        tree = ast.parse(source)
        assert not any("os" in s.message for s in _analyse_dead_imports(tree, source, "test.py"))

    def test_star_import_skipped(self):
        source = "from os.path import *\n\nx = join('a', 'b')\n"
        tree = ast.parse(source)
        assert not any(s.message.startswith("Import `*`") for s in _analyse_dead_imports(tree, source, "test.py"))


class TestAnalyseFile:
    def test_clean_file_returns_empty_result(self, tmp_path):
        py = tmp_path / "clean.py"
        py.write_text('"""A clean module."""\n\n\ndef compute(x: int) -> int:\n    """Return x doubled."""\n    return x * 2\n')
        result = _analyse_file(py, tmp_path)
        highs = [s for s in result.suggestions if s.severity == "high"]
        assert len(highs) == 0

    def test_problematic_file_has_suggestions(self, tmp_path):
        py = tmp_path / "bad.py"
        py.write_text(
            "import json\n"
            "def oops():\n"
            "    try:\n    "
            "        pass\n"
            "    except:\n"
            "        pass\n"
        )
        result = _analyse_file(py, tmp_path)
        categories = {s.category for s in result.suggestions}
        assert "BARE_EXCEPT" in categories or "MISSING_DOCSTRING" in categories

    def test_syntax_error_file_gracefully_handled(self, tmp_path):
        py = tmp_path / "broken.py"
        py.write_text("def foo(:\n    pass\n")
        result = _analyse_file(py, tmp_path)
        assert isinstance(result, FileRefactorResult)


class TestRefactorEngine:
    def test_analyze_returns_report(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "example.py").write_text('"""Module docstring."""\n\ndef foo():\n    pass\n')
        engine = RefactorEngine(repo_path=tmp_path)
        report = engine.analyze()
        assert isinstance(report, RefactorReport)
        assert report.generated_at != ""

    def test_analyze_finds_issues_in_bad_code(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "messy.py").write_text(
            "import sys\n"
            "def compute():\n"
            "    try:\n"
            "        x = 1\n"
            "    except:\n"
            "        pass\n"
        )
        engine = RefactorEngine(repo_path=tmp_path)
        report = engine.analyze()
        assert report.total_suggestions > 0

    def test_apply_safe_fixes_adds_docstrings(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py = src_dir / "short_func.py"
        py.write_text("def add(a, b):\n    return a + b\n")
        engine = RefactorEngine(repo_path=tmp_path)
        report = engine.analyze()
        auto_count = sum(len(f.auto_fixable) for f in report.files)
        if auto_count > 0:
            applied = engine.apply_safe_fixes(report)
            assert applied > 0
            content = py.read_text()
            assert "TODO" in content or '"""' in content

    def test_analyze_excludes_init_files(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("# empty init\n")
        engine = RefactorEngine(repo_path=tmp_path)
        report = engine.analyze()
        paths = [f.path for f in report.files]
        assert not any("__init__" in p for p in paths)
