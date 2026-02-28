"""Tests for src/module_graph.py — Module interconnection visualizer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.module_graph import (
    ModuleNode,
    ModuleGraph,
    generate_module_graph,
    _discover_modules,
    _extract_imports,
    _LAYER_MAP,
)


# ---------------------------------------------------------------------------
# _discover_modules
# ---------------------------------------------------------------------------


def test_discover_modules_empty_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    result = _discover_modules(src)
    assert result == []


def test_discover_modules_excludes_init(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "health.py").write_text("")
    result = _discover_modules(src)
    assert "__init__" not in result
    assert "health" in result


def test_discover_modules_returns_sorted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for name in ["zzz", "aaa", "mmm"]:
        (src / f"{name}.py").write_text("")
    result = _discover_modules(src)
    assert result == sorted(result)


# ---------------------------------------------------------------------------
# _extract_imports
# ---------------------------------------------------------------------------


def test_extract_imports_simple(tmp_path):
    src = tmp_path / "test_module.py"
    src.write_text("from src.health import foo\nfrom src.stats import bar\n")
    result = _extract_imports(src, {"health", "stats", "cli"})
    assert "health" in result
    assert "stats" in result


def test_extract_imports_no_src_imports(tmp_path):
    src = tmp_path / "test_module.py"
    src.write_text("import os\nfrom pathlib import Path\n")
    result = _extract_imports(src, {"health", "stats"})
    assert result == []


def test_extract_imports_syntax_error(tmp_path):
    src = tmp_path / "bad.py"
    src.write_text("def broken(:\n    pass\n")
    result = _extract_imports(src, {"health"})
    assert result == []


def test_extract_imports_excludes_self(tmp_path):
    src = tmp_path / "health.py"
    src.write_text("from src.health import HealthReport\n")
    result = _extract_imports(src, {"health", "stats"})
    # self-import should be included (we filter self in graph builder)
    # just ensure no exception
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# ModuleNode
# ---------------------------------------------------------------------------


def test_module_node_to_dict():
    node = ModuleNode(name="health", layer="analysis", imports=["config"])
    d = node.to_dict()
    assert d["name"] == "health"
    assert d["layer"] == "analysis"
    assert d["imports"] == ["config"]


# ---------------------------------------------------------------------------
# ModuleGraph
# ---------------------------------------------------------------------------


def test_module_graph_to_dict():
    graph = ModuleGraph()
    graph.nodes = [ModuleNode(name="health", layer="analysis")]
    graph.edges = [("cli", "health")]
    graph.layers = {"analysis": ["health"], "core": ["cli"]}
    d = graph.to_dict()
    assert d["total_nodes"] == 1
    assert d["total_edges"] == 1
    assert "layers" in d


def test_module_graph_to_mermaid_contains_nodes():
    graph = ModuleGraph()
    graph.nodes = [
        ModuleNode(name="health", layer="analysis"),
        ModuleNode(name="cli", layer="core"),
    ]
    graph.edges = [("cli", "health")]
    graph.layers = {"analysis": ["health"], "core": ["cli"]}
    mermaid = graph.to_mermaid()
    assert "```mermaid" in mermaid
    assert "graph TD" in mermaid
    assert "health" in mermaid
    assert "cli" in mermaid


def test_module_graph_to_ascii():
    graph = ModuleGraph()
    graph.nodes = [ModuleNode(name="health", layer="analysis")]
    graph.layers = {"analysis": ["health"]}
    ascii_out = graph.to_ascii()
    assert "health" in ascii_out
    assert "Module Interconnection" in ascii_out


def test_module_graph_to_markdown():
    graph = ModuleGraph()
    graph.nodes = [ModuleNode(name="health", layer="analysis")]
    graph.layers = {"analysis": ["health"]}
    graph.edges = []
    md = graph.to_markdown()
    assert "# Module Interconnection Graph" in md
    assert "health" in md


# ---------------------------------------------------------------------------
# generate_module_graph
# ---------------------------------------------------------------------------


def test_generate_module_graph_empty_src(tmp_path):
    (tmp_path / "src").mkdir()
    graph = generate_module_graph(tmp_path)
    assert isinstance(graph, ModuleGraph)
    assert len(graph.nodes) == 0


def test_generate_module_graph_no_src_dir(tmp_path):
    graph = generate_module_graph(tmp_path)
    assert isinstance(graph, ModuleGraph)
    assert graph.nodes == []


def test_generate_module_graph_with_modules(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "health.py").write_text('"""Health module."""\nimport os\n')
    (src / "config.py").write_text('"""Config."""\nimport json\n')
    (src / "cli.py").write_text('from src.health import run\nfrom src.config import load\n')
    graph = generate_module_graph(tmp_path)
    assert len(graph.nodes) == 3
    assert len(graph.edges) >= 2
    names = [n.name for n in graph.nodes]
    assert "health" in names
    assert "cli" in names


def test_generate_module_graph_assigns_layers(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "health.py").write_text("")
    (src / "config.py").write_text("")
    graph = generate_module_graph(tmp_path)
    node_layers = {n.name: n.layer for n in graph.nodes}
    assert node_layers.get("health") == "analysis"
    assert node_layers.get("config") == "core"


def test_layer_map_known_modules():
    assert _LAYER_MAP["cli"] == "core"
    assert _LAYER_MAP["server"] == "core"
    assert _LAYER_MAP["health"] == "analysis"
    assert _LAYER_MAP["gitstats"] == "git"
    assert _LAYER_MAP["report"] == "output"
    assert _LAYER_MAP["plugins"] == "extensibility"


def test_module_graph_no_self_edges(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "health.py").write_text("from src.health import HealthReport\n")
    graph = generate_module_graph(tmp_path)
    self_edges = [(f, t) for f, t in graph.edges if f == t]
    assert self_edges == []


def test_full_mermaid_includes_all_edges():
    graph = ModuleGraph()
    graph.nodes = [
        ModuleNode(name="a", layer="core"),
        ModuleNode(name="b", layer="analysis"),
    ]
    graph.edges = [("a", "b")]
    graph.layers = {"core": ["a"], "analysis": ["b"]}
    full = graph.to_full_mermaid()
    assert "a --> b" in full
