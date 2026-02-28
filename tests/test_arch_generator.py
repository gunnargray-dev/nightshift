"""Tests for src/arch_generator.py — the architecture doc auto-generator."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.arch_generator import (
    generate_architecture_doc,
    save_architecture_doc,
    _parse_module,
    _render_module_section,
    _render_dep_graph,
    _render_tree,
    _first_docstring,
    _top_level_imports,
    _arg_names,
    _return_annotation,
    ModuleInfo,
    ClassInfo,
    FunctionInfo,
    ArchitectureDoc,
    DESIGN_PRINCIPLES,
)
import ast


def _make_module(tmp_path: Path, name: str, source: str) -> Path:
    """Write a Python file and return its path."""
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return p


class TestFirstDocstring:
    def test_module_docstring_extracted(self):
        source = '"""Module level doc."""\n\nx = 1\n'
        tree = ast.parse(source)
        assert _first_docstring(tree) == "Module level doc."

    def test_no_docstring_returns_empty(self):
        tree = ast.parse("x = 1\n")
        assert _first_docstring(tree) == ""

    def test_multiline_docstring_returns_first_line(self):
        source = '"""First line.\n\nSecond paragraph."""\n'
        tree = ast.parse(source)
        assert _first_docstring(tree) == "First line."


class TestTopLevelImports:
    def test_simple_import(self):
        tree = ast.parse("import os\nimport sys\n")
        imports = _top_level_imports(tree)
        assert "os" in imports and "sys" in imports

    def test_from_import(self):
        tree = ast.parse("from pathlib import Path\n")
        assert "pathlib" in _top_level_imports(tree)

    def test_cross_module_import(self):
        tree = ast.parse("from src.health import HealthReport\n")
        assert "src" in _top_level_imports(tree)

    def test_no_imports_returns_empty(self):
        assert _top_level_imports(ast.parse("x = 1\n")) == []


class TestParseModule:
    def test_basic_module_parsed(self, tmp_path):
        source = textwrap.dedent("""\
            \"\"\"My module docstring.\"\"\"

            import os

            class MyClass:
                \"\"\"A test class.\"\"\"
                def method(self):
                    pass

            def standalone():
                \"\"\"Standalone func.\"\"\"
                pass
        """)
        p = _make_module(tmp_path, "mymod.py", source)
        info = _parse_module(p, tmp_path)
        assert info is not None
        assert info.name == "mymod"
        assert info.docstring == "My module docstring."
        assert len(info.classes) == 1
        assert info.classes[0].name == "MyClass"
        assert len(info.functions) == 1
        assert info.functions[0].name == "standalone"

    def test_import_tracking(self, tmp_path):
        p = _make_module(tmp_path, "mod.py", "import os\nfrom pathlib import Path\n\nx = 1\n")
        info = _parse_module(p, tmp_path)
        assert "os" in info.imports and "pathlib" in info.imports

    def test_syntax_error_returns_none(self, tmp_path):
        p = _make_module(tmp_path, "broken.py", "def foo(:\n    pass\n")
        assert _parse_module(p, tmp_path) is None

    def test_line_count(self, tmp_path):
        p = _make_module(tmp_path, "lines.py", "x = 1\ny = 2\nz = 3\n")
        assert _parse_module(p, tmp_path).lines == 3

    def test_relative_path_stored(self, tmp_path):
        p = _make_module(tmp_path, "relmod.py", "x = 1\n")
        assert _parse_module(p, tmp_path).path == "relmod.py"

    def test_class_with_bases(self, tmp_path):
        p = _make_module(tmp_path, "cls.py", "class Child(Base):\n    pass\n")
        assert _parse_module(p, tmp_path).classes[0].bases == ["Base"]

    def test_async_function_tracked(self, tmp_path):
        p = _make_module(tmp_path, "async_mod.py", "async def fetch():\n    pass\n")
        assert _parse_module(p, tmp_path).functions[0].is_async is True


class TestRenderModuleSection:
    def test_basic_render(self):
        info = ModuleInfo(path="src/foo.py", name="foo", docstring="Does foo.", lines=42)
        md = _render_module_section(info)
        assert "foo.py" in md and "Does foo." in md and "42 lines" in md

    def test_classes_included(self):
        info = ModuleInfo(
            path="src/foo.py", name="foo", docstring="", lines=10,
            classes=[ClassInfo(name="FooBar", lineno=5, docstring="The FooBar class.")],
        )
        assert "FooBar" in _render_module_section(info)

    def test_functions_included(self):
        info = ModuleInfo(
            path="src/foo.py", name="foo", docstring="", lines=10,
            functions=[FunctionInfo(name="compute", lineno=3, docstring="Computes stuff.")],
        )
        assert "compute" in _render_module_section(info)

    def test_private_functions_excluded(self):
        info = ModuleInfo(
            path="src/foo.py", name="foo", docstring="", lines=10,
            functions=[FunctionInfo(name="_helper", lineno=3, docstring="Private.")],
        )
        assert "_helper" not in _render_module_section(info)


class TestRenderDepGraph:
    def test_standalone_module(self):
        m = ModuleInfo(path="src/stats.py", name="stats", imports=["os", "re"])
        assert "standalone" in _render_dep_graph([m])

    def test_cross_module_dependency(self):
        health = ModuleInfo(path="src/health.py", name="health", imports=["ast"])
        readme = ModuleInfo(path="src/readme_updater.py", name="readme_updater", imports=["health"])
        assert "`health`" in _render_dep_graph([health, readme])


class TestRenderTree:
    def test_tree_includes_files(self, tmp_path):
        (tmp_path / "file.py").write_text("x=1")
        assert any("file.py" in line for line in _render_tree(tmp_path))

    def test_tree_excludes_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "foo.pyc").write_text("x")
        assert not any("__pycache__" in line for line in _render_tree(tmp_path))

    def test_tree_excludes_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert not any(".git" in line for line in _render_tree(tmp_path))


class TestGenerateArchitectureDoc:
    def test_returns_string(self, tmp_path):
        doc = generate_architecture_doc(repo_path=tmp_path)
        assert isinstance(doc, str) and len(doc) > 100

    def test_contains_section_headers(self, tmp_path):
        doc = generate_architecture_doc(repo_path=tmp_path)
        assert "# Architecture" in doc
        assert "## Design Principles" in doc
        assert "## Codebase Stats" in doc

    def test_includes_src_modules(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mymod.py").write_text('"""My module."""\n\ndef foo():\n    pass\n')
        doc = generate_architecture_doc(repo_path=tmp_path)
        assert "mymod.py" in doc and "My module." in doc

    def test_excludes_init_from_inventory(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("# init\n")
        doc = generate_architecture_doc(repo_path=tmp_path)
        assert "### `src/__init__.py`" not in doc

    def test_design_principles_present(self, tmp_path):
        doc = generate_architecture_doc(repo_path=tmp_path)
        for principle in DESIGN_PRINCIPLES[:3]:
            key_word = principle.split("**")[1].split("**")[0]
            assert key_word in doc

    def test_timestamp_present(self, tmp_path):
        doc = generate_architecture_doc(repo_path=tmp_path)
        assert "UTC" in doc or "Auto-generated" in doc

    def test_dependency_graph_section(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text('"""Health module."""\n')
        (src / "readme_updater.py").write_text('"""Readme updater."""\nfrom src import health\n')
        doc = generate_architecture_doc(repo_path=tmp_path)
        assert "Dependency" in doc


class TestSaveArchitectureDoc:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "docs" / "ARCHITECTURE.md"
        save_architecture_doc("# Test Architecture\n", out)
        assert out.exists()
        assert out.read_text() == "# Test Architecture\n"

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "a" / "b" / "c" / "ARCH.md"
        save_architecture_doc("content", out)
        assert out.exists()

    def test_overwrites_existing(self, tmp_path):
        out = tmp_path / "ARCH.md"
        out.write_text("old content")
        save_architecture_doc("new content", out)
        assert out.read_text() == "new content"
