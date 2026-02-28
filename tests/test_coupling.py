"""Tests for src/coupling.py — Module Coupling Analyzer."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from src.coupling import (
    ModuleCoupling,
    CouplingReport,
    analyze_coupling,
    render_coupling_report,
    save_coupling_report,
    _collect_src_modules,
    _parse_imports,
    _analyze_abstractness,
    _find_cycles,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MODULE_A = textwrap.dedent("""\
    \"\"\"Module A.\"\"\"
    from __future__ import annotations

    def do_something() -> int:
        \"\"\"Public function.\"\"\"
        return 42
""")

MODULE_B = textwrap.dedent("""\
    \"\"\"Module B imports module_a.\"\"\"
    from __future__ import annotations
    from src.module_a import do_something

    def consume() -> int:
        return do_something() + 1
""")

MODULE_C = textwrap.dedent("""\
    \"\"\"Module C imports both A and B.\"\"\"
    from src.module_a import do_something
    from src.module_b import consume

    class Handler:
        pass
""")

MODULE_ABSTRACT = textwrap.dedent("""\
    \"\"\"Module with abstract-style functions.\"\"\"
    from abc import ABC, abstractmethod

    class BaseAnalyzer(ABC):
        pass

    def abstract_func():
        \"\"\"Just a docstring — no implementation.\"\"\"

    def concrete_func():
        return 1 + 1
""")

MODULE_CIRCULAR_X = textwrap.dedent("""\
    from src.circular_y import something_y

    def something_x():
        return something_y()
""")

MODULE_CIRCULAR_Y = textwrap.dedent("""\
    from src.circular_x import something_x

    def something_y():
        return something_x()
""")


@pytest.fixture
def simple_src(tmp_path: Path) -> Path:
    """Create a simple src/ with 3 modules."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "module_a.py").write_text(MODULE_A)
    (src / "module_b.py").write_text(MODULE_B)
    (src / "module_c.py").write_text(MODULE_C)
    return tmp_path


@pytest.fixture
def abstract_src(tmp_path: Path) -> Path:
    """Create a src/ with an abstract module."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "module_abstract.py").write_text(MODULE_ABSTRACT)
    return tmp_path


@pytest.fixture
def circular_src(tmp_path: Path) -> Path:
    """Create a src/ with circular imports."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "circular_x.py").write_text(MODULE_CIRCULAR_X)
    (src / "circular_y.py").write_text(MODULE_CIRCULAR_Y)
    return tmp_path


@pytest.fixture
def empty_src(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# _collect_src_modules
# ---------------------------------------------------------------------------

class TestCollectSrcModules:
    def test_finds_py_files(self, simple_src: Path):
        src = simple_src / "src"
        modules = _collect_src_modules(src)
        assert "module_a" in modules
        assert "module_b" in modules
        assert "module_c" in modules

    def test_excludes_init(self, simple_src: Path):
        src = simple_src / "src"
        modules = _collect_src_modules(src)
        assert "__init__" not in modules

    def test_returns_paths(self, simple_src: Path):
        src = simple_src / "src"
        modules = _collect_src_modules(src)
        for name, path in modules.items():
            assert path.exists()
            assert path.suffix == ".py"

    def test_empty_src(self, empty_src: Path):
        src = empty_src / "src"
        modules = _collect_src_modules(src)
        assert modules == {}


# ---------------------------------------------------------------------------
# _parse_imports
# ---------------------------------------------------------------------------

class TestParseImports:
    def test_detects_from_src_import(self, simple_src: Path):
        path = simple_src / "src" / "module_b.py"
        known = {"module_a", "module_b", "module_c"}
        imports = _parse_imports(path, known)
        assert "module_a" in imports

    def test_no_imports_for_standalone(self, simple_src: Path):
        path = simple_src / "src" / "module_a.py"
        known = {"module_a", "module_b", "module_c"}
        imports = _parse_imports(path, known)
        assert imports == []

    def test_multiple_imports(self, simple_src: Path):
        path = simple_src / "src" / "module_c.py"
        known = {"module_a", "module_b", "module_c"}
        imports = _parse_imports(path, known)
        assert "module_a" in imports
        assert "module_b" in imports

    def test_nonexistent_file(self, tmp_path: Path):
        imports = _parse_imports(tmp_path / "nonexistent.py", {"a", "b"})
        assert imports == []


# ---------------------------------------------------------------------------
# _analyze_abstractness
# ---------------------------------------------------------------------------

class TestAnalyzeAbstractness:
    def test_module_a_low_abstractness(self, simple_src: Path):
        path = simple_src / "src" / "module_a.py"
        a, syms, total = _analyze_abstractness(path)
        assert a < 0.5

    def test_abstract_module(self, abstract_src: Path):
        path = abstract_src / "src" / "module_abstract.py"
        a, syms, total = _analyze_abstractness(path)
        assert a > 0.0

    def test_returns_tuple(self, simple_src: Path):
        path = simple_src / "src" / "module_a.py"
        result = _analyze_abstractness(path)
        assert len(result) == 3

    def test_abstractness_range(self, simple_src: Path):
        path = simple_src / "src" / "module_a.py"
        a, _, _ = _analyze_abstractness(path)
        assert 0.0 <= a <= 1.0


# ---------------------------------------------------------------------------
# _find_cycles
# ---------------------------------------------------------------------------

class TestFindCycles:
    def test_no_cycles_in_acyclic_graph(self):
        graph = {"a": ["b"], "b": ["c"], "c": []}
        cycles = _find_cycles(graph)
        assert cycles == []

    def test_detects_simple_cycle(self):
        graph = {"x": ["y"], "y": ["x"]}
        cycles = _find_cycles(graph)
        assert len(cycles) >= 1
        all_nodes = set()
        for c in cycles:
            all_nodes.update(c)
        assert "x" in all_nodes or "y" in all_nodes

    def test_detects_self_loop(self):
        graph = {"a": ["a"]}
        cycles = _find_cycles(graph)
        assert len(cycles) >= 1

    def test_empty_graph(self):
        assert _find_cycles({}) == []


# ---------------------------------------------------------------------------
# ModuleCoupling
# ---------------------------------------------------------------------------

class TestModuleCoupling:
    def test_to_dict_keys(self):
        mc = ModuleCoupling(name="test")
        d = mc.to_dict()
        assert "name" in d
        assert "afferent" in d
        assert "efferent" in d
        assert "instability" in d
        assert "grade" in d

    def test_defaults(self):
        mc = ModuleCoupling(name="foo")
        assert mc.afferent == 0
        assert mc.efferent == 0
        assert mc.instability == 0.0


# ---------------------------------------------------------------------------
# CouplingReport
# ---------------------------------------------------------------------------

class TestCouplingReport:
    def test_to_dict(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        d = report.to_dict()
        assert "modules" in d
        assert "avg_instability" in d
        assert isinstance(d["modules"], list)

    def test_to_json(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        data = json.loads(report.to_json())
        assert "modules" in data

    def test_to_markdown(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        md = report.to_markdown()
        assert isinstance(md, str)
        assert len(md) > 0


# ---------------------------------------------------------------------------
# analyze_coupling
# ---------------------------------------------------------------------------

class TestAnalyzeCoupling:
    def test_returns_report(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        assert isinstance(report, CouplingReport)

    def test_correct_module_count(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        assert len(report.modules) == 3

    def test_module_names_present(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        names = [m.name for m in report.modules]
        assert "module_a" in names
        assert "module_b" in names
        assert "module_c" in names

    def test_afferent_coupling(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        a_module = next(m for m in report.modules if m.name == "module_a")
        assert a_module.afferent == 2

    def test_efferent_coupling(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        c_module = next(m for m in report.modules if m.name == "module_c")
        assert c_module.efferent == 2

    def test_instability_range(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        for m in report.modules:
            assert 0.0 <= m.instability <= 1.0

    def test_stable_module(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        a = next(m for m in report.modules if m.name == "module_a")
        assert a.instability == 0.0

    def test_circular_dependencies_detected(self, circular_src: Path):
        report = analyze_coupling(repo_path=circular_src)
        assert len(report.circular_groups) >= 1

    def test_empty_src(self, empty_src: Path):
        report = analyze_coupling(repo_path=empty_src)
        assert report.modules == []

    def test_missing_src(self, tmp_path: Path):
        report = analyze_coupling(repo_path=tmp_path)
        assert "not found" in report.summary

    def test_avg_instability_in_range(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        assert 0.0 <= report.avg_instability <= 1.0

    def test_grades_assigned(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        for m in report.modules:
            assert m.grade in ("A", "B", "C", "D", "F")


# ---------------------------------------------------------------------------
# render_coupling_report
# ---------------------------------------------------------------------------

class TestRenderCouplingReport:
    def test_returns_string(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        md = render_coupling_report(report)
        assert isinstance(md, str)

    def test_contains_table(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        md = render_coupling_report(report)
        assert "|" in md

    def test_contains_module_names(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        md = render_coupling_report(report)
        assert "module_a" in md
        assert "module_b" in md

    def test_contains_stability_summary(self, simple_src: Path):
        report = analyze_coupling(repo_path=simple_src)
        md = render_coupling_report(report)
        assert "Stability Summary" in md or "stable" in md.lower()

    def test_circular_warning_shown(self, circular_src: Path):
        report = analyze_coupling(repo_path=circular_src)
        md = render_coupling_report(report)
        assert "Circular" in md or "circular" in md


# ---------------------------------------------------------------------------
# save_coupling_report
# ---------------------------------------------------------------------------

class TestSaveCouplingReport:
    def test_creates_md_file(self, simple_src: Path, tmp_path: Path):
        report = analyze_coupling(repo_path=simple_src)
        out = tmp_path / "coupling.md"
        save_coupling_report(report, out)
        assert out.exists()

    def test_creates_json_sidecar(self, simple_src: Path, tmp_path: Path):
        report = analyze_coupling(repo_path=simple_src)
        out = tmp_path / "coupling.md"
        save_coupling_report(report, out)
        json_path = tmp_path / "coupling.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert "modules" in data

    def test_creates_parent_dirs(self, simple_src: Path, tmp_path: Path):
        report = analyze_coupling(repo_path=simple_src)
        out = tmp_path / "nested" / "coupling.md"
        save_coupling_report(report, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# Integration: real repo
# ---------------------------------------------------------------------------

class TestRealRepo:
    def test_real_src(self):
        repo = Path(__file__).resolve().parent.parent
        if not (repo / "src").exists():
            pytest.skip("src/ not found")
        report = analyze_coupling(repo_path=repo)
        assert len(report.modules) >= 5
        names = [m.name for m in report.modules]
        assert "cli" in names or "stats" in names
        for m in report.modules:
            assert 0.0 <= m.instability <= 1.0
        md = report.to_markdown()
        assert len(md) > 200
