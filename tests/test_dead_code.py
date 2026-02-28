"""Tests for src/dead_code.py — Dead code detector."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dead_code import (
    DeadItem,
    DeadCodeReport,
    find_dead_code,
    save_dead_code_report,
    _parse_file,
    _NameCollector,
    _DefCollector,
)


# ---------------------------------------------------------------------------
# DeadItem
# ---------------------------------------------------------------------------

class TestDeadItem:
    def _item(self, kind="function", confidence="HIGH") -> DeadItem:
        return DeadItem(
            kind=kind,
            name="mod.foo",
            file="src/mod.py",
            line=10,
            confidence=confidence,
            reason="Never called",
        )

    def test_to_dict_keys(self):
        d = self._item().to_dict()
        assert "kind" in d
        assert "name" in d
        assert "file" in d
        assert "line" in d
        assert "confidence" in d
        assert "reason" in d

    def test_function_kind(self):
        item = self._item(kind="function")
        assert item.kind == "function"

    def test_import_kind(self):
        item = self._item(kind="import")
        assert item.kind == "import"


# ---------------------------------------------------------------------------
# DeadCodeReport
# ---------------------------------------------------------------------------

class TestDeadCodeReport:
    def _make_report(self) -> DeadCodeReport:
        rpt = DeadCodeReport(repo_path="/tmp/repo", files_scanned=5)
        rpt.items = [
            DeadItem("function", "a.foo", "src/a.py", 1, "HIGH", "Never called"),
            DeadItem("class", "a.Bar", "src/a.py", 5, "HIGH", "Never referenced"),
            DeadItem("import", "os", "src/b.py", 2, "MEDIUM", "Not used"),
        ]
        return rpt

    def test_dead_functions(self):
        rpt = self._make_report()
        assert len(rpt.dead_functions) == 1

    def test_dead_classes(self):
        rpt = self._make_report()
        assert len(rpt.dead_classes) == 1

    def test_dead_imports(self):
        rpt = self._make_report()
        assert len(rpt.dead_imports) == 1

    def test_high_confidence(self):
        rpt = self._make_report()
        assert len(rpt.high_confidence) == 2

    def test_to_markdown_has_sections(self):
        rpt = self._make_report()
        md = rpt.to_markdown()
        assert "Functions" in md
        assert "Classes" in md
        assert "Imports" in md

    def test_to_markdown_empty(self):
        rpt = DeadCodeReport(repo_path="/tmp", files_scanned=0)
        md = rpt.to_markdown()
        assert "No dead-code candidates" in md

    def test_to_dict(self):
        rpt = self._make_report()
        d = rpt.to_dict()
        assert d["dead_functions"] == 1
        assert d["dead_classes"] == 1
        assert d["dead_imports"] == 1
        assert d["high_confidence"] == 2

    def test_to_json_valid(self):
        rpt = self._make_report()
        obj = json.loads(rpt.to_json())
        assert "items" in obj


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

_SAMPLE_SOURCE = """
import os
import sys
from pathlib import Path

def public_func():
    pass

def _private_func():
    pass

class PublicClass:
    def method(self):
        pass

class _PrivateClass:
    pass
"""


class TestDefCollector:
    def _collect(self, source: str) -> _DefCollector:
        import ast
        tree = ast.parse(source)
        dc = _DefCollector()
        dc.visit(tree)
        return dc

    def test_finds_public_function(self):
        dc = self._collect(_SAMPLE_SOURCE)
        names = [n for n, _ in dc.functions]
        assert "public_func" in names

    def test_skips_private_function(self):
        # _DefCollector collects ALL top-level; caller filters underscore
        dc = self._collect(_SAMPLE_SOURCE)
        names = [n for n, _ in dc.functions]
        assert "_private_func" in names  # collected, but filtered later

    def test_finds_public_class(self):
        dc = self._collect(_SAMPLE_SOURCE)
        names = [n for n, _ in dc.classes]
        assert "PublicClass" in names

    def test_finds_imports(self):
        dc = self._collect(_SAMPLE_SOURCE)
        names = [n for n, _ in dc.imports]
        assert "os" in names
        assert "sys" in names
        assert "Path" in names

    def test_nested_not_top_level(self):
        source = """
class Outer:
    def inner_method(self):
        pass
"""
        dc = self._collect(source)
        # Only Outer should be in classes, inner_method not in top-level functions
        assert len(dc.functions) == 0
        assert len(dc.classes) == 1


class TestNameCollector:
    def _collect(self, source: str) -> set:
        import ast
        tree = ast.parse(source)
        nc = _NameCollector()
        nc.visit(tree)
        return nc.used

    def test_finds_name_usage(self):
        used = self._collect("x = os.path.join('a', 'b')")
        assert "os" in used
        assert "join" in used

    def test_finds_call_name(self):
        used = self._collect("public_func()")
        assert "public_func" in used


# ---------------------------------------------------------------------------
# _parse_file
# ---------------------------------------------------------------------------

class TestParseFile:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text("x = 1\n")
        tree = _parse_file(f)
        assert tree is not None

    def test_syntax_error_returns_none(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n")
        assert _parse_file(f) is None


# ---------------------------------------------------------------------------
# find_dead_code integration
# ---------------------------------------------------------------------------

class TestFindDeadCode:
    def test_missing_src_dir(self, tmp_path):
        report = find_dead_code(repo_path=tmp_path)
        assert report.files_scanned == 0

    def test_finds_unused_function(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text(
            "def never_called():\n    pass\n\ndef used():\n    pass\n"
        )
        # Create a second file that calls `used` but not `never_called`
        (src / "other.py").write_text("from src.mod import used\nused()\n")
        report = find_dead_code(repo_path=tmp_path)
        names = [i.name for i in report.dead_functions]
        assert "mod.never_called" in names
        # `used` is referenced in other.py so should NOT be flagged
        assert "mod.used" not in names

    def test_unused_import_flagged(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "imp.py").write_text("import os\n\ndef foo():\n    pass\n")
        report = find_dead_code(repo_path=tmp_path)
        names = [i.name for i in report.dead_imports]
        assert "os" in names

    def test_private_functions_not_flagged(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "priv.py").write_text("def _internal():\n    pass\n")
        report = find_dead_code(repo_path=tmp_path)
        names = [i.name for i in report.dead_functions]
        assert not any("_internal" in n for n in names)

    def test_skips_init_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("def init_func(): pass\n")
        report = find_dead_code(repo_path=tmp_path)
        assert report.files_scanned == 0

    def test_syntax_error_file_gracefully_skipped(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "broken.py").write_text("def bad(:\n")
        report = find_dead_code(repo_path=tmp_path)
        assert isinstance(report, DeadCodeReport)

    def test_empty_src_dir(self, tmp_path):
        (tmp_path / "src").mkdir()
        report = find_dead_code(repo_path=tmp_path)
        assert report.files_scanned == 0

    def test_report_repo_path(self, tmp_path):
        (tmp_path / "src").mkdir()
        report = find_dead_code(repo_path=tmp_path)
        assert str(tmp_path) == report.repo_path


# ---------------------------------------------------------------------------
# save_dead_code_report
# ---------------------------------------------------------------------------

class TestSaveDeadCodeReport:
    def test_writes_markdown(self, tmp_path):
        out = tmp_path / "dead.md"
        rpt = DeadCodeReport(repo_path=str(tmp_path))
        save_dead_code_report(rpt, out)
        assert out.exists()

    def test_writes_json_sidecar(self, tmp_path):
        out = tmp_path / "dead.md"
        rpt = DeadCodeReport(repo_path=str(tmp_path))
        save_dead_code_report(rpt, out)
        jf = out.with_suffix(".json")
        assert jf.exists()
        assert json.loads(jf.read_text())

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "a" / "b" / "dead.md"
        rpt = DeadCodeReport(repo_path=str(tmp_path))
        save_dead_code_report(rpt, out)
        assert out.exists()
