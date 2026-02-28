"""Tests for src/dep_graph.py — 37 tests."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.dep_graph import (
    ModuleNode,
    DepGraph,
    build_dep_graph,
    render_dep_graph,
    save_dep_graph,
    _parse_src_imports,
)


@pytest.fixture
def simple_src(tmp_path) -> Path:
    """Create a minimal fake src/ with three modules."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "alpha.py").write_text(
        "from __future__ import annotations\n"
        "import os\n"
        "from src.beta import something\n"
        "def run(): pass\n"
    )
    (src / "beta.py").write_text(
        "from __future__ import annotations\n"
        "from src.gamma import other\n"
        "def something(): pass\n"
    )
    (src / "gamma.py").write_text(
        "from __future__ import annotations\n"
        "# standalone module\n"
        "def other(): pass\n"
    )
    return src


@pytest.fixture
def cyclic_src(tmp_path) -> Path:
    """Create a fake src/ with a circular dependency: a -> b -> a."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "a.py").write_text("from src.b import x\ndef f(): pass\n")
    (src / "b.py").write_text("from src.a import f\ndef x(): pass\n")
    return src


class TestParseSrcImports:
    def test_from_import(self):
        result = _parse_src_imports("from src.health import HealthReport\n", {"health", "stats"})
        assert "health" in result

    def test_direct_import(self):
        result = _parse_src_imports("import src.stats\n", {"health", "stats"})
        assert "stats" in result

    def test_unknown_module_ignored(self):
        result = _parse_src_imports("from src.nonexistent import foo\n", {"health", "stats"})
        assert result == []

    def test_stdlib_not_included(self):
        result = _parse_src_imports("import os\nimport re\n", {"health", "stats"})
        assert result == []

    def test_multiple_imports(self):
        code = "from src.health import H\nfrom src.stats import S\n"
        result = _parse_src_imports(code, {"health", "stats", "brain"})
        assert "health" in result
        assert "stats" in result
        assert len(result) == 2

    def test_syntax_error_returns_empty(self):
        result = _parse_src_imports("def broken(:\n    pass\n", {"health"})
        assert result == []

    def test_no_imports_returns_empty(self):
        result = _parse_src_imports("x = 1\ndef f(): return x\n", {"health", "stats"})
        assert result == []

    def test_result_is_sorted(self):
        code = "from src.stats import x\nfrom src.health import y\n"
        result = _parse_src_imports(code, {"health", "stats"})
        assert result == sorted(result)


class TestModuleNode:
    def test_fan_out_counts_imports(self):
        node = ModuleNode("alpha", "src/alpha.py", ["beta", "gamma"], 50)
        assert node.fan_out == 2

    def test_fan_out_zero_when_no_imports(self):
        node = ModuleNode("gamma", "src/gamma.py", [], 30)
        assert node.fan_out == 0

    def test_to_dict_has_keys(self):
        node = ModuleNode("alpha", "src/alpha.py", ["beta"], 50)
        d = node.to_dict()
        assert "name" in d
        assert "imports" in d
        assert "fan_out" in d
        assert d["fan_out"] == 1


class TestDepGraph:
    @pytest.fixture
    def graph(self):
        nodes = [
            ModuleNode("alpha", "src/alpha.py", ["beta", "gamma"], 100),
            ModuleNode("beta", "src/beta.py", ["gamma"], 80),
            ModuleNode("gamma", "src/gamma.py", [], 60),
        ]
        return DepGraph(nodes=nodes)

    def test_module_names_sorted(self, graph):
        assert graph.module_names == ["alpha", "beta", "gamma"]

    def test_fan_in_gamma_has_two(self, graph):
        assert graph.fan_in["gamma"] == 2

    def test_fan_in_alpha_has_zero(self, graph):
        assert graph.fan_in["alpha"] == 0

    def test_no_cycles(self, graph):
        assert graph.find_cycles() == []

    def test_to_dict_has_keys(self, graph):
        d = graph.to_dict()
        assert "modules" in d
        assert "fan_in" in d
        assert "cycles" in d


class TestFindCycles:
    def test_detects_cycle(self, cyclic_src):
        graph = build_dep_graph(cyclic_src)
        cycles = graph.find_cycles()
        assert len(cycles) >= 1
        cycle_modules = {m for cycle in cycles for m in cycle}
        assert "a" in cycle_modules
        assert "b" in cycle_modules

    def test_no_cycle_in_simple_src(self, simple_src):
        graph = build_dep_graph(simple_src)
        assert graph.find_cycles() == []


class TestBuildDepGraph:
    def test_finds_all_modules(self, simple_src):
        graph = build_dep_graph(simple_src)
        names = graph.module_names
        assert "alpha" in names
        assert "beta" in names
        assert "gamma" in names
        assert "__init__" not in names

    def test_detects_imports(self, simple_src):
        graph = build_dep_graph(simple_src)
        alpha = next(n for n in graph.nodes if n.name == "alpha")
        assert "beta" in alpha.imports

    def test_line_counts_positive(self, simple_src):
        graph = build_dep_graph(simple_src)
        for node in graph.nodes:
            assert node.line_count > 0

    def test_isolated_module_has_no_imports(self, simple_src):
        graph = build_dep_graph(simple_src)
        gamma = next(n for n in graph.nodes if n.name == "gamma")
        assert gamma.imports == []


class TestRenderDepGraph:
    def test_returns_string(self, simple_src):
        result = render_dep_graph(build_dep_graph(simple_src))
        assert isinstance(result, str)

    def test_has_main_sections(self, simple_src):
        result = render_dep_graph(build_dep_graph(simple_src))
        assert "# Module Dependency Graph" in result
        assert "## Dependency Adjacency List" in result
        assert "## Coupling Metrics" in result

    def test_has_no_cycle_message(self, simple_src):
        result = render_dep_graph(build_dep_graph(simple_src))
        assert "No circular dependencies detected" in result

    def test_cycle_warning_appears(self, cyclic_src):
        result = render_dep_graph(build_dep_graph(cyclic_src))
        assert "circular dependency" in result.lower()

    def test_module_names_present(self, simple_src):
        result = render_dep_graph(build_dep_graph(simple_src))
        assert "alpha" in result
        assert "beta" in result
        assert "gamma" in result


class TestSaveDepGraph:
    def test_creates_markdown_file(self, simple_src, tmp_path):
        out = tmp_path / "docs" / "dep_graph.md"
        save_dep_graph(build_dep_graph(simple_src), out)
        assert out.exists()
        assert "Module Dependency Graph" in out.read_text()

    def test_creates_json_sidecar(self, simple_src, tmp_path):
        out = tmp_path / "dep_graph.md"
        save_dep_graph(build_dep_graph(simple_src), out)
        json_file = tmp_path / "dep_graph.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert "modules" in data

    def test_creates_parent_dirs(self, simple_src, tmp_path):
        out = tmp_path / "a" / "b" / "c" / "dep_graph.md"
        save_dep_graph(build_dep_graph(simple_src), out)
        assert out.exists()
